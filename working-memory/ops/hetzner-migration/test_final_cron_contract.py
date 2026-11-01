"""One bounded Cron-contract run; actual guards, synthetic transports, no recovery."""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import traceback
import types
import unittest
from unittest.mock import Mock, patch
import final_prewrite_rollback_once as r
import final_target_partial_source_return_once as p
import final_target_runtime_permissions_followup_once as permissions
import final_writer_open_once as w
import final_phase_common as c
from final_quiescence_once import acl_query, EFFECTIVE_PRIVILEGES_SQL

PRIVATE = Path(os.environ['CRON_CONTRACT_PRIVATE_DIR'])
SOURCE_BAD = [[{'count': v}] for v in (1, 2, False, True, 0.0, None, '0')] + [None, {}, [], [0], [{'count': 0}, {'count': 0}], [{'count': 0, 'extra': 0}], [{'other': 0}], ({'count': 0},)]
TARGET_BAD = [1, 2, False, True, 0.0, None, '0', [], {}, [{'count': 0}]]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    """All external boundaries are mocks; SQL dispatch allows only SELECTs."""
    def __init__(self, folder, source_response, target_response):
        self.root = folder
        folder.mkdir(mode=0o700)
        self.events = []
        self.source_response = source_response
        self.target_response = target_response
        self.after_stop_bad = False
        self.stopped = False
        self.gate_path = folder/'gate.json'
        self.gate_path.write_bytes(b'{}')
        self.gate = {'run_dir': str(folder), 'dump_sha256': 'synthetic', 'allcopy_receipt': {'path': str(folder/'final-snapshot-comparison.json')}}
        self.values = {'acl_frozen': b'[]', 'config': b'[]', 'query': b'SELECT synthetic_projection', 'runtime': b'{}', 'nginx_original': b'original', 'nginx_maintenance': b'maintenance'}
        self.frozen = []
        self.names = []
        self.definitions = folder/'disabled-definitions.json'
        self.definitions.write_bytes(b'[{"jobid":1,"active":false},{"jobid":2,"active":false}]\n')
        self.definition_bytes = self.definitions.read_bytes()
        self.local = folder
        self.read = Mock(return_value=b'{}')
        for name in ('markers_absent', 'workflows', 'frontend_guard', 'scopes_guard', 'mutation_guard', 'maintenance', 'restore_host', 'restore_config', 'restore_partial_host', 'start_source', 'health', 'ingress', 'resume', 'scopes', 'frontend', 'timer'):
            setattr(self, name, Mock())
        self.restore_acl = Mock(side_effect=AssertionError('Source grants forbidden in narrow test'))
        self.source_projection = types.MethodType(p.PartialOperations.source_projection, self)
        self.source_frozen = types.MethodType(p.PartialOperations.source_frozen, self)
        self.preflight_partial = types.MethodType(p.PartialOperations.preflight_partial, self)
        self.preflight = types.MethodType(r.MacReturnOperations.preflight, self)

    def source_sql(self, query):
        assert query.startswith('SELECT '), 'Non-read Source SQL forbidden'
        if query == 'SELECT count(*) AS count FROM cron.job WHERE active':
            self.events.append('source_cron')
            return [{'count': 1}] if self.after_stop_bad and self.stopped else self.source_response
        if 'cron.job' in query:
            raise AssertionError('Incorrect Source cron SQL')
        if query == EFFECTIVE_PRIVILEGES_SQL:
            return [{'role': role, 'writable_tables': 0, 'executable_writers': 0} for role in ['anon', 'authenticated', 'service_role']]
        if query == acl_query():
            return []
        if query == self.values['query'].decode():
            return [{'value': []}]
        if query.startswith('SELECT json_build_object'):
            return [{'value': {'running': 0, 'unknown_model': 0, 'unknown_question': 0, 'config': []}}]
        raise AssertionError('Unexpected Source SQL: '+query)

    def target_sql(self, query):
        assert query.startswith('SELECT '), 'Non-read Target SQL forbidden'
        if query == 'SELECT count(*) FROM cron.job WHERE active':
            self.events.append('target_cron')
            return self.target_response
        if 'cron.job' in query:
            raise AssertionError('Incorrect Target cron SQL')
        if query == self.values['query'].decode():
            return []
        if query.startswith('SELECT json_agg'):
            return []
        if query.startswith('SELECT json_build_object'):
            return {'running': 0, 'unknown_model': 0, 'unknown_question': 0}
        raise AssertionError('Unexpected Target SQL: '+query)

    def observe_host(self, *args, stopped=False):
        self.events.append('observe_stopped' if stopped else 'observe')
        return {'runtime_attempt': True}

    def stop_target(self):
        self.events.append('stop')
        self.stopped = True

    def stop_partial(self, *args):
        self.stop_target()

    def remote_python(self, code, timeout=60):
        # Execute the FULL actual embedded preflight, with disposable path mapping
        # and a synthetic HostOperations. No shell, Docker, DB or SSH dispatch.
        self.events.append('embedded')
        (self.root/'embedded.py').write_text(code)
        nginx = self.root/'nginx'
        nginx.write_bytes(b'original')
        backup = self.root/'backup.json'
        backup.write_text(json.dumps({'enabled': True, 'migration_run': self.root.name}))
        cache = self.root/'cache'
        (cache/'projections-rc1-20260919/response-outbox').mkdir(parents=True)
        (cache/'question-outbox').mkdir()
        owner = self
        class Host:
            def verify_runtime(self, *args, **kwargs):
                pass
            def sql(self, query):
                return owner.target_sql(query)
            def call(self, args, **kwargs):
                if args[:2] == ['systemctl', 'show']:
                    return b'inactive'
                if args[:2] == ['docker', 'inspect']:
                    return json.dumps([{'Config': {'Env': ['MEMORY_CACHE_DIR=/app/.local/projections-rc1-20260919', 'MEMORY_QA_OUTBOX=/app/.local/question-outbox']}, 'Mounts': [{'Destination': '/app/.local', 'Type': 'bind', 'Source': str(cache)}]}]).encode()
                if args[:3] == ['docker', 'exec', '-i']:
                    return b'0'
                raise AssertionError('Unexpected embedded call')
        mapped = code.replace('/etc/nginx/sites-available/alexa', str(nginx)).replace('/opt/dashboard-memory-canonical-draft/.local/selfhost-backup.json', str(backup)).replace('/opt/dashboard-memory-canonical-draft/.local/cache', str(cache))
        with patch.object(w, 'HostOperations', Host):
            exec(compile(mapped, '<actual-embedded-preflight>', 'exec'), {})
        return b''


