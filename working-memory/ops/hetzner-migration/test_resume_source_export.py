"""Offline regression tests; no network, credentials or operational main calls."""
import copy
import hashlib
import unittest
import io
import json
import stat
import subprocess
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch
import final_phase_common as transport
from final_quiescence_once import EFFECTIVE_PRIVILEGES_SQL, verify_effective_freeze
from vault_copy_codec import copy_value, vault_copy_rows, verify_vault_copy


def fixture():
    cipher = 'base64-line-one\nbase64-line-two'
    metadata = {'id': 'fixture-id', 'name': r'\N', 'description': None, 'key_id': None,
                'created_at': '2026-10-03T18:00:00+00:00',
                'updated_at': '2026-10-03T18:00:01+00:00',
                'nonce_hex': '0123abcd',
                'cipher_sha256': hashlib.sha256(cipher.encode()).hexdigest()}
    sql = ('COPY vault.secrets (id, name, description, secret, key_id, nonce, created_at, updated_at) FROM stdin;\n'
           'fixture-id\t' + r'\\N' + '\t' + r'\N' + '\t' + r'base64-line-one\nbase64-line-two' + '\t'
           + r'\N' + '\t' + r'\\x0123abcd' + '\t2026-10-03 18:00:00+00\t2026-10-03 18:00:01+00\n' + r'\.' + '\n')
    return sql, metadata


class CopyTests(unittest.TestCase):
    def test_null_literal_and_empty(self):
        self.assertIsNone(copy_value(r'\N'))
        self.assertEqual(copy_value(r'\\N'), r'\N')
        self.assertEqual(copy_value(''), '')

    def test_copy_escapes_bytes_and_unicode(self):
        self.assertEqual(copy_value(r'a\n\r\t\b\f\v\\z'), 'a\n\r\t\b\f\v\\z')
        self.assertEqual(copy_value(r'\101\x42\q'), 'ABq')
        self.assertEqual(copy_value(r'\303\274'), 'ü')
        self.assertEqual(copy_value('é中文'), 'é中文')
        with self.assertRaises(ValueError):
            copy_value('incomplete' + '\\')

    def test_cipher_nonce_full_metadata(self):
        sql, metadata = fixture()
        self.assertTrue(verify_vault_copy(sql, [metadata]))
        for key in metadata:
            changed = copy.deepcopy(metadata)
            changed[key] = '2026-10-03T18:00:03+00:00' if key.endswith('_at') else 'different'
            with self.subTest(field=key), self.assertRaises(AssertionError):
                verify_vault_copy(sql, [changed])

    def test_transport_hash_reproduces_old_bug(self):
        sql, metadata = fixture()
        transported = sql.split('\n')[1].split('\t')[3]
        self.assertNotEqual(hashlib.sha256(transported.encode()).hexdigest(), metadata['cipher_sha256'])
        self.assertEqual(vault_copy_rows(sql)[0]['secret'], 'base64-line-one\nbase64-line-two')

    def test_legacy_metadata_requires_null_key_id(self):
        sql, metadata = fixture()
        del metadata['key_id']
        self.assertTrue(verify_vault_copy(sql,[metadata]))
        with self.assertRaises(AssertionError):
            verify_vault_copy(sql.replace('\t'+r'\N'+'\t'+r'\\x', '\tkey-id\t'+r'\\x'),[metadata])

    def test_malformed_copy_fails_closed(self):
        sql, _ = fixture()
        for malformed in [sql.replace('fixture-id\t', ''), sql.replace(r'\.', ''), sql + sql,
                          sql.replace('(id, name,', '(id, id,')]:
            with self.assertRaises(ValueError):
                vault_copy_rows(malformed)


class FreezeTests(unittest.TestCase):
    def test_roles_and_each_effective_privilege_fail_closed(self):
        rows = [{'role': role, 'writable_tables': 0, 'executable_writers': 0}
                for role in ['anon', 'authenticated', 'service_role']]
        verify_effective_freeze(rows)
        for index in range(3):
            for field in ['writable_tables', 'executable_writers']:
                changed = copy.deepcopy(rows)
                changed[index][field] = 1
                with self.assertRaises(AssertionError):
                    verify_effective_freeze(changed)
        for changed in [rows[:2], rows + [rows[0]], [rows[0], rows[0], rows[2]]]:
            with self.assertRaises(AssertionError):
                verify_effective_freeze(changed)

    def test_query_uses_catalog_oid_and_complete_writer_scope(self):
        self.assertNotIn('regprocedure', EFFECTIVE_PRIVILEGES_SQL)
        for predicate in ["n.nspname='public'", "p.proowner='postgres'::regrole",
                          "p.provolatile='v'", "p.prorettype<>'trigger'::regtype",
                          "has_function_privilege(r.rolname,p.oid,'EXECUTE')",
                          "'INSERT,UPDATE,DELETE,TRUNCATE'"]:
            self.assertIn(predicate, EFFECTIVE_PRIVILEGES_SQL)


class PrivatePrimaryErrorTests(unittest.TestCase):
    def test_http_keychain_and_ssh_primary_errors_are_private_no_retry(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(transport,'ERROR_DIR',Path(directory)/'errors'):
            secret=b'private-primary-fixture'
            http=urllib.error.HTTPError('https://fixture.invalid',400,'bad',{},io.BytesIO(secret))
            with patch.object(transport,'source_token',return_value='fixture'), patch.object(transport.urllib.request,'urlopen',side_effect=http) as request:
                with self.assertRaises(RuntimeError) as caught:transport.sql('SELECT 1')
                self.assertNotIn(secret.decode(),str(caught.exception))
                self.assertEqual(request.call_count,1)
            for action,result in [(lambda:transport.shell('fixture'),subprocess.CompletedProcess([],1,secret,secret)),
                                  (transport.source_token,subprocess.CompletedProcess([],1,secret.decode(),secret.decode()))]:
                with patch.object(transport.subprocess,'run',return_value=result) as run:
                    with self.assertRaises(RuntimeError) as caught:action()
                    self.assertNotIn(secret.decode(),str(caught.exception))
                    self.assertEqual(run.call_count,1)
            files=list((Path(directory)/'errors').glob('*.json'))
            self.assertEqual(len(files),3)
            self.assertEqual(stat.S_IMODE((Path(directory)/'errors').stat().st_mode),0o700)
            for file in files:
                self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
                self.assertIn('kind',json.loads(file.read_text()))
            self.assertEqual(len({file.name for file in files}),3)

    def test_ssh_timeout_preserves_partial_primary_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(transport,'ERROR_DIR',Path(directory)/'errors'):
            error=subprocess.TimeoutExpired(['fixture'],1,output=b'partial',stderr=b'primary-error')
            with patch.object(transport.subprocess,'run',side_effect=error) as run:
                with self.assertRaises(RuntimeError):transport.shell('fixture')
                self.assertEqual(run.call_count,1)
            receipt=json.loads(next((Path(directory)/'errors').glob('*.json')).read_text())
            self.assertEqual(receipt['kind'],'SSH_TIMEOUT')
            self.assertEqual(receipt['stderr']['base64'],'cHJpbWFyeS1lcnJvcg==')


if __name__ == '__main__':
    unittest.main()
