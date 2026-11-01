import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import archive_index
import backfill
from call_budget import CallBudget, BudgetExceeded


class BackfillTests(unittest.TestCase):
    def test_all_sources_queued_without_calls_and_changed_generation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = archive_index.connect(root / 'archive.sqlite')
            for identifier, day in [('second', '2026-07-20'), ('first', '2026-07-15')]:
                body = 'Original ' + identifier
                digest = hashlib.sha256(body.encode()).hexdigest()
                archive.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',
                                (identifier, 'drive:' + identifier, day, '2026-08-01T00:00:00+00:00',
                                 'Identical title', digest, digest, body, body, '{}'))
            archive.commit()
            with patch.object(backfill.processor, 'pipeline_version', return_value='frozen-v1'), patch.object(backfill.processor, 'anthropic') as api:
                db, meetings, summary = backfill.prepare(root / 'archive.sqlite', root / 'generation.sqlite', 'fixture')
                self.assertEqual([m['source_id'] for m in meetings], ['drive:first', 'drive:second'])
                self.assertEqual(summary['jobs'], {'queued': 2})
                self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
                db.close()
                db, repeated, _ = backfill.prepare(root / 'archive.sqlite', root / 'generation.sqlite', 'fixture')
                self.assertEqual([m['job_id'] for m in meetings], [m['job_id'] for m in repeated])
                db.close()
                api.assert_not_called()
            with patch.object(backfill.processor, 'pipeline_version', return_value='changed-v2'):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    backfill.prepare(root / 'archive.sqlite', root / 'generation.sqlite', 'fixture')
            archive.close()

    def test_budget_survives_restart_and_unknown_usage_never_becomes_free(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'budget.sqlite'
            budget = CallBudget(path, 1)
            api = Mock(return_value={'stop_reason': None, 'error': 'TimeoutError'})
            budget.wrap(api, {})('Text', 'claude-opus-5')
            spent = budget.total()
            self.assertGreater(spent, .6)
            budget.close()
            budget = CallBudget(path, 1)
            self.assertEqual(budget.total(), spent)
            with self.assertRaises(BudgetExceeded):
                budget.wrap(api, {})('Text', 'claude-opus-5')
            self.assertEqual(api.call_count, 1)
            budget.close()

    def test_known_usage_releases_unused_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = CallBudget(Path(directory) / 'budget.sqlite', 1)
            api = Mock(return_value={'usage_final': True, 'usage': {'input_tokens': 100, 'output_tokens': 100}})
            wrapped = budget.wrap(api, {})
            wrapped('Text', 'claude-opus-5')
            wrapped('Text', 'claude-opus-5')
            self.assertAlmostEqual(budget.total(), .006)
            budget.close()


if __name__ == '__main__':
    unittest.main()
