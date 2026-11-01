import tempfile,sqlite3,unittest
from pathlib import Path
from readonly_snapshot import create
class ReadOnlySnapshotTests(unittest.TestCase):
    def test_live_wal_snapshot_has_committed_rows_without_sidecars(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);db=sqlite3.connect(root/'live.sqlite');db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE test(value)');db.execute('INSERT INTO test VALUES (42)');db.commit()
            result=create(root/'live.sqlite',root/'snapshot.sqlite');self.assertEqual(result['journal_mode'],'delete')
            copy=sqlite3.connect((root/'snapshot.sqlite').as_uri()+'?mode=ro',uri=True)
            self.assertEqual(copy.execute('SELECT value FROM test').fetchone()[0],42);copy.close()
            self.assertFalse((root/'snapshot.sqlite-wal').exists());self.assertFalse((root/'snapshot.sqlite-shm').exists());db.close()
if __name__=='__main__':unittest.main()
