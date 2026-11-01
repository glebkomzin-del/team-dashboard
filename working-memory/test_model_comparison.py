import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_model_comparison as comparison


class ModelComparisonTests(unittest.TestCase):
    def test_preflight_is_offline_and_has_nonvacuous_gold_cases(self):
        with patch.object(comparison, 'request', side_effect=AssertionError('network')):
            result = comparison.preflight()
        self.assertEqual(result['pipeline_cases'], 12)
        self.assertEqual(result['qa_cases'], 20)
        self.assertEqual(result['long_transcripts_checked_at_prompt'], [])
        self.assertEqual(len(comparison.cases()[1]), 20)

    def test_manifest_requires_pinned_input_and_expectations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source.txt').write_text('Gleb: Test.')
            manifest = root / 'cases.json'
            manifest.write_text(json.dumps([{'id': 'real', 'transcript_file': 'source.txt',
                                             'sha256': '0' * 64, 'tasks': None, 'done': None,
                                             'meeting_date': '2026-06-16', 'observed_at': '2026-06-16T12:00:00Z',
                                             'gold_review': [{'quote': 'Gleb: Test.', 'expected': {
                                                 'owner': 'Gleb', 'status': 'open', 'condition_text': None}}]}]))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                comparison.preflight(manifest)

    def test_long_manifest_is_deferred_to_actual_compact_prompt_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = 'x' * 220001
            (root / 'source.txt').write_text(body)
            manifest = root / 'cases.json'
            manifest.write_text(json.dumps([{'id': 'real', 'transcript_file': 'source.txt',
                                             'sha256': hashlib.sha256(body.encode()).hexdigest(),
                                             'meeting_date': '2026-06-16', 'observed_at': '2026-06-16T12:00:00Z',
                                             'tasks': None, 'done': None,
                                             'gold_review': [{'quote': 'xxx', 'expected': {
                                                 'owner': None, 'status': None, 'condition_text': None}}]}]))
            with patch.object(comparison, 'request', side_effect=AssertionError('network')):
                self.assertEqual(comparison.preflight(manifest)['long_transcripts_checked_at_prompt'][0]['id'], 'real')

    def test_real_manifest_rejects_unquoted_gold_and_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body, prior = 'Gleb: Heute nichts Neues.\r\nJan: Genau.', 'Gleb: Ich kläre das mit der IT.\r\nJan: Gut.'
            (root / 'current.txt').write_bytes(body.encode())
            (root / 'prior.txt').write_bytes(prior.encode())
            item = {'id': 'real', 'transcript_file': 'current.txt',
                    'sha256': hashlib.sha256(body.encode()).hexdigest(), 'tasks': None, 'done': None,
                    'meeting_date': '2026-06-16', 'observed_at': '2026-06-16T12:00:00Z',
                    'gold_review': [{'quote': 'Gleb: Heute nichts Neues.', 'expected': {
                        'owner': 'Gleb', 'status': 'open', 'condition_text': None}}],
                    'prior_transcript_file': 'prior.txt', 'prior_sha256': hashlib.sha256(prior.encode()).hexdigest(),
                    'real_seed': [{'source_quote': prior, 'prior_date': '2026-06-09', 'matter': 'IT',
                                   'title': 'IT klären', 'claim': prior, 'owner': 'Gleb', 'quotes': [prior]}]}
            manifest = root / 'cases.json'
            manifest.write_text(json.dumps([item]))
            case = comparison.cases(manifest)[0][-1]
            with patch.object(comparison, 'request', side_effect=AssertionError('network')):
                self.assertEqual(comparison.preflight(manifest)['pipeline_cases'], 13)
            from memory import connect, overview
            db = connect(root / 'seed.sqlite')
            try:
                comparison.seed_real(db, case)
                seeded = comparison.work_rows(overview(db, '2026-06-16'))
                self.assertEqual([(r['matter'], r['owner'], r['status']) for r in seeded.values()],
                                 [('IT', 'Gleb', 'open')])
                checks = comparison.check_pipeline(case, overview(db, '2026-06-16'), overview(db, '2026-06-16'),
                                                   {'status': 'applied', 'observations': 1, 'new_work': 0}, 1)
                self.assertNotIn('new_tasks', checks)
                self.assertNotIn('seed_status', checks)
                self.assertTrue(checks['seed_identity'])
            finally:
                db.close()
            item['gold_review'][0]['quote'] = 'not in transcript'
            manifest.write_text(json.dumps([item]))
            with self.assertRaisesRegex(ValueError, 'gold_review'):
                comparison.cases(manifest)
            item['gold_review'][0]['quote'] = body
            item['real_seed'][0]['quotes'] = ['invented prior quote']
            manifest.write_text(json.dumps([item]))
            with self.assertRaisesRegex(ValueError, 'Real seed'):
                comparison.cases(manifest)

    def test_pipeline_checks_do_not_pass_empty_or_wrong_counts(self):
        state = {'personal': [], 'waiting': [], 'waiting_dependencies': [], 'completed': []}
        checks = comparison.check_pipeline({'id': 'clear_promise', 'tasks': 1, 'done': 0}, state)
        self.assertFalse(all(checks.values()))

    def test_seeded_identity_and_waiting_status_are_required(self):
        original = {'id': 'original', 'title': 'Daten migrieren', 'owner': 'Gleb',
                    'status': 'waiting', 'condition_text': 'Maria und Tom'}
        before = {'personal': [], 'waiting': [], 'waiting_dependencies': [original], 'completed': []}
        after = {'personal': [{**original, 'id': 'replacement', 'status': 'open'}],
                 'waiting': [], 'waiting_dependencies': [], 'completed': []}
        case = {'id': 'partial_condition', 'tasks': 0, 'done': 0, 'seed': [('Daten migrieren', 'source')]}
        checks = comparison.check_pipeline(case, after, before)
        self.assertFalse(checks['seed_identity'])
        self.assertFalse(checks['seed_status'])
        self.assertFalse(all(checks.values()))

    def test_empty_observations_fail_even_when_counters_match(self):
        state = {'personal': [], 'waiting': [], 'waiting_dependencies': [], 'completed': []}
        checks = comparison.check_pipeline({'id': 'fact_no_action', 'tasks': 0, 'done': 0}, state, state,
                                           {'status': 'applied', 'observations': 0, 'new_work': 0}, 0)
        self.assertFalse(checks['observations'])

    def test_structured_qa_uses_actual_service_without_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(comparison, 'PRIVATE', root), patch.object(comparison, 'request', side_effect=AssertionError('network')):
                result = comparison.qa_case(comparison.cases()[1][0], 'gpt-5.6-terra', root / 'budget.sqlite',
                                            10_000_000, root)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['incremental_micro_usd'], 0)

    def test_successful_pipeline_result_is_reported_from_local_sqlite(self):
        from memory import register
        def process(db, meeting, model, **kwargs):
            job = register(db, source_id=meeting['source_id'], event_date=meeting['meeting_date'],
                           title=meeting['title'], transcript=meeting['raw_transcript'])
            source = db.execute('SELECT source_version FROM jobs WHERE id=?', (job,)).fetchone()[0]
            db.execute("UPDATE jobs SET status='applied' WHERE id=?", (job,))
            db.execute("INSERT INTO matters VALUES ('m','Fact')")
            db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?)',
                       ('o', job, source, 'm', meeting['meeting_date'], 'fact', '{}'))
            return {'job': job, 'status': 'applied', 'observations': 1, 'new_work': 0,
                    'hybrid': {'repairs': 0}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(comparison, 'PRIVATE', root), patch.object(comparison, 'process',
                side_effect=process) as invoked:
                result = comparison.pipeline_case(comparison.cases()[0][1], 'gpt-5.6-terra', None,
                                                  root / 'budget.sqlite', 10_000_000, root)
                real = {'id': 'real-example', 'title': 'Originaltitel', 'text': 'Original',
                        'difficulty': 'real', 'tasks': None, 'done': None,
                        'gold_review': [{'quote': 'Original', 'expected': {
                            'owner': None, 'status': None, 'condition_text': None}}]}
                real_result = comparison.pipeline_case(real, 'gpt-5.6-terra', None,
                                                       root / 'budget.sqlite', 10_000_000, root)
                saved = json.loads((root / 'real-example.json').read_text())
        self.assertTrue(result['passed'], result)
        self.assertFalse(real_result['passed'])
        self.assertTrue(real_result['manual_semantic_review_required'])
        self.assertTrue(all(real_result['checks'].values()))
        self.assertNotIn('new_tasks', real_result['checks'])
        self.assertEqual(saved['observations'][0]['data'], {})
        self.assertEqual(saved['before_state']['personal'], [])
        self.assertEqual(result['repairs'], 0)
        self.assertEqual(result['review_count'], 0)
        self.assertTrue(invoked.call_args.kwargs['compact'])
        self.assertEqual(invoked.call_args.args[1]['title'], 'Originaltitel')

    def test_failed_case_keeps_paid_call_cost_and_marks_stop(self):
        def provider(*_args, **_kwargs):
            return {'stop_reason': 'end_turn', 'usage_final': True,
                    'usage': {'input_tokens': 100, 'output_tokens': 10,
                              'input_tokens_details': {}}, 'elapsed_seconds': 1.5,
                    'content': [{'type': 'text', 'text': '{}'}]}
        def process(_db, _meeting, model, *, api, **_kwargs):
            api('known prompt', model, schema={'type': 'object'})
            raise ValueError('controlled semantic failure')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(comparison, 'PRIVATE', root), patch.object(comparison, 'process', side_effect=process), \
                 patch.object(comparison, 'request', side_effect=provider), \
                 patch.object(comparison, 'count_input_tokens', return_value=100):
                with self.assertRaisesRegex(ValueError, 'controlled semantic failure') as raised:
                    comparison.pipeline_case(comparison.cases()[0][1], 'gpt-5.6-terra', None,
                                             root / 'budget.sqlite', 10_000_000, root)
            failed = raised.exception.comparison_result
            self.assertFalse(failed['passed'])
            self.assertEqual(failed['fresh_call_count'], 1)
            self.assertGreater(failed['incremental_micro_usd'], 0)
            self.assertGreater(failed['used_micro_usd']['gpt-5.6-terra'], 0)
            self.assertEqual(failed['provider_elapsed_seconds'], 1.5)

    def test_exact_ledger_replay_is_counted_separately_from_fresh_calls(self):
        from evaluation_budget import EvaluationCalls
        from test_qa_service import Store
        sent = []
        def provider(*_args, **_kwargs):
            sent.append(1)
            return {'stop_reason': 'end_turn', 'usage_final': True,
                    'usage': {'input_tokens': 100, 'output_tokens': 10,
                              'input_tokens_details': {}}, 'elapsed_seconds': 2.25,
                    'content': [{'type': 'text', 'text': '{}'}]}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / 'budget.sqlite'
            first = EvaluationCalls(ledger, Store(), provider, {'type': 'object'}, {'case': 'one'})
            first('same request', 'gpt-5.6-terra')
            self.assertEqual(comparison.call_metrics(first, set())['fresh_call_count'], 1)
            first.close()
            second = EvaluationCalls(ledger, Store(), provider, {'type': 'object'}, {'case': 'one'})
            before = {row[0] for row in second.db.execute('SELECT hash FROM calls')}
            second('same request', 'gpt-5.6-terra')
            metrics = comparison.call_metrics(second, before)
            second.close()
        self.assertEqual(sent, [1])
        self.assertEqual(metrics['fresh_call_count'], 0)
        self.assertEqual(metrics['reused_call_count'], 1)
        self.assertEqual(metrics['provider_elapsed_seconds'], 2.25)

    def test_repeat_partitions_identical_request_without_changing_default_scope(self):
        from evaluation_budget import EvaluationCalls
        from test_qa_service import Store
        self.assertEqual(comparison.comparison_scope('case', 'same_topic_different_action'),
                         {'comparison': '20260924', 'case': 'same_topic_different_action'})
        self.assertEqual(comparison.comparison_scope('qa', 'q09'),
                         {'comparison': '20260924', 'qa': 'q09'})
        sent = []
        def provider(*_args, **_kwargs):
            sent.append(1)
            return {'stop_reason': 'end_turn', 'usage_final': True,
                    'usage': {'input_tokens': 10, 'output_tokens': 1,
                              'input_tokens_details': {}},
                    'content': [{'type': 'text', 'text': '{}'}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'budget.sqlite'
            for repeat, fresh in zip((0, 0, 1, 1, 2), (1, 0, 1, 0, 1)):
                calls = EvaluationCalls(path, Store(), provider, {'type': 'object'},
                                        comparison.comparison_scope('case', 'same_topic_different_action', repeat))
                try:
                    before = {row[0] for row in calls.db.execute('SELECT hash FROM calls')}
                    calls('same prompt', 'gpt-5.6-terra')
                    metrics = comparison.call_metrics(calls, before)
                    self.assertEqual(metrics['fresh_call_count'], fresh)
                    self.assertEqual(metrics['reused_call_count'], 1 - fresh)
                finally:
                    calls.close()
        self.assertEqual(len(sent), 3)

    def test_repeat_is_limited_to_selected_cases(self):
        with self.assertRaisesRegex(ValueError, 'selected hard cases'):
            comparison.run('terra', 'screening', case_id='clear_promise', repeat=1)
        with self.assertRaisesRegex(ValueError, '0, 1 or 2'):
            comparison.run('terra', 'screening', case_id='same_topic_different_action', repeat=3)


if __name__ == '__main__':
    unittest.main()
