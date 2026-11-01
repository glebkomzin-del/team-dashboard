"""Synthetic checks: acceptance needs positive evidence, never empty errors."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('test_v2_comparison', ROOT / 'compare_v2.py')
compare = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compare
spec.loader.exec_module(compare)


def fixtures():
    decisions = {'update_target': {'type': ['string', 'null']}, 'update': {'type': 'boolean'},
                 'matter_id': {'type': ['string', 'null']}}
    observation = {'type': 'object', 'properties': {'source_index': {'type': 'integer'}, **decisions},
                   'required': ['source_index', *decisions], 'additionalProperties': False}
    full_schema = {'type': 'object', 'properties': {'observations': {'type': 'array', 'items': observation},
                   'open_ids': {'type': 'array', 'items': {'type': 'string'}},
                   'work_results': {'type': ['object', 'null']}},
                   'required': ['observations', 'open_ids', 'work_results'], 'additionalProperties': False}
    patch = {'type': 'object', 'properties': {'source_index': {'type': 'integer'},
             'decision': {'type': 'object', 'properties': decisions, 'required': list(decisions), 'additionalProperties': False},
             'changes': {'type': 'array', 'items': {'type': 'object'}}},
             'required': ['source_index', 'decision', 'changes'], 'additionalProperties': False}
    delta_schema = {'type': 'object', 'properties': {'observations': {'type': 'array', 'items': deepcopy(patch)},
                    'open_ids': {'type': 'array', 'items': {'type': 'string'}},
                    'work_results': {'type': ['array', 'null']},
                    'unchanged_work_indices': {'type': ['array', 'null']}},
                    'required': ['observations', 'open_ids', 'work_results', 'unchanged_work_indices'], 'additionalProperties': False}
    full = {'observations': [{'source_index': 0, 'update_target': 'W1', 'update': True, 'matter_id': 'M1'}],
            'open_ids': [], 'work_results': {'0': {'action': 'close'}}}
    usage = {'input_tokens': 100, 'output_tokens': 100, 'input_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0},
             'output_tokens_details': {'reasoning_tokens': 20}}
    record = {'job_id': 'synthetic', 'call_index': 0, 'replay_id': 'synthetic:0:delta-v2',
              'request_json': {'prompt': '', 'schema': delta_schema, 'max_tokens': 100},
              'reference_schema': full_schema, 'reference_full': full, 'reference_usage': usage,
              'obs_in': deepcopy(full['observations']), 'work': [{'id': 'W1', 'work_index': '0'}],
              'next_round_reserved_micro_usd': 160000}
    delta = compare.load('delta_codec').to_delta(full, record['obs_in'], record['work'])
    reservation = {k: record[k] for k in ('job_id', 'call_index', 'replay_id')}
    reservation.update(record_type='reservation', reserved_micro_usd=160000)
    attempt = deepcopy(reservation)
    attempt.update(record_type='attempt', status='ok', usage=deepcopy(usage))
    attempt['usage']['output_tokens'] = 40
    refresh(attempt, delta)
    controls = {'decision_agreement_rate': 1.0, 'complete': True, 'evidence_known': 1, 'calls': 3, 'errors': 0}
    return record, reservation, attempt, controls


def refresh(attempt, delta=None):
    if delta is not None:
        attempt['text'] = json.dumps(delta)
    attempt['response'] = {'status': 'completed', 'model': 'gpt-6.1-sol', 'service_tier': 'default',
                           'usage': deepcopy(attempt['usage']),
                           'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                                       'content': [{'type': 'output_text', 'text': attempt['text']}]}]}
    attempt['raw_response'] = json.dumps(attempt['response'])
    attempt['actual_micro_usd'] = compare.load('replay_common').usage_micro_usd(attempt['usage'], 'gpt-6.1-sol')


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.record, self.reservation, self.attempt, self.controls = fixtures()

    def report(self, controls=True, events=None):
        return compare.compare_records([self.record], events if events is not None else [self.reservation, self.attempt],
                                       self.controls if controls else None)

    def change(self, key, value):
        delta = json.loads(self.attempt['text'])
        delta['observations'][0]['decision'][key] = value
        refresh(self.attempt, delta)

    def test_positive_evidence_accepts(self):
        report = self.report()
        self.assertEqual(report['passed'], 1)
        self.assertEqual(report['total']['output_ratio'], .4)
        self.assertEqual(report['total']['lifecycle_positive_recall'], 1)

    def test_wrong_decision_fails_despite_valid_schemas(self):
        self.change('matter_id', 'M2')
        report = self.report()
        self.assertEqual(report['schema_pass'], 1)
        self.assertEqual(report['decision_agreement_pass'], 0)
        self.assertEqual(report['total']['update_target_rate'], 1)
        self.assertEqual(report['passed'], 0)

    def test_unknown_control_is_not_success(self):
        report = self.report(controls=False)
        self.assertIsNone(report['decision_agreement_pass'])
        self.assertEqual(report['passed'], 0)

    def test_incomplete_required_controls_fail(self):
        self.controls['missing_control_prefixes'] = ['missing']
        self.assertEqual(self.report()['passed'], 0)

    def test_boolean_control_evidence_not_integer(self):
        self.controls['evidence_known'] = True
        self.assertEqual(self.report()['control_evidence_known'], 0)

    def test_control_rate_nonfinite_is_unknown(self):
        self.controls['decision_agreement_rate'] = float('nan')
        self.assertIsNone(self.report()['decision_agreement_pass'])

    def test_missing_output_usage_fails(self):
        del self.attempt['usage']['output_tokens']
        refresh(self.attempt)
        report = self.report()
        self.assertIsNone(report['total']['output_ratio'])
        self.assertIsNone(report['output_pass'])
        self.assertEqual(report['passed'], 0)

    def test_output_includes_reasoning_once(self):
        self.attempt['usage']['output_tokens_details']['reasoning_tokens'] = 35
        refresh(self.attempt)
        report = self.report()
        self.assertEqual(report['total']['output_tokens'], 40)
        self.assertEqual(report['passed'], 1)

    def test_output_above_cap_fails(self):
        self.attempt['usage']['output_tokens'] = 41
        refresh(self.attempt)
        self.assertEqual(self.report()['output_pass'], 0)

    def test_reasoning_cannot_exceed_total_output(self):
        self.attempt['usage']['output_tokens_details']['reasoning_tokens'] = 41
        refresh(self.attempt)
        self.assertIsNone(self.report()['output_pass'])
        self.assertEqual(self.report()['passed'], 0)

    def test_per_call_rates(self):
        self.change('matter_id', 'M2')
        row = self.report()['calls'][0]
        self.assertEqual((row['update_target_rate'], row['update_rate'], row['matter_id_rate'], row['decision_agreement_rate']), (1, 1, 0, 0))
        self.assertEqual(row['observation_coverage_rate'], 1)

    def test_noise_threshold_boundary(self):
        # Fifty observations, one incorrect decision: exactly two percentage points.
        full = self.record['reference_full']
        full['observations'] = [dict(full['observations'][0], source_index=i) for i in range(50)]
        self.record['obs_in'] = deepcopy(full['observations'])
        delta = compare.load('delta_codec').to_delta(full, self.record['obs_in'], self.record['work'])
        delta['observations'][0]['decision']['matter_id'] = 'M2'
        refresh(self.attempt, delta)
        self.assertEqual(self.report()['decision_agreement_pass'], 1)
        delta['observations'][1]['decision']['matter_id'] = 'M2'
        refresh(self.attempt, delta)
        self.assertEqual(self.report()['decision_agreement_pass'], 0)

    def test_valid_followup_is_open_not_decoder_error(self):
        refresh(self.attempt, {'observations': [], 'open_ids': ['W1'], 'work_results': None, 'unchanged_work_indices': None})
        report = self.report()
        row = report['calls'][0]
        self.assertEqual((row['errors'], row['decoder_errors'], row['decoded_schema_ok'], row['followup']), (0, 0, 1, 1))
        self.assertEqual(report['passed'], 0)
        self.assertEqual(report['next_round']['reserved_micro_usd'], 160000)
        self.assertIsNone(report['next_round']['added_opened_input_tokens'])
        self.assertEqual(report['next_round']['executed'], 0)

    def test_missing_final_observation_decoder_error(self):
        delta = json.loads(self.attempt['text'])
        delta['observations'] = []
        refresh(self.attempt, delta)
        report = self.report()
        self.assertEqual(report['total']['decoder_errors'], 1)
        self.assertEqual(report['passed'], 0)

    def test_duplicate_source_index_decoder_error(self):
        delta = json.loads(self.attempt['text'])
        delta['observations'] *= 2
        refresh(self.attempt, delta)
        self.assertEqual(self.report()['total']['decoder_errors'], 1)

    def test_boolean_is_not_integer(self):
        self.change('update', 1)
        report = self.report()
        self.assertEqual(report['calls'][0]['delta_schema_ok'], 0)
        self.assertFalse(compare.equal({'x': [False]}, {'x': [0]}))
        self.assertEqual(report['passed'], 0)

    def test_duplicate_attempt_even_identical_fails(self):
        report = self.report(events=[self.reservation, self.attempt, deepcopy(self.attempt)])
        self.assertEqual(report['total']['duplicate_attempts'], 1)
        self.assertEqual(report['passed'], 0)

    def test_conflicting_duplicate_attempt_fails(self):
        other = deepcopy(self.attempt)
        other['status'] = 'error'
        self.assertEqual(self.report(events=[self.reservation, self.attempt, other])['passed'], 0)

    def test_duplicate_requests_fail(self):
        report = compare.compare_records([self.record, deepcopy(self.record)], [self.reservation, self.attempt], self.controls)
        self.assertEqual(report['total']['global_errors'], 1)
        self.assertEqual(report['passed'], 0)

    def test_missing_attempt_fails(self):
        report = self.report(events=[self.reservation])
        self.assertEqual(report['total']['pending_reservations'], 1)
        self.assertEqual(report['passed'], 0)

    def test_missing_reservation_fails(self):
        self.assertEqual(self.report(events=[self.attempt])['passed'], 0)

    def test_zero_reservation_fails(self):
        self.reservation['reserved_micro_usd'] = 0
        self.assertEqual(self.report()['passed'], 0)

    def test_error_attempt_not_accepted(self):
        self.attempt['status'] = 'error'
        self.assertEqual(self.report()['passed'], 0)

    def test_unknown_identity_fails(self):
        other = deepcopy(self.attempt)
        other.update(job_id='other', replay_id='other:0:delta-v2')
        self.assertEqual(self.report(events=[self.reservation, self.attempt, other])['passed'], 0)

    def test_raw_usage_conflict_fails(self):
        self.attempt['usage']['output_tokens'] = 39
        self.assertEqual(self.report()['passed'], 0)

    def test_saved_cost_conflict_fails(self):
        self.attempt['actual_micro_usd'] += 1
        self.assertEqual(self.report()['passed'], 0)

    def test_cache_write_cost_included(self):
        self.attempt['usage']['input_tokens_details'] = {'cached_tokens': 10, 'cache_write_tokens': 30}
        refresh(self.attempt)
        report = self.report()
        self.assertEqual(report['total']['actual_micro_usd'], 60 * 2 + 10 * .1 + 30 * 2.5 + 40 * 10)
        self.assertEqual(report['passed'], 1)

    def test_lifecycle_mismatch_reported_without_new_gate(self):
        delta = json.loads(self.attempt['text'])
        delta['work_results'][0]['result']['action'] = 'reopen'
        refresh(self.attempt, delta)
        report = self.report()
        self.assertEqual(report['total']['lifecycle_positive_recall'], 0)
        self.assertEqual(report['total']['additional_flags'], 1)
        self.assertEqual(report['passed'], 1)

    def test_reference_not_final_fails(self):
        self.record['reference_full']['open_ids'] = ['W1']
        self.assertEqual(self.report()['passed'], 0)

    def test_missing_reference_schema_fails_closed(self):
        del self.record['reference_schema']
        self.assertEqual(self.report()['passed'], 0)

    def test_null_reference_usage_fails_closed(self):
        self.record['reference_usage'] = None
        self.assertIsNone(self.report()['output_pass'])
        self.assertEqual(self.report()['passed'], 0)

    def test_decoded_original_schema_is_checked(self):
        self.record['reference_schema']['properties']['observations']['items']['properties']['matter_id']['enum'] = ['M1']
        self.change('matter_id', 'M2')
        report = self.report()
        self.assertEqual(report['calls'][0]['delta_schema_ok'], 1)
        self.assertEqual(report['calls'][0]['decoded_schema_ok'], 0)
        self.assertEqual(report['passed'], 0)

    def test_empty_selection_is_not_success(self):
        self.assertEqual(compare.compare_records([], [], self.controls)['passed'], 0)


if __name__ == '__main__':
    unittest.main()
