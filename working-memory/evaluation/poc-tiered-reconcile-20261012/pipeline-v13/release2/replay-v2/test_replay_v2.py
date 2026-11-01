"""Synthetic offline checks; no credentials, provider calls or fixture contents.

Question: can replay spend or resend without durable, valid budget evidence?
Criterion: reservation precedes transport; paid identities never retry; unknown
usage blocks and all costs count. Scope: pure runner with in-memory transport
and ledger. A failure leaves the corresponding runner acceptance open.
Run: python3 -I -B test_replay_v2.py
"""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('synthetic_replay_v2', ROOT / 'replay_v2.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
SCHEMA = {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}


def record(index=0):
    return {'job_id': 'synthetic', 'call_index': index,
            'replay_id': f'synthetic:{index}:delta-v2',
            'request_json': {'prompt': 'new', 'schema': copy.deepcopy(SCHEMA), 'max_tokens': 16000},
            'reference_request_json': {'prompt': 'old', 'schema': copy.deepcopy(SCHEMA), 'max_tokens': 12000},
            'reference_usage': {'input_tokens': 100}, 'max_output_tokens': 16000}


def result(usage=None, status='completed', http=200):
    body = {'model': 'gpt-6.1-sol', 'service_tier': 'default', 'status': status,
            'usage': {'input_tokens': 100, 'output_tokens': 2} if usage is None else usage,
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': '{}'}]}]}
    raw = 'data: ' + json.dumps({'type': 'response.' + status, 'response': body}) + '\n\n'
    return {'http_status': http, 'raw_response': raw}


def reservation(index=0, amount=170490):
    return dict((k, v) for k, v in record(index).items() if k in ('job_id', 'call_index', 'replay_id')) | {
        'record_type': 'reservation', 'reserved_micro_usd': amount}


class ReplayTests(unittest.TestCase):
    def test_request_contract_and_reference_cap(self):
        value = record()
        value['reference_request_json']['max_tokens'] = 20000
        value['max_output_tokens'] = 20000
        value['request_json']['max_tokens'] = 20000
        payload = runner.build_request(value)
        self.assertEqual(payload['model'], 'gpt-6.1-sol')
        self.assertEqual(payload['reasoning'], {'effort': 'medium'})
        self.assertEqual(payload['service_tier'], 'default')
        self.assertEqual(payload['prompt_cache_options'], {'mode': 'explicit'})
        self.assertEqual(payload['max_output_tokens'], 20000)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['truncation'], 'disabled')
        for cap in (15999, 19999, 20001, True, 128001):
            invalid = copy.deepcopy(value)
            invalid['max_output_tokens'] = cap
            invalid['request_json']['max_tokens'] = cap
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                runner.build_request(invalid)
        for source_cap in (16000, 20001, None):
            invalid = copy.deepcopy(value)
            invalid['request_json']['max_tokens'] = source_cap
            with self.subTest(source_cap=source_cap), self.assertRaises(ValueError):
                runner.build_request(invalid)

    def test_identity_requires_positive_agreement(self):
        for changes in ({'replay_id': 'synthetic:0:delta'}, {'call_index': True}, {'job_id': ''}):
            with self.subTest(fields=list(changes)), self.assertRaises(ValueError):
                runner.identity(record() | changes)
        with self.assertRaises(ValueError):
            runner.replay([record(), record()])

    def test_anchor_positive_utf8_changes_and_highest_input_rate(self):
        value = record()
        value['request_json']['prompt'] = 'oldé'
        plan = runner.estimate(value)
        expected_input = 100 + 2 + 4096
        self.assertEqual(plan['reserved_input_tokens'], expected_input)
        self.assertEqual(plan['reserved_micro_usd'], expected_input * 2.5 + 16000 * 10)
        self.assertEqual(plan['estimate_method'], 'observed_reference_plus_positive_utf8_deltas')
        value['request_json']['prompt'] = ''
        self.assertEqual(runner.estimate(value)['reserved_input_tokens'], 100 + 4096)
        value['reference_usage']['input_tokens'] = 0
        with self.assertRaises(ValueError):
            runner.estimate(value)

    def test_schema_growth_and_declared_anchor_are_counted(self):
        value = record()
        value['request_json']['schema']['description'] = 'é'
        old = len(json.dumps(SCHEMA, ensure_ascii=False).encode('utf-8'))
        new = len(json.dumps(value['request_json']['schema'], ensure_ascii=False).encode('utf-8'))
        self.assertEqual(runner.estimate(value)['reserved_input_tokens'], 100 + new - old + 4096)
        value['input_tokens_estimate'] = 9000
        self.assertEqual(runner.estimate(value)['reserved_input_tokens'], 9000)

    def test_actual_split_rates_and_round_up(self):
        usage = {'input_tokens': 100, 'output_tokens': 3,
                 'input_tokens_details': {'cached_tokens': 20, 'cache_write_tokens': 30}}
        self.assertEqual(runner.common.usage_micro_usd(usage, 'gpt-6.1-sol'), 207)
        self.assertEqual(runner.common.usage_micro_usd({'input_tokens': 1, 'output_tokens': 0,
                         'input_tokens_details': {'cached_tokens': 1}}, 'gpt-6.1-sol'), 1)

    def test_invalid_usage_fails_closed(self):
        bad = [{}, {'input_tokens': True, 'output_tokens': 0},
               {'input_tokens': -1, 'output_tokens': 0},
               {'input_tokens': 1, 'output_tokens': 0, 'input_tokens_details': None},
               {'input_tokens': 2, 'output_tokens': 0, 'input_tokens_details': {'cached_tokens': 2, 'cache_write_tokens': 1}},
               {'input_tokens': 2, 'output_tokens': 0, 'input_tokens_details': {'cache_write_tokens': True}}]
        for usage in bad:
            with self.subTest(case=bad.index(usage)):
                self.assertIsNone(runner.common.usage_micro_usd(usage, 'gpt-6.1-sol'))

    def test_reservation_precedes_transport_and_raw_attempt_is_retained(self):
        ledger = []
        response = result()
        def transport(payload):
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]['record_type'], 'reservation')
            return response
        summary = runner.replay([record()], transport=transport, writer=ledger.append)
        self.assertEqual(summary['attempts'], 1)
        self.assertEqual(summary['actual_micro_usd'], 220)
        self.assertEqual(ledger[1]['raw_response'], response['raw_response'])
        self.assertEqual(ledger[1]['transport'], response)
        self.assertEqual(ledger[1]['status'], 'ok')
        self.assertEqual(runner.prior_state(ledger)['spent'], 220)

    def test_writer_failure_prevents_transport(self):
        transport = unittest.mock.Mock()
        with self.assertRaises(OSError):
            runner.replay([record()], transport=transport, writer=lambda _: (_ for _ in ()).throw(OSError()))
        transport.assert_not_called()
        with self.assertRaises(ValueError):
            runner.replay([record()], transport=transport)

    def test_paid_error_not_retried_on_restart(self):
        for response in (result(status='failed'), result(http=429)):
            with self.subTest(case=response['http_status']):
                ledger = []
                transport = unittest.mock.Mock(return_value=response)
                first = runner.replay([record()], transport=transport, writer=ledger.append)
                self.assertEqual(first['failed'], 1)
                self.assertEqual(transport.call_count, 1)
                restart = runner.replay([record()], transport=transport, writer=ledger.append, previous=ledger)
                self.assertEqual(restart['skipped'], 1)
                self.assertEqual(restart['attempts'], 0)
                self.assertEqual(transport.call_count, 1)

    def test_uncertain_usage_stops_remaining_calls_and_restart(self):
        ledger = []
        transport = unittest.mock.Mock(return_value=result(usage={}))
        summary = runner.replay([record(), record(1)], transport=transport, writer=ledger.append)
        self.assertEqual(summary['stopped'], 'uncertain_budget')
        self.assertEqual(summary['attempts'], 1)
        self.assertEqual(transport.call_count, 1)
        restart = runner.replay([record(), record(1)], transport=transport, writer=ledger.append, previous=ledger)
        self.assertEqual(restart['stopped'], 'uncertain_budget')
        self.assertEqual(restart['skipped'], 1)
        self.assertEqual(transport.call_count, 1)

    def test_unknown_pending_blocks_and_counts_reservation(self):
        previous = [reservation()]
        state = runner.prior_state(previous)
        self.assertEqual(state['spent'], 170490)
        self.assertTrue(state['blocked'])
        transport = unittest.mock.Mock()
        summary = runner.replay([record(), record(1)], transport=transport, writer=lambda _: None, previous=previous)
        self.assertEqual(summary['stopped'], 'uncertain_budget')
        self.assertEqual(summary['skipped'], 1)
        transport.assert_not_called()

    def test_transport_exception_is_recorded_once_and_blocks(self):
        ledger = []
        transport = unittest.mock.Mock(side_effect=OSError())
        summary = runner.replay([record(), record(1)], transport=transport, writer=ledger.append)
        self.assertEqual(summary['stopped'], 'uncertain_budget')
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[-1]['status'], 'error')

    def test_budget_hard_ceiling_and_previous_cost_included(self):
        transport = unittest.mock.Mock(return_value=result())
        for cap in (1300001, 0, True):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                runner.replay([record()], max_micro_usd=cap, transport=transport, writer=lambda _: None)
        previous = [reservation(9), reservation(9) | {'record_type': 'attempt', 'actual_micro_usd': 1200000, 'status': 'error'}]
        summary = runner.replay([record()], transport=transport, writer=lambda _: None, previous=previous)
        self.assertEqual(summary['previous_micro_usd'], 1200000)
        self.assertEqual(summary['stopped'], 'estimated_budget')
        transport.assert_not_called()

    def test_unknown_model_or_tier_prevents_further_spend(self):
        for field, value in (('model', 'other'), ('service_tier', 'flex')):
            response = result()
            body = json.loads(response['raw_response'][6:])
            body['response'][field] = value
            response['raw_response'] = 'data: ' + json.dumps(body) + '\n\n'
            ledger = []
            transport = unittest.mock.Mock(return_value=response)
            summary = runner.replay([record(), record(1)], transport=transport, writer=ledger.append)
            self.assertEqual(summary['stopped'], 'uncertain_budget')
            self.assertEqual(transport.call_count, 1)

    def test_dryrun_never_constructs_transport(self):
        with patch.object(runner, 'StreamingTransport', side_effect=AssertionError('transport forbidden')):
            summary = runner.replay([record()])
        self.assertEqual(summary['execute'], 0)
        self.assertEqual(summary['attempts'], 0)
        self.assertEqual(summary['calls'], 1)

    def test_cli_dryrun_never_constructs_transport_or_writes(self):
        output = io.StringIO()
        with patch.object(runner.common, 'read_jsonl', return_value=iter([record()])), \
                patch.object(Path, 'exists', return_value=False), \
                patch.object(runner, 'StreamingTransport', side_effect=AssertionError('transport forbidden')), \
                patch.object(runner.os, 'open', side_effect=AssertionError('write forbidden')), \
                contextlib.redirect_stdout(output):
            code = runner.main(['--requests', 'unused-synthetic-path'])
        summary = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(summary['execute'], 0)
        self.assertEqual(summary['attempts'], 0)

    def test_actual_over_reservation_blocks_next_call(self):
        ledger = []
        # A proxy is not a guaranteed bound: a surprising recorded actual cost
        # must stop further transport, even after initial plans fit the cap.
        response = result(usage={'input_tokens': 1, 'output_tokens': 120000})
        transport = unittest.mock.Mock(return_value=response)
        summary = runner.replay([record(), record(1)], transport=transport, writer=ledger.append)
        self.assertEqual(summary['stopped'], 'actual_budget')
        self.assertEqual(summary['attempts'], 1)
        self.assertEqual(summary['actual_micro_usd'], 1200002)
        self.assertEqual(transport.call_count, 1)


if __name__ == '__main__':
    unittest.main()