class CronContract(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for owner, name in [(subprocess, 'run'), (subprocess, 'check_output'), (subprocess, 'Popen'), (socket, 'create_connection'), (c, 'shell'), (c, 'n8n_sql')]:
            self.stack.enter_context(patch.object(owner, name, side_effect=AssertionError('External operation forbidden')))
        self.stack.enter_context(patch.object(p, 'bound', return_value=json.dumps({'source_sha256': 'synthetic', 'mismatches': [], 'comparison_before_auth_vault_acl': True}).encode()))

    def run_case(self, family, index, source, target, deny, action):
        folder = PRIVATE/(family+'-'+str(index))
        fixture = Fixture(folder, source, target)
        record = {'family': family, 'index': index, 'source': source, 'target': target, 'expected': 'DENY' if deny else 'ACCEPT'}
        try:
            if deny:
                with self.assertRaises(Exception) as caught:
                    action(fixture)
                record['rejection'] = str(caught.exception)
                self.assertIn('cron' if family.startswith('partial') else ('scheduled writer' if 'source' in family else ''), record['rejection'])
            else:
                action(fixture)
            self.assertIn('target_cron' if family.endswith('target') else 'source_cron', fixture.events)
            self.assertEqual(fixture.definitions.read_bytes(), fixture.definition_bytes)
            fixture.restore_acl.assert_not_called()
            self.assertNotIn('stop', fixture.events)
            record['status'] = 'PASS'
        except BaseException:
            record['status'] = 'FAIL'
            record['traceback'] = traceback.format_exc()
            raise
        finally:
            record['events'] = fixture.events
            record['definitions_sha256'] = sha(fixture.definitions)
            (folder/'case-primary.json').write_text(json.dumps(record, indent=2))
            for path in folder.rglob('*'):
                path.chmod(0o700 if path.is_dir() else 0o600)

    def rejection_entrypoint(self, f, module):
        # Actual execute reaches actual preflight; all mutations remain forbidden.
        with patch.object(module, 'load', return_value=(f.gate, {}, f.values, [], [])), patch.object(module, 'durable', side_effect=AssertionError('Marker before cron rejection')), patch.object(r, 'private_error', side_effect=lambda error: str(error)):
            if module is p:
                with patch.object(p, 'proof_extra'):
                    p.execute(f.root, f.gate_path, operations=f)
            else:
                r.execute(f.root, f.gate_path, operations=f)

    def test_prewrite_source(self):
        for i, value in enumerate([[{'count': 0}]]+SOURCE_BAD):
            with self.subTest(case=i):
                self.run_case('prewrite-source', i, value, 0, i>0, lambda f: self.rejection_entrypoint(f, r) if i else f.preflight(f.gate, f.values, [], []))

    def test_prewrite_embedded_target(self):
        for i, value in enumerate([0]+TARGET_BAD):
            with self.subTest(case=i):
                self.run_case('prewrite-target', i, [{'count': 0}], value, i>0, lambda f: self.rejection_entrypoint(f, r) if i else f.preflight(f.gate, f.values, [], []))

    def test_partial_source(self):
        for i, value in enumerate([[{'count': 0}]]+SOURCE_BAD):
            with self.subTest(case=i):
                self.run_case('partial-source', i, value, 0, i>0, lambda f: self.rejection_entrypoint(f, p) if i else f.source_frozen(f.values, [], []))
        # Actual partial execute rechecks Source after Target stop and before grants.
        f = Fixture(PRIVATE/'partial-poststop-rejection', [{'count': 0}], 0)
        f.after_stop_bad = True
        record = {'family': 'partial-poststop-rejection'}
        try:
            with patch.object(p, 'load', return_value=(f.gate, {}, f.values, [], [])), patch.object(p, 'proof_extra'), patch.object(p, 'durable'), patch.object(r, 'private_error', side_effect=lambda error: str(error)):
                with self.assertRaisesRegex(r.PreconditionsError, 'Source cron writer'):
                    p.execute(f.root, f.gate_path, operations=f)
            self.assertEqual(f.events, ['source_cron', 'observe', 'target_cron', 'stop', 'observe_stopped', 'source_cron'])
            f.restore_acl.assert_not_called()
            self.assertEqual(f.definitions.read_bytes(), f.definition_bytes)
            record['status'] = 'PASS'
        except BaseException:
            record.update(status='FAIL', traceback=traceback.format_exc())
            raise
        finally:
            record['events'] = f.events
            (f.root/'case-primary.json').write_text(json.dumps(record, indent=2))

    def test_partial_target_and_bindings(self):
        for i, value in enumerate([0]+TARGET_BAD):
            with self.subTest(case=i):
                self.run_case('partial-target', i, [{'count': 0}], value, i>0, lambda f: self.rejection_entrypoint(f, p) if i else f.preflight_partial(f.gate, f.values, [], []))
        original = PRIVATE/'originals'
        base = Path(r.__file__).parent
        # Exact whole-file comparison defines the only permitted four site edits.
        before = (original/Path(r.__file__).name).read_text()
        expected = before.replace("        require(self.source_sql('SELECT count(*) AS count FROM cron.job') == [{'count': 0}], 'Source scheduled writer unknown/nonempty')", "        cron = self.source_sql('SELECT count(*) AS count FROM cron.job WHERE active')\n        require(type(cron) is list and len(cron) == 1 and type(cron[0]) is dict and set(cron[0]) == {'count'} and type(cron[0]['count']) is int and cron[0]['count'] == 0, 'Source scheduled writer unknown/nonempty')").replace("assert op.sql('SELECT count(*) FROM cron.job')==0", "cron=op.sql('SELECT count(*) FROM cron.job WHERE active')\nassert type(cron) is int and cron==0")
        self.assertEqual(Path(r.__file__).read_text(), expected)
        before = (original/Path(p.__file__).name).read_text()
        expected = before.replace("        require(self.source_sql('SELECT count(*) AS count FROM cron.job')==[{'count':0}],'Source cron writer')", "        cron=self.source_sql('SELECT count(*) AS count FROM cron.job WHERE active')\n        require(type(cron) is list and len(cron)==1 and type(cron[0]) is dict and set(cron[0])=={'count'} and type(cron[0]['count']) is int and cron[0]['count']==0,'Source cron writer')").replace("            require(self.target_sql('SELECT count(*) FROM cron.job')==0,'Target cron writer')", "            cron=self.target_sql('SELECT count(*) FROM cron.job WHERE active')\n            require(type(cron) is int and cron==0,'Target cron writer')")
        self.assertEqual(Path(p.__file__).read_text(), expected)
        oldpermissions = (original/Path(permissions.__file__).name).read_text()
        oldpartial = sha(original/Path(p.__file__).name)
        self.assertEqual(Path(permissions.__file__).read_text(), oldpermissions.replace("PARTIAL_SHA='"+oldpartial+"'", "PARTIAL_SHA='"+sha(Path(p.__file__))+"'"))
        self.assertEqual(permissions.PARTIAL_SHA, sha(Path(p.__file__)))
        self.assertEqual(permissions.OLD_SHA, sha(base/'final_target_runtime_once.py'))
        self.assertIs(p.r, r)
        inventory = json.loads((PRIVATE/'protected-final-original.json').read_bytes())['hashes']
        # All transitive helpers in PartialReturn.SCRIPTS remain original except r.
        for name in p.SCRIPTS:
            if name not in (Path(p.__file__).name, Path(r.__file__).name):
                self.assertEqual(sha(base/name), inventory['working-memory/ops/hetzner-migration/'+name])
        for file in (Path(r.__file__), Path(p.__file__), Path(permissions.__file__), Path(__file__)):
            ast.parse(file.read_text(), filename=str(file))
        (PRIVATE/'bindings-primary.json').write_text(json.dumps({'status': 'PASS', 'partial_sha': permissions.PARTIAL_SHA, 'old_runtime_sha': permissions.OLD_SHA, 'four_sites_only': True, 'transitive_scripts': list(p.SCRIPTS)}, indent=2))


if __name__ == '__main__':
    unittest.main()
