"""Offline synthetic tests plus all available complete archived responses.

Run with python3 -I -B test_delta.py. No production actions or source writes.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT.parents[2] / 'sol-operational-release-20261006' / 'backend'
# Isolated Python does not put script directories on sys.path.
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT), str(RELEASE)]
from delta_codec import to_delta, from_delta, equal
import delta_schema
import compact_reconcile as compact
import hybrid_schema
import hybrid_pipeline
from memory import ValidationError
from processor import units

hybrid_schema.ROOT = RELEASE

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

legacy = load('legacy_compact_for_test', RELEASE / 'compact_reconcile.py')
common = load('delta_test_schema_validator', ROOT / 'replay_common.py')


def observation():
    return dict(matter='Fixture', matter_id=None, kind='fact', title='Fixture',
        claim='A fixture is available.', owner=None,
        commitment_strength='not_applicable', due_text=None, update_target=None,
        update='none', uncertainty=None, required_review=False,
        evidence_ids=['U0001'], action_uncertainty=None, condition_text=None,
        work_state='not_applicable', state_evidence_ids=[], subject='Fixture',
        search_keywords=['fixture'], assignment_score=2, change_score=2,
        confidence_reason='Explicit fixture statement.')


def response(obs=None, work=None):
    return {'observations': [{'source_index': 0, **(obs or observation())}],
            'work_results': work if work is not None else {'0': 'unchanged'},
            'open_ids': [], 'coverage_notes': []}


class CodecTests(unittest.TestCase):
    def setUp(self):
        self.obs = [observation()]
        self.work = [{'id': 'fixture-task'}]

    def roundtrip(self, full):
        delta = to_delta(full, self.obs, self.work)
        self.assertTrue(equal(from_delta(delta, self.obs, self.work), full))
        return delta

    def test_unchanged_is_explicit_source_only_and_sparse_work(self):
        delta = self.roundtrip(response())
        self.assertEqual(delta['observations'], [{'source_index': 0, 'changes': []}])
        self.assertEqual(delta['work_results'], [])

    def test_explicit_null_replaces_old_value(self):
        self.obs[0]['owner'] = 'Fixture owner'
        delta = self.roundtrip(response())
        self.assertIn({'owner': None}, delta['observations'][0]['changes'])

    def test_missing_change_inherits_nonnull_value(self):
        self.obs[0]['owner'] = 'Fixture owner'
        full = response(self.obs[0])
        self.assertEqual(self.roundtrip(full)['observations'][0]['changes'], [])

    def test_missing_input_field_can_be_added_as_null(self):
        del self.obs[0]['owner']
        self.assertIn({'owner': None}, self.roundtrip(response())['observations'][0]['changes'])

    def test_removal_is_invalid_under_original_contract(self):
        full = response()
        del full['observations'][0]['owner']
        with self.assertRaises(ValueError):
            to_delta(full, self.obs, self.work)

    def test_lists_replace_and_preserve_order_duplicates(self):
        full = response()
        full['observations'][0]['search_keywords'] = ['b', 'a', 'b']
        full['observations'][0]['state_evidence_ids'] = []
        self.roundtrip(full)

    def test_type_strict_false_vs_zero(self):
        self.assertFalse(equal(False, 0))
        self.assertFalse(equal({'x': [False]}, {'x': [0]}))
        full = response()
        full['observations'][0]['required_review'] = 0
        self.assertIn({'required_review': 0}, self.roundtrip(full)['observations'][0]['changes'])

    def test_reordered_sources_roundtrip(self):
        self.obs = [{**observation(), 'source_index': 7}, {**observation(), 'source_index': 2}]
        full = response()
        full['observations'] = [{**observation(), 'source_index': 2}, {**observation(), 'source_index': 7}]
        self.roundtrip(full)

    def test_open_only_null_is_not_converted_to_final(self):
        full = {'observations': [], 'work_results': None,
                'open_ids': ['H0'], 'coverage_notes': ['Fixture need']}
        self.roundtrip(full)

    def test_nonfinal_empty_observations_remain_empty(self):
        full = response()
        full['observations'] = []
        self.roundtrip(full)

    def test_lifecycle_change_preserved(self):
        full = response(work={'0': {'action': 'progress', 'reason': 'fixture',
            'title': 'fixture', 'claim': 'fixture', 'evidence_ids': ['U0001'],
            'owner': None, 'due_text': None, 'assignment_score': 2, 'change_score': 2}})
        self.assertEqual(len(self.roundtrip(full)['work_results']), 1)

    def test_input_objects_are_not_mutated_and_no_shared_lists(self):
        full = response()
        saved = copy.deepcopy((full, self.obs, self.work))
        delta = to_delta(full, self.obs, self.work)
        restored = from_delta(delta, self.obs, self.work)
        restored['observations'][0]['search_keywords'].append('changed')
        self.assertTrue(equal((full, self.obs, self.work), saved))

    def test_duplicate_unknown_and_bool_indices_rejected(self):
        for index in (False, 99):
            with self.subTest(case=str(index)):
                delta = to_delta(response(), self.obs, self.work)
                delta['observations'][0]['source_index'] = index
                with self.assertRaises(ValueError):
                    from_delta(delta, self.obs, self.work)
        delta = to_delta(response(), self.obs, self.work)
        delta['observations'] *= 2
        with self.assertRaises(ValueError):
            from_delta(delta, self.obs, self.work)

    def test_unknown_duplicate_and_multi_field_changes_rejected(self):
        for changes in ([{'bogus': None}], [{'owner': None}, {'owner': 'x'}],
                        [{'owner': None, 'update': 'none'}], [{'source_index': 2}]):
            delta = to_delta(response(), self.obs, self.work)
            delta['observations'][0]['changes'] = changes
            with self.assertRaises(ValueError):
                from_delta(delta, self.obs, self.work)

    def test_unknown_duplicate_unchanged_lifecycle_rejected(self):
        for entries in ([{'work_index': '99', 'result': {'action': 'done'}}],
                        [{'work_index': '0', 'result': {'action': 'unchanged'}}],
                        [{'work_index': '0', 'result': {'action': 'done'}}] * 2):
            delta = to_delta(response(), self.obs, self.work)
            delta['work_results'] = entries
            with self.assertRaises(ValueError):
                from_delta(delta, self.obs, self.work)

    def test_incomplete_full_lifecycle_is_not_silently_repaired(self):
        with self.assertRaises(ValueError):
            to_delta(response(work={}), self.obs, self.work)

    def test_wrong_work_order_is_rejected(self):
        with self.assertRaises(ValueError):
            to_delta(response(), self.obs, [{'id': 'fixture', 'work_index': '9'}])


class SchemaTests(unittest.TestCase):
    def full_schema(self):
        with patch.dict(os.environ, {'DASHBOARD_DELTA_OUTPUT': '0'}):
            return compact.response_schema(compact.Catalog([{'id': 'fixture-task'}], {}, {}), [0])

    def test_derived_schema_valid_and_preserves_full_schema(self):
        full = self.full_schema()
        saved = copy.deepcopy(full)
        schema = delta_schema.delta_schema(full)
        self.assertTrue(common.validate_schema_structure(schema))
        self.assertTrue(equal(full, saved))
        self.assertEqual(common.schema_errors(to_delta(response(), [observation()], [{'id': 'fixture-task'}]), schema), [])

    def test_every_strict_object_property_is_required(self):
        def walk(value):
            if isinstance(value, dict):
                if value.get('type') == 'object':
                    self.assertEqual(set(value['properties']), set(value['required']))
                    self.assertIs(value['additionalProperties'], False)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(delta_schema.delta_schema(self.full_schema()))

    def test_empty_catalog_source_and_work_empty(self):
        with patch.dict(os.environ, {'DASHBOARD_DELTA_OUTPUT': '1'}):
            schema = compact.response_schema(compact.Catalog([], {}, {}), [])
        value = {'observations': [], 'coverage_notes': [], 'work_results': [], 'open_ids': []}
        self.assertEqual(common.schema_errors(value, schema), [])
        value['work_results'] = [{'work_index': '0', 'result': {}}]
        self.assertTrue(common.schema_errors(value, schema))

    def test_wrong_type_unknown_fields_and_aliases_fail(self):
        schema = delta_schema.delta_schema(self.full_schema())
        for change in ({'update_target': 'W99'}, {'change_score': False}, {'bogus': 'x'}):
            value = to_delta(response(), [observation()], [{'id': 'fixture-task'}])
            value['observations'][0]['changes'] = [change]
            self.assertTrue(common.schema_errors(value, schema))

    def test_prompt_preserves_data_section_and_updates_coverage_rules(self):
        data = 'FIXTURE DATA: Genau ein work_results-Eintrag pro Arbeitsplatz, auch bei unveränderten Aufgaben.'
        prompt = compact.INSTRUCTION + '\n' + __import__('reconcile').PROMPT + '\nVorläufige Beobachtungen:\n' + data
        updated = delta_schema.delta_prompt(prompt)
        self.assertEqual(updated.split('\nVorläufige Beobachtungen:\n')[1], data)
        self.assertNotIn('Genau ein work_results-Eintrag pro Arbeitsplatz', updated.split('\nVorläufige Beobachtungen:\n')[0])
        self.assertIn(delta_schema.PROMPT_ADDENDUM, updated)


class IntegrationTests(unittest.TestCase):
    def execute(self, module, enabled, transform=None, hits=None, work=None, replies=None):
        text = 'A fixture is available.'
        raw = {'observations': [observation()], 'coverage_notes': []}
        calls = []
        work = work or [{'id': 'fixture-task', 'title': 'Fixture', 'claim': text, 'parent_matter_id': None}]
        full = response()
        def stage(name, prompt, schema, check, limit):
            calls.append((name, prompt, schema, limit))
            value = copy.deepcopy(replies[len(calls)-1] if replies else full)
            if transform:
                value = transform(value)
            if enabled == '1':
                value = to_delta(value, raw['observations'], work)
            return check(value)
        with patch.dict(os.environ, {'DASHBOARD_DELTA_OUTPUT': enabled}):
            result = module.run(raw=raw, work=work, hits=hits or {}, query_hits={},
                originals=units(text), meeting={'raw_transcript': text}, known={'fixture-task'},
                stage=stage, rules='Fixture rules', base='Fixture source', confidence_rules='Fixture confidence')
        return result, calls

    def test_disabled_prompt_schema_limit_and_result_identical_to_original(self):
        for disabled in ('0', '', 'true', '01'):
            actual = self.execute(compact, disabled)
            original = self.execute(legacy, disabled)
            self.assertTrue(equal(actual, original))
            self.assertEqual(json.dumps(actual, ensure_ascii=False), json.dumps(original, ensure_ascii=False))

    def test_delta_actual_existing_check_accepts_same_proposal(self):
        (actual, calls) = self.execute(compact, '1')
        (original, _) = self.execute(legacy, '0')
        self.assertTrue(equal(actual, original))
        self.assertIn(delta_schema.PROMPT_ADDENDUM, calls[0][1])
        self.assertEqual(calls[0][2]['properties']['observations']['items']['required'], ['source_index', 'changes'])

    def test_missing_source_fails_original_coverage_gate(self):
        def transform(value):
            value['observations'] = []
            return value
        with self.assertRaisesRegex(ValidationError, 'coverage'):
            self.execute(compact, '1', transform)

    def test_open_then_final_uses_unchanged_existing_expansion_gate(self):
        hit = {'id': 'fixture-hit', 'kind': 'passage', 'text': 'Fixture historical text', 'metadata': {}}
        opening = {'observations': [], 'work_results': None, 'coverage_notes': [], 'open_ids': ['H0']}
        (actual, _) = self.execute(compact, '1', hits={'fixture-hit': hit}, replies=[opening, response()])
        (original, _) = self.execute(legacy, '0', hits={'fixture-hit': hit}, replies=[opening, response()])
        self.assertTrue(equal(actual, original))
        self.assertEqual(actual[1]['rounds'], 2)

    def test_open_partial_result_rejected(self):
        hit = {'id': 'fixture-hit', 'kind': 'passage', 'text': 'Fixture', 'metadata': {}}
        value = response()
        value['open_ids'] = ['H0']
        with self.assertRaisesRegex(ValidationError, 'partial'):
            self.execute(compact, '1', hits={'fixture-hit': hit}, replies=[value])

    def test_unknown_delta_lifecycle_slot_fails_before_gate(self):
        def stage(name, prompt, schema, check, limit):
            check({'observations': [{'source_index': 0, 'changes': []}],
                   'work_results': [{'work_index': '3', 'result': {'action': 'done'}}],
                   'open_ids': [], 'coverage_notes': []})
        with patch.dict(os.environ, {'DASHBOARD_DELTA_OUTPUT': '1'}):
            with self.assertRaisesRegex(ValidationError, 'delta'):
                compact.run(raw={'observations': [observation()]}, work=[], hits={}, query_hits={},
                    originals=units('A fixture is available.'), meeting={'raw_transcript': 'A fixture is available.'},
                    known=set(), stage=stage, rules='', base='', confidence_rules='')

    def test_version_prefix_only_for_enabled_compact(self):
        # Version namespace test; no source hashes or exterior scope proofs.
        with patch.object(Path, 'read_text', return_value='fixture'), patch.object(hybrid_pipeline, 'fingerprint', return_value='fixture-revision'):
            with patch.dict(os.environ, {'DASHBOARD_DELTA_OUTPUT': '1'}):
                self.assertTrue(hybrid_pipeline.version('fixture', compact=True).startswith('v13:compact-delta2:gate1:'))
                self.assertTrue(hybrid_pipeline.version('fixture', compact=False).startswith('v10:hybrid1:gate1:'))
            with patch.dict(os.environ, {'DASHBOARD_DELTA_OUTPUT': '0'}):
                self.assertTrue(hybrid_pipeline.version('fixture', compact=True).startswith('v11:compact1:gate1:'))

    def test_disabled_version_uses_identical_original_algorithm_input(self):
        original = load('legacy_pipeline_for_version_test', RELEASE / 'hybrid_pipeline.py')
        captured_original, captured_patched = [], []
        # Capture algorithm input instead of computing any source hash.
        def capture(target):
            def calculate(value):
                target.append(value)
                return 'fixture-revision'
            return calculate
        real_read = Path.read_text
        modified = ('compact_reconcile.py', 'hybrid_schema.py', 'hybrid_pipeline.py')
        def original_input(path, *args, **kwargs):
            if path.parent == RELEASE and path.name in modified:
                return real_read(path, *args, **kwargs)
            return 'synthetic dependency source: ' + str(path.relative_to(RELEASE))
        def read_from_patch(path, *args, **kwargs):
            if path.parent == RELEASE and path.name in modified:
                return real_read(ROOT / 'backend' / path.name, *args, **kwargs)
            return original_input(path, *args, **kwargs)
        with patch.object(Path, 'read_text', original_input), patch.object(original, 'fingerprint', capture(captured_original)):
            expected = [original.version('fixture', compact=flag) for flag in (False, True)]
        with patch.object(hybrid_pipeline, 'ROOT', RELEASE), patch.object(Path, 'read_text', read_from_patch), patch.object(hybrid_pipeline, 'fingerprint', capture(captured_patched)):
            with patch.dict(os.environ, {'DASHBOARD_DELTA_OUTPUT': '0'}):
                actual = [hybrid_pipeline.version('fixture', compact=flag) for flag in (False, True)]
        self.assertEqual(actual, expected)
        self.assertTrue(equal(captured_patched, captured_original))


class ArchivedRoundtripTests(unittest.TestCase):
    def test_all_available_complete_archived_responses(self):
        count = 0
        for line in (ROOT / 'data' / 'all_calls.jsonl').read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row.get('full_response') is None:
                continue
            count += 1
            delta = to_delta(row['full_response'], row['obs_in'], row['work'])
            restored = from_delta(delta, row['obs_in'], row['work'])
            self.assertTrue(equal(restored, row['full_response']), 'Archive roundtrip mismatch')
            schema = delta_schema.delta_schema(row['request_json']['schema'])
            self.assertEqual(common.schema_errors(delta, schema), [], 'Archive delta schema mismatch')
        self.assertEqual(count, 40)


if __name__ == '__main__':
    unittest.main()
