import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from archive_index import connect, ingest_archive, catalogue, original, spans


class ArchiveIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = connect(self.root / 'index.sqlite')

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def archive(self, name, sources, observed='2026-07-21T12:00:00Z'):
        folder = self.root / name
        folder.mkdir()
        rows = []
        for identifier, day, title, text in sources:
            digest = hashlib.sha256(text.encode()).hexdigest()
            (folder / (digest + '.txt')).write_bytes(text.encode())
            rows.append({'source_id': identifier, 'event_date': day, 'title': title,
                         'body_sha256': digest, 'export_sha256': digest, 'body_offset_characters': 0})
        (folder / 'manifest.json').write_text(json.dumps({'sources': rows, 'inventory_files': len(rows), 'stopped_at': observed}))
        return folder

    def test_full_content_coverage_and_exact_spans(self):
        text = '01:01 Gleb: ' + 'Änderung. ' * 1500 + '\r\n99:00 Oliver: Schlusszusage.'
        folder = self.archive('a', [('drive:a', '2026-07-15', 'Finance', text)])
        self.assertEqual(ingest_archive(self.db, folder), 1)
        self.assertEqual(ingest_archive(self.db, folder), 0)
        covered = set()
        for start, end, part in spans(text):
            covered.update(range(start, end)); self.assertEqual(text[start:end], part)
        self.assertEqual(len(covered), len(text))
        result = catalogue(self.db, query='Schlusszusage', as_of='2026-07-20', known_at='2026-07-22T00:00:00Z')
        hit = result['sources'][0]
        self.assertEqual(text[hit['match']['start']:hit['match']['end']], hit['match']['text'])
        self.assertEqual(original(self.db, hit['id'])['transcript'], text)

    def test_event_and_knowledge_boundaries(self):
        ingest_archive(self.db, self.archive('a', [('drive:a', '2026-07-15', 'A', 'Umrechnungskurse früher'), ('drive:b', '2026-07-20', 'B', 'Umrechnungskurse später')]))
        self.assertEqual(catalogue(self.db, query='Umrechnungskurse', as_of='2026-07-15', known_at='2026-07-22T00:00:00Z')['total'], 1)
        self.assertEqual(catalogue(self.db, as_of='2026-07-20', known_at='2026-07-20T00:00:00Z')['total'], 0)

    def test_metadata_revision_and_identical_titles_keep_identity(self):
        ingest_archive(self.db, self.archive('a', [('drive:a', '2026-07-15', 'Gleich', 'Text A'), ('drive:b', '2026-07-15', 'Gleich', 'Text B')]))
        ingest_archive(self.db, self.archive('b', [('drive:a', '2026-07-15', 'Umbenannt', 'Text A')], '2026-07-23T00:00:00Z'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM documents').fetchone()[0], 3)
        current = catalogue(self.db, as_of='2026-07-25', known_at='2026-07-24T00:00:00Z')
        self.assertEqual(current['total'], 2)
        self.assertEqual({s['title'] for s in current['sources']}, {'Gleich', 'Umbenannt'})
        previous = catalogue(self.db, as_of='2026-07-25', known_at='2026-07-22T00:00:00Z')
        self.assertEqual({s['title'] for s in previous['sources']}, {'Gleich'})

    def test_corruption_rolls_back_whole_snapshot(self):
        folder = self.archive('a', [('drive:a', '2026-07-15', 'A', 'Text A'), ('drive:b', '2026-07-15', 'B', 'Text B')])
        (folder / (hashlib.sha256(b'Text B').hexdigest() + '.txt')).write_text('Damaged')
        with self.assertRaises(ValueError): ingest_archive(self.db, folder)
        self.assertEqual(self.db.execute('SELECT count(*) FROM documents').fetchone()[0], 0)

    def test_search_input_and_pagination_are_bounded(self):
        ingest_archive(self.db, self.archive('a', [('drive:a', '2026-07-15', 'A', 'Finanzierung'), ('drive:b', '2026-07-15', 'B', 'Finanzierung')]))
        one = catalogue(self.db, query='Finanz', limit=1)
        two = catalogue(self.db, query='Finanz', limit=1, offset=1)
        self.assertEqual(one['total'], 2); self.assertNotEqual(one['sources'][0]['id'], two['sources'][0]['id'])
        self.assertEqual(catalogue(self.db, query='" OR NichtVorhanden*')['total'], 0)
        self.assertEqual([row['title'] for row in catalogue(self.db, query='Finanz', order='title')['sources']], ['A', 'B'])
        with self.assertRaises(ValueError): catalogue(self.db, order='unsupported')
        with self.assertRaises(ValueError): catalogue(self.db, limit=101)
        with self.assertRaises(ValueError): catalogue(self.db, known_at='2026-07-20T00:00:00')
        self.assertIsNone(original(self.db, '../manifest.json'))


if __name__ == '__main__': unittest.main()
