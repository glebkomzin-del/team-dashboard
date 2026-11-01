"""The isolated image plan must include exact source migration 48."""
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

CANDIDATE=Path('/private/tmp/dashboard-sol-operational-20261006/candidate')
AUTHORITY=Path('/Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Dashboard Job/supabase/migrations/20261006103000_isolate_processing_job_failures.sql')
sys.path.insert(0,str(CANDIDATE))
import restore_schema

class RestoreBindingTest(unittest.TestCase):
    def test_exact_48_and_authority(self):
        paths=restore_schema.migration_paths(CANDIDATE/'schema')
        self.assertEqual(len(paths),48)
        self.assertEqual(paths[-1].name,restore_schema.JOB_ISOLATION)
        self.assertEqual(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),restore_schema.JOB_ISOLATION_SHA256)
        self.assertEqual(AUTHORITY.read_bytes(),paths[-1].read_bytes())
    def test_missing_or_changed_last_migration_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for path in (CANDIDATE/'schema').glob('*.sql'):
                shutil.copyfile(path,directory/path.name)
            target=directory/restore_schema.JOB_ISOLATION
            target.unlink()
            with self.assertRaisesRegex(ValueError,'Required RC2 migration is missing'):
                restore_schema.migration_paths(directory)
            shutil.copyfile(AUTHORITY,target)
            target.write_bytes(target.read_bytes()+b'\n-- changed')
            with self.assertRaisesRegex(ValueError,'Required job-isolation migration changed'):
                restore_schema.migration_paths(directory)

if __name__=='__main__':unittest.main()
