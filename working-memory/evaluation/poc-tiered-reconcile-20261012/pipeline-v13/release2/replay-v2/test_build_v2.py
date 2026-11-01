"""Synthetic release-builder checks; imports only, never reads saved call data.

Question: does request conversion use the actual release contract while retaining
the original data and authoritative full response? Criterion: exact prompt tail,
release delta schema, reference fidelity and safe output cap. Scope: one synthetic
observation/work slot. Failure leaves builder acceptance open.
Run: python3 -I -B test_build_v2.py
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('synthetic_build_v2', ROOT / 'build_v2_requests.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def fixture():
    fields = {'source_index': {'type': 'integer', 'enum': [0]},
              'update_target': {'type': ['null', 'string']}, 'update': {'type': 'boolean'},
              'matter_id': {'type': ['null', 'string']}, 'claim': {'type': 'string'}}
    change = {'type': 'object', 'additionalProperties': False,
              'properties': {'action': {'type': 'string', 'enum': ['done']}}, 'required': ['action']}
    schema = {'type': 'object', 'additionalProperties': False,
        'properties': {'observations': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'properties': fields, 'required': list(fields)}},
            'work_results': {'anyOf': [{'type': 'object', 'additionalProperties': False,
                'properties': {'0': {'$ref': '#/$defs/lifecycle_result'}}, 'required': ['0']}, {'type': 'null'}]},
            'open_ids': {'type': 'array', 'items': {'type': 'string'}},
            'coverage_notes': {'type': 'string'}},
        'required': ['observations', 'work_results', 'open_ids', 'coverage_notes'],
        '$defs': {'lifecycle_result': {'anyOf': [{'type': 'string', 'enum': ['unchanged']}, change]}}}
    observation = {'source_index': 0, 'update_target': None, 'update': False, 'matter_id': None, 'claim': 'synthetic'}
    full = {'observations': [observation], 'work_results': {'0': 'unchanged'},
            'open_ids': [], 'coverage_notes': 'synthetic saved-only field'}
    call = {'job_id': 'synthetic', 'call_index': 0, 'meeting_date': '2000-01-01',
            'obs_in': [copy.deepcopy(observation)], 'obs_out': [copy.deepcopy(observation)],
            'work': [{'work_index': '0'}], 'work_results': {'0': 'unchanged'}, 'open_ids': []}
    request = {'job_id': 'synthetic', 'call_index': 0,
        'request_json': {'model': 'gpt-6.1-sol', 'prompt': 'Head' + build.MARKER + 'synthetic é\nwork: 0\n',
                         'schema': schema, 'max_tokens': 12000},
        'reference_text': json.dumps(full), 'reference_usage': {'input_tokens': 100},
        'reference_micro_usd': 200}
    return call, request, full


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas, cls.compact = build.load_release(ROOT.parent / 'overlay')

    def test_actual_release_import_restores_stubbed_modules(self):
        names = ('hybrid_index', 'hybrid_schema', 'memory', 'retrieval_context', 'reconcile')
        before = {name: sys.modules.get(name) for name in names}
        sentinel = types.ModuleType('memory')
        sys.modules['memory'] = sentinel
        try:
            schemas, compact = build.load_release(ROOT.parent / 'overlay')
            self.assertIs(sys.modules['memory'], sentinel)
            self.assertEqual(Path(schemas.__file__).resolve(), (ROOT.parent / 'overlay/hybrid_schema.py').resolve())
            self.assertEqual(Path(compact.__file__).resolve(), (ROOT.parent / 'overlay/compact_reconcile.py').resolve())
            for name in names:
                if name != 'memory':
                    self.assertIs(sys.modules.get(name), before[name])
        finally:
            if before['memory'] is None:
                sys.modules.pop('memory', None)
            else:
                sys.modules['memory'] = before['memory']

    def test_prompt_tail_schema_full_reference_and_inputs_preserved(self):
        call, request, full = fixture()
        original = copy.deepcopy((call, request))
        row = build.build_record(call, request, self.schemas, self.compact)
        self.assertEqual(row['request_json']['prompt'].split(build.MARKER, 1)[1],
                         request['request_json']['prompt'].split(build.MARKER, 1)[1])
        self.assertNotEqual(row['request_json']['prompt'].split(build.MARKER, 1)[0], 'Head')
        self.assertEqual(row['request_json']['schema'], self.schemas.delta_schema(request['request_json']['schema']))
        self.assertEqual(row['reference_full'], full)
        self.assertIn('coverage_notes', row['reference_full'])
        self.assertEqual(row['reference_request_json'], request['request_json'])
        self.assertEqual(row['reference_schema'], request['request_json']['schema'])
        self.assertEqual(row['reference_usage'], request['reference_usage'])
        self.assertEqual(row['obs_in'], call['obs_in'])
        self.assertEqual(row['work'], call['work'])
        self.assertEqual(row['replay_id'], 'synthetic:0:delta-v2')
        self.assertEqual((call, request), original)

    def test_synthetic_delta_schema_accepts_changed_and_unchanged_slots(self):
        call, request, _ = fixture()
        schema = build.build_record(call, request, self.schemas, self.compact)['request_json']['schema']
        delta = {'observations': [{'source_index': 0,
                 'decision': {'update_target': None, 'update': False, 'matter_id': None}, 'changes': []}],
                 'work_results': [], 'unchanged_work_indices': ['0'], 'open_ids': [], 'coverage_notes': ''}
        self.assertEqual(build.common.schema_errors(delta, schema), [])
        delta['unchanged_work_indices'] = []
        delta['work_results'] = [{'work_index': '0', 'result': {'action': 'done'}}]
        self.assertEqual(build.common.schema_errors(delta, schema), [])
        delta['work_results'][0]['result'] = 'unchanged'
        self.assertTrue(build.common.schema_errors(delta, schema))

    def test_output_cap_minimum_and_larger_reference(self):
        for reference_cap, expected in ((12000, 16000), (20000, 20000)):
            call, request, _ = fixture()
            request['request_json']['max_tokens'] = reference_cap
            row = build.build_record(call, request, self.schemas, self.compact)
            self.assertEqual(row['max_output_tokens'], expected)
            self.assertEqual(row['request_json']['max_tokens'], expected)
            self.assertEqual(row['next_round_reserved_micro_usd'], build.replay.estimate(row)['reserved_micro_usd'])

    def test_model_identity_and_missing_marker_fail_closed(self):
        for change in ('model', 'identity', 'marker'):
            call, request, _ = fixture()
            if change == 'model':
                request['request_json']['model'] = 'other'
            elif change == 'identity':
                request['call_index'] = 1
            else:
                request['request_json']['prompt'] = 'synthetic'
            with self.subTest(case=change), self.assertRaises(ValueError):
                build.build_record(call, request, self.schemas, self.compact)

    def test_reference_archive_and_saved_lifecycle_mismatch_fail(self):
        for field in ('observations', 'open_ids', 'work_results'):
            call, request, full = fixture()
            full[field] = {} if field == 'work_results' else ['synthetic mismatch']
            request['reference_text'] = json.dumps(full)
            with self.subTest(field=field), self.assertRaises(ValueError):
                build.build_record(call, request, self.schemas, self.compact)

    def test_modified_data_tail_is_rejected(self):
        call, request, _ = fixture()
        compact = types.SimpleNamespace(delta_prompt=lambda prompt: prompt + 'changed')
        with self.assertRaises(ValueError):
            build.build_record(call, request, self.schemas, compact)

    def test_invalid_or_duplicate_saved_json_is_rejected(self):
        for text in ('not json', '{"observations":[],"observations":[]}'):
            call, request, _ = fixture()
            request['reference_text'] = text
            with self.subTest(case=len(text)), self.assertRaises(ValueError):
                build.build_record(call, request, self.schemas, self.compact)


if __name__ == '__main__':
    unittest.main()
