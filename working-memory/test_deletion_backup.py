import tempfile
import unittest
from pathlib import Path

from deletion_backup import persist_restore_barrier
from deletion_ledger import read, write
from memory import ValidationError


class Store:
    def __init__(self):
        self.revision = 2
        self.rows = [{'deletion_id': 'deletion-a', 'source_id': 'source-a', 'state': 'purging'}]
        self.drift = False

    def space(self):
        return {'id': 'space-a', 'owner_id': 'owner-a', 'deletion_revision': self.revision}

    def call(self, op, **kwargs):
        assert op == 'source_deletion_ledger' and kwargs == {'actor_id': 'owner-a'}
        if self.drift:
            self.revision += 1
        return self.rows


class RestoreBarrierTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'external' / 'ledger.json'
        self.store = Store()
        self.owner = {'role': 'owner', 'id': 'owner-a'}

    def test_durable_receipt_contains_current_watermark(self):
        receipt = persist_restore_barrier(self.store, self.owner, self.path)
        self.assertEqual(receipt['minimum_deletion_revision'], 2)
        self.assertTrue(receipt['restore_ledger_persisted'])
        self.assertEqual(read(self.path, space_id='space-a')['deletions'], self.store.rows)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_old_database_cannot_overwrite_independent_newer_barrier(self):
        write(self.path, space_id='space-a', minimum_deletion_revision=3,
              deletions=self.store.rows, observed_at='2026-09-19T00:00:00+00:00')
        with self.assertRaises(ValidationError):
            persist_restore_barrier(self.store, self.owner, self.path)
        self.assertEqual(read(self.path, space_id='space-a')['minimum_deletion_revision'], 3)

    def test_changing_ledger_never_attests_an_unstable_snapshot(self):
        self.store.drift = True
        with self.assertRaises(ValidationError):
            persist_restore_barrier(self.store, self.owner, self.path)
        self.assertFalse(self.path.exists())

    def test_missing_path_and_wrong_owner_fail_closed(self):
        with self.assertRaises(ValidationError):
            persist_restore_barrier(self.store, self.owner, '')
        with self.assertRaises(PermissionError):
            persist_restore_barrier(self.store, {'role': 'owner', 'id': 'other'}, self.path)


if __name__ == '__main__':
    unittest.main()
