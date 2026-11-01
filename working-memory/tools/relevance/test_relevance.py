"""Synthetic, content-free checks for the offline relevance projection."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('relevance', HERE / 'relevance.py')
relevance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relevance)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.config = relevance.load_config()
        self.context = {'config': self.config, 'as_of': '2026-10-13', 'topics': {}}

    def test_missing_evidence_is_neutral_and_status_does_not_change_score(self):
        task = {'id': 'x', 'claim': 'Eine Aufgabe', 'status': 'open'}
        first = relevance.score(task, self.context)
        self.assertEqual(first['features']['explicit_commitment'], 0)
        self.assertEqual(first['features']['due_present'], 0)
        self.assertEqual(first['klasse'], 'kleinigkeit')
        self.assertEqual(relevance.score({**task, 'status': 'done'}, self.context), first)

    def test_due_date_requires_unambiguous_date_for_proximity(self):
        task = {'due_text': 'nächste Woche', 'claim': 'Eine Aufgabe'}
        features = relevance.extract_features(task, self.context)
        self.assertEqual(features['due_present'], 1)
        self.assertEqual(features['due_soon'], 0)
        self.assertEqual(features['due_overdue'], 0)
        dated = relevance.extract_features({**task, 'due_date': '2026-10-15'}, self.context)
        self.assertEqual(dated['due_soon'], 1)

    def test_meeting_count_uses_distinct_source_identity_and_caps_events(self):
        task = {'claim': 'Dokument erstellen', 'history': [
            {'source_id': 'same', 'action': 'created'}, {'source_id': 'same', 'action': 'progress'},
            {'source_id': 'other', 'action': 'progress'}, {'source_id': 'other', 'action': 'progress'}]}
        features = relevance.extract_features(task, self.context)
        self.assertEqual(features['meeting_count'], 2)
        self.assertEqual(features['event_count'], 3)

    def test_classification_thresholds(self):
        low = self.config['thresholds']['standard']
        high = self.config['thresholds']['wichtig']
        self.assertEqual(relevance.classify(low - 0.0001, self.config), 'kleinigkeit')
        self.assertEqual(relevance.classify(low, self.config), 'standard')
        self.assertEqual(relevance.classify(high - 0.0001, self.config), 'standard')
        self.assertEqual(relevance.classify(high, self.config), 'wichtig')

    def test_commitment_strength_requires_positive_evidence(self):
        bare = relevance.extract_features({'kind': 'commitment', 'claim': 'Eine Aufgabe'}, self.context)
        self.assertEqual(bare['explicit_commitment'], 0)
        self.assertEqual(bare['clear_promise'], 0)
        explicit = relevance.extract_features({'kind': 'commitment', 'commitment_strength': 'explicit',
                                               'claim': 'Eine Aufgabe'}, self.context)
        self.assertEqual(explicit['explicit_commitment'], 1)
        self.assertEqual(explicit['clear_promise'], 1)

    def test_people_topic_and_claim_detail_use_bounded_explicit_evidence(self):
        context = {**self.context, 'topics': {'m': {'active_count': 7, 'last_date': '2026-10-12'}}}
        task = {'matter_id': 'm', 'owner': 'Person A', 'participants': ['Person B', 'Person A'],
                'history': [{'owner': 'Person C'}], 'claim': 'Modell 3 messen und Freigabe erstellen'}
        features = relevance.extract_features(task, context)
        self.assertEqual(features['topic_active'], 3)
        self.assertEqual(features['person_evidence'], 3)
        self.assertEqual(features['artifact_detail'], 1)
        self.assertGreater(features['claim_length'], 0)


class ArchiveTests(unittest.TestCase):
    def test_direct_and_wrapped_journal_formats(self):
        direct = {'kind': 'human', 'command_id': 'synthetic'}
        self.assertEqual(relevance._journal_entry(direct), direct)
        self.assertEqual(relevance._journal_entry({'kind': 'human', 'record_json': json.dumps(direct)}), direct)

    def test_streams_exact_member_and_rejects_missing(self):
        archive = HERE / '.test-relevance-archive.tar.gz'
        try:
            with tarfile.open(archive, 'w:gz') as tar:
                payload = b'{"kind":"source"}\n'
                info = tarfile.TarInfo('canonical/journal.jsonl'); info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            self.assertEqual(list(relevance._member_rows(archive, 'journal.jsonl')), [{'kind': 'source'}])
            with self.assertRaises(ValueError):
                list(relevance._member_rows(archive, 'notes.jsonl'))
        finally:
            archive.unlink(missing_ok=True)

    def test_output_boundary_rejects_traversal_and_symlink(self):
        with self.assertRaises(ValueError):
            relevance._output_path('../escape.jsonl')
        alias = HERE / '.test-relevance-link'
        try:
            alias.symlink_to(HERE / 'config.json')
            with self.assertRaises(ValueError):
                relevance._output_path(alias.name)
        finally:
            alias.unlink(missing_ok=True)

    def test_task_candidate_separation_preserves_rejected(self):
        state = {'personal': [{'id': 'work', 'title': 'Task', 'claim': 'Bericht erstellen', 'status': 'open'}],
                 'waiting_dependencies': [], 'waiting': [], 'completed': [], 'cancelled': [],
                 'knowledge': [{'id': 'candidate', 'event_date': '2026-10-01', 'data':
                                {'kind': 'commitment', 'title': 'Proposal', 'claim': 'Dokument senden',
                                 'knowledge_status': 'rejected'}},
                               {'id': 'fact', 'data': {'kind': 'fact', 'title': 'Fact', 'claim': 'A fact'}}],
                 'human_decisions': []}
        archive = HERE / '.test-relevance-source.tar.gz'
        out = '.test-relevance-out.jsonl'; report = '.test-relevance-report.md'
        try:
            archive.write_bytes(b'synthetic')
            with patch.object(relevance, '_project', return_value=(state, {'source': 1}, {})):
                result = relevance.run(str(archive), out, report)
            rows = [json.loads(line) for line in (HERE / out).read_text().splitlines()]
            self.assertEqual(result['tasks'], 1)
            self.assertEqual(result['candidates'], 1)
            self.assertTrue(all('title' not in row for row in rows))
            self.assertEqual({row['id'] for row in rows}, {'work', 'candidate'})
            self.assertEqual(next(row for row in rows if row['id'] == 'candidate')['status'], 'rejected')
            self.assertNotIn('Proposal', (HERE / report).read_text())
        finally:
            archive.unlink(missing_ok=True)
            (HERE / out).unlink(missing_ok=True)
            (HERE / report).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
