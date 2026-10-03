"""Offline safety proof. Synthetic receipts are temporary test data, never gates."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import final_writer_open_once as writer
import final_prewrite_rollback_once as rollback


class FinalWriterSafety(unittest.TestCase):
    def fixture(self, root):
        now = dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc)
        run = root/'final-export-20261004T000000Z'; run.mkdir()
        remote = str(run)
        refs = {}; receipts = {
            'comparison': {'mismatches': {}, 'comparison_before_auth_vault_acl': True, 'source_sha256': 'a'*64},
            'runtime': {'status': 'TARGET_READONLY_RUNTIME_ACTIVE', 'closed_flags': writer.CLOSED,
                        'base_image': writer.BASE, 'backend_origin': writer.ORIGIN,
                        'target_image': 'sha256:'+'b'*64, 'writers_opened': False},
            'flags': writer.ORIGINAL,
            'config': [{'space_id': 'fixture-only', 'enabled': True, 'cutoff': 'preserved', 'budget': 17}],
            'source': {'problem_id': writer.PROBLEM, 'run_dir': remote, 'observed_at': now.isoformat(),
                       'query_sha256': 'c'*64, 'roles': [{'role': r, 'writable_tables': 0, 'executable_writers': 0}
                       for r in ['anon', 'authenticated', 'service_role']], 'catalog_function_count': 43,
                       'source_config': [{'space_id': 'fixture-only', 'enabled': False, 'cutoff': 'preserved', 'budget': 17}],
                       'source_backend_running': False, 'other_hosted_writer_processes': [], 'primary_receipts': []},
            'owner': {'status': 'PASSED', 'run_dir': remote, 'source_uid': 'fixture-uid', 'target_uid': 'fixture-uid',
                      'overview': True, 'archive': True, 'saved_summary': True, 'same_original': True,
                      'readonly': True, 'primary_receipts': []},
            'frontend': {'status': 'PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED',
                         'production': {'readyState': 'READY', 'target': 'production', 'aliases': list(writer.ALIASES)},
                         'checks': [{'alias': a, 'exact_index': True, 'exact_headers': True} for a in writer.ALIASES]},
            'backup': {'state': 'ok', 'archive': 'dashboard-20261004T000000Z.tar.gz', 'sha256': 'd'*64, 'bytes': 99,
                       'selfhost': {'enabled': True, 'restore_verified': True},
                       'n8n': {'active': 0, 'published': 0, 'external_network': False, 'model_calls': 0,
                               'credential_decryption_verified': True}},
            'mirror': {'state': 'ok', 'target': 'owner_mac', 'archive': 'dashboard-20261004T000000Z.tar.gz',
                       'sha256': 'd'*64, 'bytes': 99, 'files_verified': 2},
            'bundle_manifest': {'format': 'dashboard-full-backup-v1',
                                'files': {'selfhost/restore-check.json': {}, 'n8n-restore-check.json': {}}}}
        raw = run/'fixture-primary.txt'; raw.write_text('synthetic offline only')
        primary = {'path': str(raw), 'sha256': writer.digest(raw)}
        receipts['owner']['primary_receipts'] = [primary]; receipts['source']['primary_receipts'] = [primary]
        for name, receipt in receipts.items():
            path = run/(writer.RECEIPTS[name] or name+'.json')
            path.write_text(json.dumps(receipt)); refs[name] = {'path': str(path), 'sha256': writer.digest(path)}
        manifest = {'schema': writer.CONTRACT['manifest_schema'], 'problem_id': writer.PROBLEM,
                    'run_dir': remote, 'receipts': refs}
        manifest_path = run/'final-writer-prerequisites.json'; manifest_path.write_text(json.dumps(manifest))
        (run/'n8n_dashboard_pause_once.py').write_text('# fixture only, never execute')
        hashes = {ref['path']: ref['sha256'] for ref in refs.values()}
        hashes[str(raw)] = primary['sha256']; hashes[str(manifest_path)] = writer.digest(manifest_path)
        gate = {'problem_id': writer.PROBLEM, 'phase': 'TARGET_WRITER_OPEN', 'decision': 'CONTINUE_BOUNDED',
                'run_dir': remote, 'issued_at': now.isoformat(), 'expires_at': (now+dt.timedelta(minutes=5)).isoformat(),
                'dump_sha256': 'a'*64, 'source_query_sha256': 'c'*64, 'receipt_hashes': hashes,
                'script_hashes': {'final_writer_open_once.py': writer.digest(writer.__file__),
                                  'n8n_dashboard_pause_once.py': writer.digest(run/'n8n_dashboard_pause_once.py')}}
        gate_path = run/'fixture-gate.json'; gate_path.write_text(json.dumps(gate))
        return now, run, gate_path, gate

    def test_wrong_or_stale_receipt_prevents_any_mutation(self):
        """Use actual loader/execute ordering, not just predicate assertions."""
        from unittest.mock import patch
        for problem in ['wrongsha', 'stale', 'incomplete']:
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); now, run, gate_path, gate = self.fixture(root)
                original = writer.re.fullmatch
                def mapped(pattern, string, *args, **kw):
                    if pattern.startswith('/opt/dashboard-supabase-20261003/'):
                        pattern = pattern.replace('/opt/dashboard-supabase-20261003', str(root))
                    return original(pattern, string, *args, **kw)
                with patch.object(writer, 'ROOT', root), patch.object(writer.re, 'fullmatch', side_effect=mapped):
                    writer.load_and_validate(run, gate_path, now)
                if problem == 'wrongsha':
                    (run/'target-runtime-receipt.json').write_text('{}')
                elif problem == 'stale':
                    gate['expires_at'] = (now-dt.timedelta(seconds=1)).isoformat()
                    gate_path.write_text(json.dumps(gate))
                else:
                    (run/'production-owner-flow-receipt.json').unlink()
                before = {str(p): p.read_bytes() for p in run.iterdir() if p.is_file()}
                operations = Mock()
                original = writer.re.fullmatch
                with patch.object(writer, 'ROOT', root), patch.object(writer.re, 'fullmatch', wraps=original) as match:
                    # Only map the fixed production-root regex to this disposable fixture root.
                    def mapped(pattern, string, *args, **kw):
                        if pattern.startswith('/opt/dashboard-supabase-20261003/'):
                            pattern = pattern.replace('/opt/dashboard-supabase-20261003', str(root))
                        return original(pattern, string, *args, **kw)
                    match.side_effect = mapped
                    with self.assertRaises((writer.PreconditionsError, FileNotFoundError)):
                        writer.execute(run, gate_path, operations, now)
                self.assertEqual(operations.mock_calls, [])
                self.assertEqual(before, {str(p): p.read_bytes() for p in run.iterdir() if p.is_file()})
                self.assertFalse((run/'writer-open-attempt.marker').exists())

    def test_source_rollback_refuses_after_writer_open(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            marker = run/'writer-open-attempt.marker'; marker.write_text('writer started; outcome unknown')
            operations = Mock()
            with self.assertRaisesRegex(writer.PreconditionsError, 'Writer already opened'):
                rollback.execute(run, run/'nonexistent-gate.json', operations)
            self.assertEqual(operations.mock_calls, [])
            self.assertEqual(list(run.iterdir()), [marker])
            self.assertEqual(marker.read_text(), 'writer started; outcome unknown')


if __name__ == '__main__':
    unittest.main()
