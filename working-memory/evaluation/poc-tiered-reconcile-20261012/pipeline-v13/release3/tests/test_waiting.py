"""Synthetic Release-3 regression coverage, no network or meeting data."""
import copy
import importlib.util
import itertools
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import candidate_filter
import hybrid_pipeline as pipeline
import canonical_worker
import test_hotset as legacy
from local_support import ROOT, RELEASE2
from memory import ValidationError

DAY = '2026-10-12'
OBS = {'title': 'Synthetic', 'subject': '', 'search_keywords': []}
QUERY = 'Synthetic '
legacy.ROOT = ROOT

def load_original(name):
    spec = importlib.util.spec_from_file_location('release2_' + name, RELEASE2 / 'overlay' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class WaitingFilterTests(unittest.TestCase):
    def select(self, work, **options):
        return candidate_filter.filter_work(work, {}, [], DAY, set(), **options)

    def test_waiting_alone_keeps_old_unranked_unmentioned_work(self):
        item = {'id': 'waiting', 'status': 'waiting', 'last_changed': '2026-01-01'}
        kept, dropped, stats = self.select([item], keep_waiting=True)
        self.assertEqual(kept, [item])
        self.assertIs(kept[0], item)
        self.assertEqual(dropped, [])
        self.assertEqual([stats[k] for k in ('age', 'rank', 'exact', 'waiting')], [0, 0, 0, 1])

    def test_only_exact_waiting_status_gets_the_new_reason(self):
        work = [{'id': str(i), 'last_changed': '2026-01-01', 'status': status}
                for i, status in enumerate(('waiting', 'Waiting', 'wartend', 'waiting ', '', None, 'pending', 'done', 1))]
        work.append({'id': 'missing', 'last_changed': '2026-01-01'})
        kept, dropped, stats = self.select(work, keep_waiting=True)
        self.assertEqual([v['id'] for v in kept], ['0'])
        self.assertEqual(len(dropped), 9)
        self.assertEqual(stats['waiting'], 1)

    def test_missing_unknown_status_does_not_override_other_rules(self):
        kept, dropped, stats = self.select([{'id': 'unknown'}, {'id': 'null', 'status': None}], keep_waiting=True)
        self.assertEqual(len(kept), 2)
        self.assertFalse(dropped)
        self.assertEqual((stats['age'], stats['waiting']), (2, 0))

    def test_all_16_rule_combinations_use_or_and_overlap_counters(self):
        for age, rank, exact, waiting in itertools.product((False, True), repeat=4):
            with self.subTest(age=age, rank=rank, exact=exact, waiting=waiting):
                row = {'id': 'a', 'last_changed': DAY if age else '2026-01-01',
                       'status': 'waiting' if waiting else 'pending'}
                hits = {QUERY: [{'kind': 'work', 'target_id': 'a'}]} if rank else {}
                kept, dropped, stats = candidate_filter.filter_work(
                    [row], hits, [OBS], DAY, {'a'} if exact else set(), keep_waiting=True)
                self.assertEqual(bool(kept), any((age, rank, exact, waiting)))
                self.assertEqual(bool(dropped), not any((age, rank, exact, waiting)))
                self.assertEqual([stats[k] for k in ('age', 'rank', 'exact', 'waiting')],
                                 [int(v) for v in (age, rank, exact, waiting)])

    def test_order_identity_no_mutation_and_duplicate_reasons(self):
        work = [{'id': 'b', 'last_changed': DAY, 'status': 'waiting'},
                {'id': 'drop', 'last_changed': '2026-01-01'},
                {'id': 'a', 'last_changed': '2026-01-01', 'status': 'waiting'}]
        hits = {QUERY: [{'target_id': 'b'}, {'target_id': 'b'}, {'target_id': 'a'}]}
        before = copy.deepcopy((work, hits))
        kept, dropped, stats = candidate_filter.filter_work(work, hits, [OBS, OBS], DAY, {'a', 'b'}, keep_waiting=True)
        self.assertEqual([v['id'] for v in kept], ['b', 'a'])
        self.assertIs(kept[0], work[0]); self.assertIs(kept[1], work[2]); self.assertIs(dropped[0], work[1])
        self.assertEqual([stats[k] for k in ('age', 'rank', 'exact', 'waiting')], [1, 2, 2, 2])
        self.assertEqual((work, hits), before)

    def test_default_and_false_match_release2_serialized_results(self):
        old = load_original('candidate_filter')
        work = [{'id': 'old', 'status': 'waiting', 'last_changed': '2026-01-01'},
                {'id': 'fresh', 'status': 'waiting', 'last_changed': DAY}]
        expected = old.filter_work(work, {}, [], DAY, set())
        for options in ({}, {'keep_waiting': False}):
            actual = self.select(work, **options)
            self.assertEqual(json.dumps(actual).encode(), json.dumps(expected).encode())
            self.assertNotIn('waiting', actual[2])

    def test_waiting_works_with_zero_thresholds_and_empty_inputs(self):
        row = {'id': 'a', 'last_changed': '2026-01-01', 'status': 'waiting'}
        self.assertEqual(self.select([row], age_days_max=0, rank_max=0, keep_waiting=True)[0], [row])
        kept, dropped, stats = self.select([], keep_waiting=True)
        self.assertEqual((kept, dropped, stats['waiting']), ([], [], 0))

    def test_non_boolean_argument_is_rejected(self):
        for value in (0, 1, None, '1', [], {}):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                self.select([], keep_waiting=value)

class WaitingPipelineTests(unittest.TestCase):
    def execute(self, module=pipeline, **options):
        real_task = legacy.task
        def waiting_task(identifier, *args, **kwargs):
            row = real_task(identifier, *args, **kwargs)
            row['status'] = 'waiting' if identifier == 'drop' else 'pending'
            return row
        with patch.object(legacy, 'task', side_effect=waiting_task):
            return legacy.PipelineTests().execute(module, **options)

    def test_active_rule_retains_waiting_catalog_and_hits_in_full_pipeline(self):
        env = {'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '1'}
        off = self.execute(environment=env)
        actual = self.execute(environment={**env, 'DASHBOARD_HOTSET_KEEP_WAITING': '1'})
        self.assertEqual([v['id'] for v in off[1]['work']], ['ranked', 'fresh', 'exact'])
        self.assertEqual([v['id'] for v in actual[1]['work']], ['drop', 'ranked', 'fresh', 'exact'])
        self.assertIn('drop', {v['target_id'] for v in actual[1]['hits'].values()})
        self.assertEqual(actual[0]['hybrid']['hotset']['waiting'], 1)
        self.assertEqual(actual[0]['hybrid']['hotset']['dropped_ids'], [])
        self.assertEqual(actual[0]['status'], 'applied')
        self.assertEqual(actual[4], 'synthetic-pipeline:hotset1:age=30:rank=1:wait1')

    def test_waiting_and_delta_preserve_same_checked_proposal(self):
        env = {'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '1', 'DASHBOARD_HOTSET_KEEP_WAITING': '1'}
        expected = self.execute(environment=env, update='drop')
        actual = self.execute(environment={**env, 'DASHBOARD_DELTA_OUTPUT': '1'}, update='drop')
        self.assertEqual(actual[3], expected[3])
        self.assertEqual(actual[3][0]['observations'][0]['update_target'], 'drop')
        self.assertTrue(actual[4].endswith(':rank=1:wait1:delta2'))

    def test_default_and_zero_preserve_release2_prompt_result_and_explicit_identity_bytes(self):
        old = load_original('hybrid_pipeline')
        for filter_flag, delta_flag in itertools.product(('0', '1'), repeat=2):
            env = {'DASHBOARD_HOTSET_FILTER': filter_flag, 'DASHBOARD_DELTA_OUTPUT': delta_flag,
                   'DASHBOARD_HOTSET_RANK': '1'}
            expected = self.execute(old, environment=env, update='ranked')
            for waiting in (None, '0'):
                active_env = {**env, **({} if waiting is None else {'DASHBOARD_HOTSET_KEEP_WAITING': waiting})}
                with self.subTest(filter=filter_flag, delta=delta_flag, waiting=waiting):
                    actual = self.execute(environment=active_env, update='ranked')
                    self.assertEqual(actual[2], expected[2])
                    self.assertEqual(actual[0], expected[0])
                    self.assertEqual(actual[3:], expected[3:])
                    self.assertEqual(actual[4].encode(), expected[4].encode())

    def test_ignored_when_filter_off_or_noncompact_preserves_release2_flow(self):
        old = load_original('hybrid_pipeline')
        for compact, env in ((True, {'DASHBOARD_HOTSET_FILTER': '0'}),
                             (False, {'DASHBOARD_HOTSET_FILTER': '1'})):
            expected = self.execute(old, compact=compact, environment=env)
            for value in ('0', '1'):
                actual = self.execute(compact=compact, environment={**env, 'DASHBOARD_HOTSET_KEEP_WAITING': value})
                self.assertEqual(actual[2:], expected[2:])
                self.assertEqual(actual[0], expected[0])

    def test_invalid_active_values_fail_before_register(self):
        for value in ('', 'true', 'false', '2', '-1', ' 1', '1 ', '01', 'ON'):
            with self.subTest(value=value), patch.dict(os.environ,
                    {'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_KEEP_WAITING': value}, clear=True), \
                    patch.object(pipeline, 'register') as register:
                with self.assertRaises(ValidationError):
                    pipeline.process(None, {}, 'synthetic', compact=True, api=type('API', (), {'store': None})())
                register.assert_not_called()
                with self.assertRaises(ValidationError):
                    pipeline.version('synthetic', compact=True)

    def test_invalid_switch_is_configuration_error_even_when_inactive(self):
        for compact, filter_flag in itertools.product((False, True), ('0', '1')):
            with self.subTest(compact=compact, filter=filter_flag), patch.dict(os.environ,
                    {'DASHBOARD_HOTSET_FILTER': filter_flag, 'DASHBOARD_HOTSET_KEEP_WAITING': 'invalid'}, clear=True):
                with self.assertRaises(ValidationError):
                    pipeline.feature_suffix(compact)

    def test_exact_suffix_and_no_duplicate_for_explicit_id(self):
        env = {'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '8',
               'DASHBOARD_HOTSET_KEEP_WAITING': '1', 'DASHBOARD_DELTA_OUTPUT': '1'}
        expected = 'synthetic-pipeline:hotset1:age=30:rank=8:wait1:delta2'
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(pipeline.feature_suffix(True), ':hotset1:age=30:rank=8:wait1:delta2')
        self.assertEqual(self.execute(environment=env, explicit_pipeline=expected)[4], expected)

    def test_off_version_matches_release2_with_identical_fingerprint_input(self):
        old = load_original('hybrid_pipeline')
        # Both functions read the same current source bytes through one ROOT.
        # Actual Release-2 and Release-3 source revisions intentionally differ.
        with patch.object(old, 'ROOT', pipeline.ROOT):
            for compact, filter_flag, delta_flag in itertools.product((False, True), ('0', '1'), ('0', '1')):
                env = {'DASHBOARD_HOTSET_FILTER': filter_flag, 'DASHBOARD_DELTA_OUTPUT': delta_flag}
                with patch.dict(os.environ, env, clear=True):
                    expected = old.version('synthetic', compact=compact)
                    self.assertEqual(pipeline.version('synthetic', compact=compact).encode(), expected.encode())
                    with patch.dict(os.environ, {'DASHBOARD_HOTSET_KEEP_WAITING': '0'}):
                        self.assertEqual(pipeline.version('synthetic', compact=compact).encode(), expected.encode())

    def test_canonical_suffix_follows_waiting_and_delta(self):
        import processor
        env = {'DASHBOARD_HOTSET_FILTER': '1', 'DASHBOARD_HOTSET_RANK': '8',
               'DASHBOARD_HOTSET_KEEP_WAITING': '1', 'DASHBOARD_DELTA_OUTPUT': '1'}
        with patch.object(processor, 'PROMPT_VERSION', 'v11'), patch.dict(os.environ, env, clear=True):
            value = canonical_worker.pipeline_version('gpt-6.1-sol')
        self.assertIn(':hotset1:age=30:rank=8:wait1:delta2:canonical1:', value)

class ArtifactTests(unittest.TestCase):
    def test_contract_bytes_except_revision_are_release2_bytes(self):
        current = json.loads((ROOT / 'overlay/default_contract.json').read_text())
        # Read the baseline directly, bypassing the runtime overlay resolver.
        with open(RELEASE2 / 'overlay/default_contract.json', encoding='utf-8') as handle:
            original = json.load(handle)
        self.assertEqual(current['contract'], original['contract'])
        self.assertNotEqual(current['pipeline_version'], original['pipeline_version'])

    def test_manifest_reuse_targets_match_only_actual_copy_payloads(self):
        import make_manifest
        docker = (ROOT / 'overlay/Dockerfile').read_text()
        payloads = next(line for line in docker.splitlines() if line.startswith('COPY ')).split()[2:-1]
        self.assertEqual(payloads, [*make_manifest.TARGETS, 'build-manifest.json'])
        self.assertEqual(set(make_manifest.TARGETS), {'candidate_filter.py', 'hybrid_pipeline.py', 'offline_check.py', 'default_contract.json'})
