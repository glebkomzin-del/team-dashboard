import tempfile
from pathlib import Path
import unittest
from memory import connect, register, claim, apply
from review_api import review
from test_memory import TEXT, observation, proposal


class ReviewCoverageTests(unittest.TestCase):
    def test_queued_original_does_not_inflate_processed_source_count(self):
        with tempfile.TemporaryDirectory() as directory:
            db = connect(Path(directory) / 'memory.sqlite')
            first = register(db, source_id='drive:processed', event_date='2026-07-15', title='Processed', transcript=TEXT)
            register(db, source_id='drive:queued', event_date='2026-07-15', title='Queued', transcript='Noch nicht ausgewertet.')
            apply(db, first, claim(db, first), proposal(observation()), model='fixture')
            result = review(db, '2026-07-15')
            self.assertEqual([s['source_id'] for s in result['sources']], ['drive:processed'])
            self.assertEqual(len(result['jobs']), 2)
            self.assertEqual(result['dates'], ['2026-07-15'])
            db.close()


if __name__ == '__main__':
    unittest.main()
