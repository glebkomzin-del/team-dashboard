"""Question: can missing/wrong replay code or archive pair pass recovery?
Required: exact wrapper+SQL+954e archive source, two original tables in same
snapshot SQL. Scope: local positive/negative contracts, no DB/backup execution.
Pass permits read-only independent review; failure blocks start/handoff.
"""
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('recovery', ROOT / 'restore_enriched.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class ReplayContract(unittest.TestCase):
    def dependencies(self, folder):
        for name in ('full_backup_once.py', 'enriched-fingerprint.sql'):
            shutil.copyfile(ROOT / name, folder / name)

    def test_exact_dependencies_and_two_original_tables(self):
        wrapper = recovery.load_wrapper(ROOT)
        self.assertEqual(len(wrapper.TABLES), 16)
        for name in ('wm_archive_documents', 'wm_archive_notes'):
            self.assertIn(name, wrapper.TABLES)
            self.assertIn('from public.' + name + ' t', (ROOT / 'enriched-fingerprint.sql').read_text())
        self.assertIn('to_jsonb(t)::text', (ROOT / 'enriched-fingerprint.sql').read_text())

    def test_missing_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.dependencies(folder)
            (folder / 'full_backup_once.py').unlink()
            with self.assertRaises(ValueError):
                recovery.load_wrapper(folder)

    def test_changed_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.dependencies(folder)
            with (folder / 'full_backup_once.py').open('a') as stream:
                stream.write('\n# Wrong replay code\n')
            with self.assertRaises(ValueError):
                recovery.load_wrapper(folder)

    def test_missing_or_changed_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.dependencies(folder)
            (folder / 'enriched-fingerprint.sql').unlink()
            with self.assertRaises(ValueError):
                recovery.load_wrapper(folder)
            (folder / 'enriched-fingerprint.sql').write_text('SELECT 1;')
            with self.assertRaises(ValueError):
                recovery.load_wrapper(folder)

    def test_exact_archive_pair_and_missing_or_wrong_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            archives = {'full_backup': folder / 'full.tar.gz', 'supplement': folder / 'supplement.tar.gz'}
            pair = {'format': 'dashboard-final-backup-pair-v1'}
            for key, path in archives.items():
                path.write_bytes(key.encode())
                pair[key] = {'archive': path.name, 'sha256': recovery.digest(path), 'bytes': path.stat().st_size}
            receipt = folder / 'pair.json'
            receipt.write_text(json.dumps(pair))
            self.assertEqual(recovery.validate_pair(receipt, *archives.values()), pair)
            pair['supplement']['sha256'] = '0' * 64
            receipt.write_text(json.dumps(pair))
            with self.assertRaises(ValueError):
                recovery.validate_pair(receipt, *archives.values())
            receipt.write_text('{}')
            with self.assertRaises(ValueError):
                recovery.validate_pair(receipt, *archives.values())

    def test_reconstructed_sql_from_exact_original(self):
        archive_source = Path('/private/tmp/dashboard-sol-parent-release-20261006/package/scheduled_backup.py')
        self.assertEqual(recovery.digest(archive_source), recovery.INSTALLED_SHA)
        baseline = next(ast.literal_eval(node.value) for node in ast.parse(archive_source.read_text()).body
                        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SELFHOST_FINGERPRINT_SQL' for t in node.targets))
        wrapper = recovery.load_wrapper(ROOT)
        self.assertEqual(wrapper.enriched_sql(baseline), (ROOT / 'enriched-fingerprint.sql').read_text())


if __name__ == '__main__':
    unittest.main()
