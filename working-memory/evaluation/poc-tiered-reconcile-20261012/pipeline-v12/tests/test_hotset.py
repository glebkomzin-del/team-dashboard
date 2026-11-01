"""Synthetic filter and pipeline contract tests; no real meeting inputs."""
import copy
from contextlib import ExitStack
from datetime import date, datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compact_reconcile
import hybrid_pipeline as pipeline
from candidate_filter import filter_work
from durable_calls import DurableCalls
from memory import ValidationError, connect
from test_durable_calls import Store
from test_memory import observation

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parents[1] / 'sol-operational-release-20261006/backend/hybrid_pipeline.py'
DAY = '2026-10-12'
OBS = {'title': 'Synthetic title', 'subject': 'Synthetic subject', 'search_keywords': ['keyword']}
QUERY = 'Synthetic title Synthetic subject keyword'


def task(identifier, changed='2026-01-01', **fields):
    return {'id': identifier, 'last_changed': changed, 'claim': 'Synthetic task', **fields}


def hit(identifier, **fields):
    return {'id': 'hit-'+identifier, 'target_id': identifier, 'kind': 'work', 'metadata': {}, **fields}


def ids(items):
    return [item['id'] for item in items]


class FilterTests(unittest.TestCase):
    def check_case(self, work, expected, *, observations=(), hits=None, exact=(), **options):
        before = copy.deepcopy((work, hits, observations, exact))
        kept, dropped, stats = filter_work(work, hits or {}, observations, DAY, exact, **options)
        self.assertEqual(ids(kept), expected)
        self.assertEqual(stats['n_in'], len(work))
        self.assertEqual(stats['n_kept'] + stats['n_dropped'], len(work))
        self.assertEqual(ids(dropped), [w['id'] for w in work if w['id'] not in expected])
        self.assertEqual((work, hits, observations, exact), before)
        return stats

    def test_age_alone(self):
        stats = self.check_case([task('fresh', '2026-10-11'), task('old')], ['fresh'])
        self.assertEqual((stats['age'], stats['rank'], stats['exact']), (1, 0, 0))

    def test_age_boundary_inclusive(self):
        self.check_case([task('boundary', '2026-09-12'), task('outside', '2026-09-11')], ['boundary'])

    def test_25_day_lifecycle_at_rank_12_is_kept_at_30_but_dropped_at_21(self):
        # Synthetic reproduction of selector/RANK-VALIDATION.md, W349:
        # age 25, original zero-based Work rank 12, no exact mention.
        work = [task('lifecycle', '2026-09-17')]
        self.assertEqual((date.fromisoformat(DAY) - date.fromisoformat(work[0]['last_changed'])).days, 25)
        hits = {QUERY: [hit('other-'+str(i)) for i in range(12)] + [hit('lifecycle')]}
        self.assertEqual(hits[QUERY][12]['target_id'], 'lifecycle')
        for age, expected in ((30, ['lifecycle']), (21, [])):
            with self.subTest(age_days_max=age):
                stats = self.check_case(work, expected, observations=[OBS], hits=hits,
                                        exact=(), age_days_max=age, rank_max=5)
                self.assertEqual((stats['age'], stats['rank'], stats['exact']), (int(age == 30), 0, 0))
        defaults = self.check_case(work, ['lifecycle'], observations=[OBS], hits=hits, exact=())
        self.assertEqual((defaults['age_days_max'], defaults['rank_max']), (30, 5))

    def test_missing_and_invalid_last_changed_are_kept(self):
        work = [{'id': 'missing'}] + [task(str(i), value) for i, value in enumerate(
            (None, '', 'invalid', '2026-02-30', '2026-01-01 garbage', 7))]
        self.check_case(work, ids(work))

    def test_invalid_meeting_date_conservatively_keeps_all(self):
        for day in (None, 'bad', '2026-02-30'):
            with self.subTest(day=day):
                kept, dropped, stats = filter_work([task('old')], {}, [], day, set())
                self.assertEqual(ids(kept), ['old']); self.assertFalse(dropped)
                self.assertEqual(stats['age'], 1)

    def test_iso_timestamp_date_objects_and_future_dates(self):
        self.check_case([task('timestamp', '2026-10-01T23:59:00Z'), task('date', date(2026, 10, 1)),
                         task('datetime', datetime(2026, 10, 1)), task('future', '2027-01-01')],
                        ['timestamp', 'date', 'datetime', 'future'])

    def test_rank_alone_and_exclusive_boundary(self):
        work = [task(str(i)) for i in range(6)]
        stats = self.check_case(work, ['0', '1', '2', '3', '4'], observations=[OBS],
                                hits={QUERY: [hit(str(i)) for i in range(6)]})
        self.assertEqual((stats['age'], stats['rank'], stats['exact']), (0, 5, 0))

    def test_rank_is_zero_based_and_uses_target_id(self):
        self.check_case([task('a'), task('b')], ['b'], observations=[OBS],
                        hits={QUERY: [hit('b'), hit('a')]}, rank_max=1)

    def test_only_observation_queries_qualify(self):
        self.check_case([task('a')], [], observations=[OBS], hits={'broad topic': [hit('a')]})

    def test_any_observation_qualifies(self):
        other = {'title': 'Other'}
        self.check_case([task('a')], ['a'], observations=[OBS, other], hits={'Other ': [hit('a')]})

    def test_empty_observations_do_not_grant_rank(self):
        self.check_case([task('a')], [], hits={QUERY: [hit('a')]})

    def test_exact_alone(self):
        stats = self.check_case([task('a'), task('b')], ['b'], exact={'b'})
        self.assertEqual((stats['age'], stats['rank'], stats['exact']), (0, 0, 1))

    def test_done_is_subject_to_same_rules(self):
        self.check_case([task('done', '2026-10-01', status='done'), task('old-done', status='done')], ['done'])

    def test_duplicate_hits_and_queries_count_reason_once_per_row(self):
        stats = self.check_case([task('a'), task('b')], ['a'], observations=[OBS, OBS],
                                hits={QUERY: [hit('a'), hit('a'), hit('b')]}, rank_max=2)
        self.assertEqual(stats['rank'], 1)

    def test_mapping_and_nonwork_hits_preserve_work_rank(self):
        hits = {'passage': hit('not-work', kind='passage'), 'z': hit('b'), 'a': hit('a')}
        self.check_case([task('a'), task('b')], ['b'], observations=[OBS], hits={QUERY: hits}, rank_max=1)

    def test_order_identity_and_overlapping_counts(self):
        work = [task('b', '2026-10-01'), task('drop'), task('a')]
        kept, dropped, stats = filter_work(work, {QUERY: [hit('b'), hit('a')]}, [OBS], DAY, {'b', 'a'})
        self.assertEqual(ids(kept), ['b', 'a']); self.assertIs(kept[0], work[0]); self.assertIs(dropped[0], work[1])
        self.assertEqual((stats['age'], stats['rank'], stats['exact']), (1, 2, 2))
        self.assertEqual((stats['age_days_max'], stats['rank_max']), (30, 5))

    def test_zero_thresholds_disable_rank_but_keep_same_day_age(self):
        self.check_case([task('today', DAY), task('yesterday', '2026-10-11')], ['today'],
                        observations=[OBS], hits={QUERY: [hit('yesterday')]}, age_days_max=0, rank_max=0)

    def test_empty_work_and_invalid_thresholds(self):
        self.check_case([], [])
        for options in ({'age_days_max': -1}, {'rank_max': -1}, {'rank_max': True}, {'age_days_max': '30'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                filter_work([], {}, [], DAY, [], **options)


class PipelineTests(unittest.TestCase):
    def execute(self, module=pipeline, *, environment=None, compact=True, update=None, missing_date=False,
                empty_observations=False, bad_target=False, mock_stage=False, explicit_pipeline='synthetic-pipeline'):
        work = [task('drop'), task('ranked'), task('fresh', '2026-10-01'), task('exact')]
        if missing_date:
            work[0].pop('last_changed')
        text = 'Synthetic speaker: Synthetic status is recorded. exact'
        item = observation(title=OBS['title'], claim=text, subject=OBS['subject'], search_keywords=OBS['search_keywords'],
                           kind='fact', commitment_strength='not_applicable', owner=None, due_text=None,
                           evidence_ids=['U0001'], state_evidence_ids=[], assignment_score=2, change_score=2,
                           confidence_reason='Synthetic explicit evidence')
        raw = {'observations': [] if empty_observations else [item], 'coverage_notes': [],
               'search_queries': [{'text': 'Broad topic', 'evidence_ids': ['U0001']}],
               'meeting_summary': [{'text': 'Synthetic summary', 'evidence_ids': ['U0001']}]}
        captured = {}; prompts = []; applied = []

        class Index:
            def __init__(self, *args): pass
            def prepare(self, *args): return {'snapshot_id': 'synthetic'}
            def search(self, query, kinds, limit):
                if query == QUERY:
                    # Deliberate wrong order in mixed search; separate Work quota
                    # is authoritative for Hot-Set rank.
                    order = ['ranked', 'drop', 'fresh'] if kinds == ['work'] else ['drop', 'fresh', 'ranked']
                else:
                    order = ['drop', 'fresh', 'ranked']
                return [hit(w) for w in order]
            def persist(self, *args): pass

        class API:
            store = object()
            def __call__(self, prompt, model, max_tokens=0, schema=None):
                prompts.append((prompt.encode('utf-8'), copy.deepcopy(schema), max_tokens))
                if schema is None:
                    value = raw
                elif 'work_results' in schema.get('properties', {}):
                    aligned = copy.deepcopy(raw['observations'])
                    for i, obs in enumerate(aligned):
                        obs['source_index'] = i
                        if update:
                            obs.update(kind='status', update='progress', work_state='waiting',
                                       update_target='W'+str(ids(captured['work']).index(update)))
                        if bad_target:
                            obs['update_target'] = 'W999'
                    value = {'observations': aligned, 'coverage_notes': [], 'open_ids': [],
                             'work_results': {str(i): 'unchanged' for i in range(len(captured['work']))}}
                elif 'results' in schema.get('properties', {}):
                    value = {'results': {str(i): 'unchanged' for i in range(len(work))}}
                elif 'verdicts' in schema.get('properties', {}):
                    value = {'verdicts': [{'index': 0, 'verdict': 'supported', 'evidence_ids': ['U0001'],
                              'due_role': 'none', 'duplicate_of': None, 'action_uncertainty': None,
                              'reason': 'Synthetic support'}]}
                else:
                    value = {'observations': [{**item, 'source_index': 0}], 'coverage_notes': []}
                return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': json.dumps(value)}], 'usage': {}}

        real_run = compact_reconcile.run
        def compact_run(**kwargs):
            captured.update(kwargs)
            if mock_stage:
                stage_inputs = []
                def stage(name, prompt, schema, check, limit):
                    stage_inputs.append((name, prompt, schema))
                    response = {'observations': [{**item, 'source_index': 0}], 'coverage_notes': [],
                                'open_ids': [], 'work_results': {str(i): 'unchanged' for i in range(len(kwargs['work']))}}
                    return check(response)
                kwargs['stage'] = stage
                result = real_run(**kwargs)
                captured['mock_stages'] = stage_inputs
                return result
            return real_run(**kwargs)

        def fake_apply(db, job, token, proposal, **kwargs):
            applied.append(copy.deepcopy(proposal))
            return []

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            db = connect(Path(tmp)/'synthetic.sqlite')
            stack.callback(db.close)
            stack.enter_context(patch.dict('os.environ', environment or {}, clear=True))
            # Original process is imported read-only; all its runtime writes and
            # prompt resource reads are redirected into this isolated copy.
            stack.enter_context(patch.object(module, 'ROOT', Path(tmp)))
            resources = Path(tmp)/'evaluation'; resources.mkdir()
            for name in ('prompt-v9.txt', 'work-gate-prompt-v9.txt', 'work-gate-schema-v9.json'):
                (resources/name).write_bytes((ROOT/'backend/evaluation'/name).read_bytes())
            stack.enter_context(patch.object(module, 'SearchIndex', Index))
            stack.enter_context(patch.object(module, 'known_work_ids', return_value=set(ids(work))))
            stack.enter_context(patch.object(module, 'apply', side_effect=fake_apply))
            stack.enter_context(patch.object(module, 'documents', return_value=[]))
            stack.enter_context(patch.object(module, 'current_source_documents', return_value=[]))
            stack.enter_context(patch('reconcile.candidates', return_value=work))
            stack.enter_context(patch('compact_reconcile.run', side_effect=compact_run))
            result = module.process(db, {'id': 'synthetic-new', 'title': 'Synthetic meeting', 'meeting_date': DAY,
                                       'raw_transcript': text}, 'gpt-5.6-terra', api=API(), compact=compact,
                                    pipeline=explicit_pipeline)
            registered = db.execute('select pipeline from jobs').fetchone()[0]
        return result, captured, prompts, applied, registered

    def test_disabled_prompts_are_byte_identical_to_original_compact(self):
        spec = importlib.util.spec_from_file_location('original_hybrid_pipeline', SOURCE)
        original = importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
        expected = self.execute(original, update='ranked')
        for environment in ({}, {'DASHBOARD_HOTSET_FILTER': '0'}, {'DASHBOARD_HOTSET_FILTER': 'true'},
                            {'DASHBOARD_HOTSET_AGE_DAYS': 'invalid'}):
            with self.subTest(environment=environment):
                actual = self.execute(environment=environment, update='ranked')
                self.assertEqual(actual[2], expected[2])
                self.assertEqual(actual[0], expected[0])
                self.assertEqual(actual[3:], expected[3:])
                self.assertNotIn('hotset', actual[0]['hybrid'])

    def test_noncompact_ignores_filter_and_preserves_original_prompts(self):
        spec = importlib.util.spec_from_file_location('original_hybrid_pipeline', SOURCE)
        original = importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
        expected = self.execute(original, compact=False)
        actual = self.execute(compact=False, environment={'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': 'bad'})
        self.assertEqual(actual[2], expected[2]); self.assertEqual(actual[0], expected[0])

    def test_integration_filters_real_work_rank_and_records_only_dropped_ids(self):
        result, captured, prompts, applied, registered = self.execute(
            environment={'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '1'}, update='ranked')
        self.assertEqual(ids(captured['work']), ['ranked', 'fresh', 'exact'])
        self.assertNotIn('drop', {h['target_id'] for h in captured['hits'].values()})
        self.assertNotIn('drop', {h['target_id'] for values in captured['query_hits'].values() for h in values.values()})
        stats = result['hybrid']['hotset']
        self.assertEqual(stats, {'n_in': 4, 'n_kept': 3, 'n_dropped': 1, 'age': 1, 'rank': 1, 'exact': 1,
                                 'age_days_max': 30, 'rank_max': 1, 'dropped_ids': ['drop']})
        self.assertEqual(result['hybrid']['selected_work'], 3)
        self.assertEqual(applied[0]['observations'][0]['update_target'], 'ranked')
        self.assertEqual(applied[0]['observations'][0]['change_score'], 2)
        gate_prompt = prompts[-1][0].decode()
        gate_work = json.loads(gate_prompt.split('\nBestehende Arbeit:\n')[1].split('\nMeeting: ')[0])
        self.assertEqual(ids(gate_work), ['ranked'])
        self.assertEqual(registered, 'synthetic-pipeline:hotset1:age=30:rank=1')

    def test_mock_stage_executes_compact_contract_without_api(self):
        result, captured, _, _, _ = self.execute(mock_stage=True,
            environment={'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '1'})
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(captured['mock_stages'][0][0], 'compact-0')
        self.assertEqual(ids(captured['work']), ['ranked', 'fresh', 'exact'])

    def test_explicit_active_pipeline_identity_is_not_suffixed_twice(self):
        expected = 'synthetic-pipeline:hotset1:age=30:rank=5'
        _, _, _, _, registered = self.execute(environment={'DASHBOARD_HOTSET_FILTER': '1'},
                                               explicit_pipeline=expected)
        self.assertEqual(registered, expected)

    def test_kept_missing_date_does_not_break_unused_pending_in_compact(self):
        result, captured, _, _, _ = self.execute(missing_date=True,
            environment={'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '0'})
        self.assertIn('drop', ids(captured['work'])); self.assertEqual(result['status'], 'applied')

    def test_empty_observations_keep_age_and_exact_but_no_rank(self):
        result, captured, _, _, _ = self.execute(empty_observations=True,
            environment={'DASHBOARD_HOTSET_FILTER': '1'})
        self.assertEqual(ids(captured['work']), ['fresh', 'exact'])
        self.assertEqual(result['hybrid']['hotset']['rank'], 0)

    def test_environment_age_threshold_changes_selection(self):
        result, captured, _, _, _ = self.execute(environment={'DASHBOARD_HOTSET_FILTER': '1',
            'DASHBOARD_HOTSET_AGE_DAYS': '0', 'DASHBOARD_HOTSET_RANK': '1'})
        self.assertEqual(ids(captured['work']), ['ranked', 'exact'])
        self.assertEqual(result['hybrid']['hotset']['age_days_max'], 0)

    def test_dropped_work_cannot_be_selected_by_compact_alias(self):
        with self.assertRaisesRegex(ValidationError, 'Unknown compact candidate alias'):
            self.execute(bad_target=True, environment={'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '0'})

    def test_invalid_environment_fails_before_register_and_negative_rejected(self):
        for value in ('bad', '-1', ''):
            with self.subTest(value=value), patch.dict('os.environ',
                 {'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': value}, clear=True), \
                 patch.object(pipeline, 'register') as register:
                with self.assertRaises(ValidationError):
                    pipeline.process(None, {}, 'fixture', api=type('API', (), {'store': None})(), compact=True)
                register.assert_not_called()


class IdentityTests(unittest.TestCase):
    def test_version_has_filter_and_parameter_identity_only_for_compact(self):
        with patch.dict('os.environ', {}, clear=True):
            disabled = pipeline.version('gpt-5.6-terra', compact=True)
            noncompact = pipeline.version('gpt-5.6-terra')
        with patch.dict('os.environ', {'DASHBOARD_HOTSET_FILTER': '1'}, clear=True):
            active = pipeline.version('gpt-5.6-terra', compact=True)
            self.assertTrue(active.endswith(':hotset1:age=30:rank=5'))
            self.assertEqual(noncompact, pipeline.version('gpt-5.6-terra'))
        with patch.dict('os.environ', {'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '2'}, clear=True):
            changed = pipeline.version('gpt-5.6-terra', compact=True)
        self.assertNotEqual(active, disabled); self.assertNotEqual(active, changed)
        self.assertNotIn(':hotset1', disabled)

    def test_filter_source_participates_in_active_fingerprint_only(self):
        original = Path.read_text
        def changed(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            return value+'\n# synthetic revision' if path.name == 'candidate_filter.py' else value
        for enabled in ('0', '1'):
            with self.subTest(enabled=enabled), patch.dict('os.environ', {'DASHBOARD_HOTSET_FILTER': enabled}, clear=True):
                before = pipeline.version('gpt-5.6-terra', compact=True)
                with patch.object(Path, 'read_text', changed):
                    after = pipeline.version('gpt-5.6-terra', compact=True)
                self.assertEqual(before == after, enabled == '0')

    def test_durable_request_scope_changes_even_for_identical_prompt(self):
        hashes = []
        with tempfile.TemporaryDirectory() as tmp:
            for enabled in ('0', '1'):
                with patch.dict('os.environ', {'DASHBOARD_HOTSET_FILTER': enabled}, clear=True):
                    version = pipeline.version('gpt-5.6-terra', compact=True)
                store = Store()
                api = lambda *a, **k: {'usage_final': True, 'usage': {'input_tokens': 2, 'output_tokens': 1}}
                calls = DurableCalls(store, {'id': 'a'*64, 'lease_token': 'synthetic', 'pipeline': version,
                                     'expected_revision': 1}, api, {}, Path(tmp), prior_calls=[])
                calls('identical synthetic prompt', 'gpt-5.6-terra')
                request = json.loads(store.rows[0]['request_json'])
                self.assertEqual(request['scope']['pipeline'], version)
                hashes.append(store.rows[0]['request_hash'])
        self.assertNotEqual(*hashes)


if __name__ == '__main__':
    unittest.main()
