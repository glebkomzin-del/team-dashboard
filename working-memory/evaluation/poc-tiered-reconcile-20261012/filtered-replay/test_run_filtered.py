"""Synthetic offline runner checks: budget/validity/raw logs; no API access."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location('filtered_runner_test_module', Path(__file__).with_name('run_filtered.py'))
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


def record(variant='filtered'):
    return {'job_id': 'synthetic', 'call_index': 0, 'replay_variant': variant,
        'replay_id': 'synthetic:0:' + variant,
        'request_json': {'prompt': 'Kandidaten: synthetic', 'schema': {
            'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
            'required': ['ok'], 'additionalProperties': False},
            'max_tokens': 100, 'transport': {'reasoning_effort': 'medium'}},
        'filter_metadata': {'candidates_before': 4, 'candidates_after': 2,
            'prompt_characters_before': 40, 'prompt_characters_after': 20}}


def response(text='{"ok": true}', usage=True):
    body = {'status': 'completed', 'model': 'gpt-6.1-sol', 'service_tier': 'default',
        'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                   'content': [{'type': 'output_text', 'text': text}]}]}
    if usage:
        body['usage'] = {'input_tokens': 100, 'output_tokens': 20,
                         'input_tokens_details': {'cached_tokens': 50}}
    return {'http_status': 200, 'raw_response': json.dumps(body)}


class RunnerTests(unittest.TestCase):
    def test_dry_run_no_credentials_transport_or_printed_contents(self):
        with patch.object(runner, 'OpenAITransport', side_effect=AssertionError), patch.dict(runner.os.environ, {}, clear=True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = runner.replay([record()])
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['attempts'], 0)
        self.assertEqual(result['candidates_before'], 4)
        self.assertEqual(result['candidates_after'], 2)

    def test_payload_parameters_and_reasoning_conflict(self):
        value = record()
        payload = runner.build_request(value)
        self.assertEqual(payload['reasoning'], {'effort': 'medium'})
        self.assertEqual(payload['max_output_tokens'], 16000)
        self.assertEqual(payload['service_tier'], 'default')
        value['reference_usage'] = {'reasoning_effort': 'low'}
        with self.assertRaises(ValueError): runner.build_request(value)

    def test_duplicate_variants_are_distinct(self):
        self.assertEqual(runner.replay([record(), record('control')])['calls'], 2)
        with self.assertRaises(ValueError): runner.replay([record(), record()])

    def test_budget_stops_before_send(self):
        calls = []
        result = runner.replay([record()], max_micro_usd=1,
            transport=lambda payload: calls.append(payload), writer=io.StringIO())
        self.assertEqual(calls, [])
        self.assertEqual(result['stopped'], 'estimated_budget')

    def test_unknown_cost_stops_full_reservation_and_keeps_raw(self):
        logs, calls = io.StringIO(), []
        raw = response(usage=False)
        def transport(payload):
            calls.append(payload)
            return raw
        result = runner.replay([record(), record('control')], transport=transport, writer=logs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['stopped'], 'uncertain_budget')
        self.assertEqual(result['budget_charged_micro_usd'], runner.estimate(calls[0])['estimated_micro_usd'])
        self.assertEqual(json.loads(logs.getvalue())['raw_response'], raw['raw_response'])

    def test_schema_error_logged_without_retry(self):
        logs, calls = io.StringIO(), []
        def transport(payload):
            calls.append(payload)
            return response('{"ok": "incorrect"}')
        result = runner.replay([record()], transport=transport, writer=logs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['failed_calls'], 1)
        self.assertEqual(json.loads(logs.getvalue())['status'], 'content_error')
        self.assertEqual(result['actual_micro_usd'], 305)

    def test_transport_failure_without_retry(self):
        calls = []
        def transport(payload):
            calls.append(payload)
            raise TimeoutError('synthetic')
        result = runner.replay([record()], transport=transport, writer=io.StringIO())
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['unknown_cost_attempts'], 1)
        self.assertEqual(result['failed_calls'], 1)

    def test_actual_overage_stops(self):
        calls = []
        def transport(payload):
            calls.append(payload)
            body = json.loads(response()['raw_response'])
            body['usage']['output_tokens'] = 100000
            return {'http_status': 200, 'raw_response': json.dumps(body)}
        result = runner.replay([record(), record('control')], max_micro_usd=200000,
                               transport=transport, writer=io.StringIO())
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['stopped'], 'actual_budget')

    def test_sse_raw_retention(self):
        raw = response()
        body = json.loads(raw['raw_response'])
        raw['raw_response'] = 'data: ' + json.dumps({'type': 'response.completed', 'response': body}) + '\n\n'
        logs = io.StringIO()
        result = runner.replay([record()], transport=lambda p: raw, writer=logs)
        self.assertEqual(result['failed_calls'], 0)
        self.assertEqual(json.loads(logs.getvalue())['raw_response'], raw['raw_response'])

    def test_cli_dry_run_and_execute_preflight_without_credentials(self):
        # Temporary files stay in the only authorized package directory.
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            requests = Path(directory) / 'requests.jsonl'
            requests.write_text(json.dumps(record()) + '\n')
            result_path = Path(directory) / 'results.jsonl'
            with patch.object(runner, 'OpenAITransport', side_effect=AssertionError), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(['--requests', str(requests)]), 0)
            self.assertFalse(result_path.exists())
            # Exclusive preflight must reject an existing cost ledger before credentials.
            result_path.write_text('existing')
            with patch.object(runner, 'OpenAITransport', side_effect=AssertionError), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(['--requests', str(requests), '--results', str(result_path), '--execute']), 1)
            self.assertEqual(result_path.read_text(), 'existing')

    def test_selection_group_cap_blocks_before_execute_credentials(self):
        value = record('control')
        value['request_json']['max_tokens'] = 128000
        value['selection_budget'] = {'filtered_cap_micro_usd': 2500000,
                                     'control_cap_micro_usd': 950000, 'feasible': True}
        dry = runner.replay([value])
        self.assertEqual(dry['budget_blocked'], 1)
        self.assertEqual(dry['calls'], 1)
        calls = []
        execution = runner.replay([value], transport=lambda p: calls.append(p), writer=io.StringIO())
        self.assertEqual(calls, [])
        self.assertEqual(execution['stopped'], 'selection_budget')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            requests = Path(directory) / 'requests.jsonl'
            results = Path(directory) / 'results.jsonl'
            requests.write_text(json.dumps(value) + '\n')
            with patch.object(runner, 'OpenAITransport', side_effect=AssertionError), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(['--execute', '--requests', str(requests), '--results', str(results)]), 1)
            self.assertFalse(results.exists())

    def test_adjusted_control_cap_allows_plan_and_rejects_overage(self):
        # This synthetic reservation exceeds the former cap but fits the authorized cap.
        # Execution is simulated exclusively with a mock; no CLI --execute or API call.
        value = record('control')
        value['request_json']['max_tokens'] = 85000
        value['selection_budget'] = {'filtered_cap_micro_usd': 2500000,
                                     'control_cap_micro_usd': 950000, 'feasible': False}
        self.assertEqual(runner.replay([value])['budget_blocked'], 0)
        sent = []
        def transport(payload):
            sent.append(payload)
            return response()
        execution = runner.replay([value], transport=transport, writer=io.StringIO())
        self.assertEqual(execution['stopped'], 'end')
        self.assertEqual(execution['attempts'], 1)
        self.assertEqual(len(sent), 1)

        # A feasibility flag cannot override an over-budget or unknown reservation.
        value['request_json']['max_tokens'] = 95000
        value['selection_budget']['feasible'] = True
        sent.clear()
        self.assertEqual(runner.replay([value])['budget_blocked'], 1)
        execution = runner.replay([value], transport=transport, writer=io.StringIO())
        self.assertEqual(execution['stopped'], 'selection_budget')
        self.assertEqual(execution['attempts'], 0)
        self.assertEqual(sent, [])
        with patch.object(runner.common, 'read_jsonl', return_value=iter([value])), patch.object(runner, 'OpenAITransport', side_effect=AssertionError), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main([]), 2)
        for invalid_cap in (None, 950001):
            with self.subTest(control_cap=invalid_cap):
                value['selection_budget']['control_cap_micro_usd'] = invalid_cap
                with self.assertRaises(ValueError):
                    runner.replay([value], transport=transport, writer=io.StringIO())
                self.assertEqual(sent, [])

    def test_cache_write_usage_and_output_reasoning_once(self):
        usage = {'input_tokens': 36808, 'output_tokens': 3152,
                 'input_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 36805},
                 'output_tokens_details': {'reasoning_tokens': 3000}}
        self.assertEqual(runner.common.usage_micro_usd(usage, 'gpt-6.1-sol'), 123539)
        usage['input_tokens_details'] = {'cached_tokens': 1, 'cache_write_tokens': 1}
        usage['input_tokens'] = 3
        usage['output_tokens'] = 0
        self.assertEqual(runner.common.usage_micro_usd(usage, 'gpt-6.1-sol'), 5)

    def test_invalid_usage_stays_unknown(self):
        base = {'input_tokens': 3, 'output_tokens': 2,
                'input_tokens_details': {'cached_tokens': 1, 'cache_write_tokens': 1}}
        for details in (None, {'cached_tokens': 2, 'cache_write_tokens': 2},
                        {'cache_write_tokens': -1}, {'cache_write_tokens': True},
                        {'cached_tokens': '1'}, {'cache_write_tokens': 1.0}):
            with self.subTest(details=details):
                usage = dict(base, input_tokens_details=details)
                self.assertIsNone(runner.common.usage_micro_usd(usage, 'gpt-6.1-sol'))
        for field, value in (('input_tokens', True), ('output_tokens', -1),
                             ('input_tokens', None), ('output_tokens', 2.5)):
            self.assertIsNone(runner.common.usage_micro_usd(dict(base, **{field: value}), 'gpt-6.1-sol'))
        self.assertIsNone(runner.common.usage_micro_usd(base, 'unknown'))

    def test_explicit_cache_payload_both_variants_and_reservation(self):
        for variant in ('filtered', 'control'):
            payload = runner.build_request(record(variant))
            self.assertEqual(payload['prompt_cache_options'], {'mode': 'explicit'})
            self.assertNotIn('breakpoints', payload['prompt_cache_options'])
            reservation = runner.estimate(payload)
            tokens = reservation['estimated_input_tokens']
            self.assertEqual(reservation['estimated_micro_usd'],
                             (tokens * 5 + 1) // 2 + 160000)

    def test_known_cache_write_cost_continues_without_retry(self):
        raw = response()
        body = json.loads(raw['raw_response'])
        body['usage'] = {'input_tokens': 36808, 'output_tokens': 3152,
                         'input_tokens_details': {'cache_write_tokens': 36805}}
        raw['raw_response'] = json.dumps(body)
        calls = []
        def transport(payload):
            calls.append(payload)
            return raw
        result = runner.replay([record(), record('control')], transport=transport, writer=io.StringIO())
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['actual_micro_usd'], 247078)
        self.assertEqual(result['unknown_cost_attempts'], 0)
        self.assertEqual(result['stopped'], 'end')

    def test_invalid_write_cost_stops_after_one_attempt(self):
        raw = response()
        body = json.loads(raw['raw_response'])
        body['usage']['input_tokens_details']['cache_write_tokens'] = 101
        raw['raw_response'] = json.dumps(body)
        calls = []
        def transport(payload):
            calls.append(payload)
            return raw
        result = runner.replay([record(), record('control')], transport=transport, writer=io.StringIO())
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['stopped'], 'uncertain_budget')

    def test_skip_multiple_paid_failure_ledgers_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / 'one.jsonl', Path(directory) / 'two.jsonl']
            for path, variant in zip(paths, ('filtered', 'control')):
                paid = record(variant)
                paid['status'] = 'transport_error'
                path.write_text(json.dumps(paid) + '\n' + json.dumps(paid) + '\n')
            snapshots = [path.read_bytes() for path in paths]
            for unused in range(2):
                calls = []
                result = runner.replay([record(), record('control')], skip_done=paths,
                    transport=lambda payload: calls.append(payload), writer=io.StringIO())
                self.assertEqual(calls, [])
                self.assertEqual(result['skipped_done_calls'], 2)
                self.assertEqual(result['calls'], 0)
            self.assertEqual([path.read_bytes() for path in paths], snapshots)

    def test_skip_occurs_before_selection_gate(self):
        value = record('control')
        value['request_json']['max_tokens'] = 128000
        value['selection_budget'] = {'control_cap_micro_usd': 950000}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'paid.jsonl'
            path.write_text(json.dumps(value) + '\n')
            calls = []
            result = runner.replay([value], skip_done=[path], transport=lambda p: calls.append(p), writer=io.StringIO())
            self.assertEqual(result['budget_blocked'], 0)
            self.assertEqual(result['skipped_done_calls'], 1)
            self.assertEqual(calls, [])

    def test_skip_unpaid_identity_still_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'paid.jsonl'
            path.write_text(json.dumps(record('control')) + '\n')
            calls = []
            def transport(payload):
                calls.append(payload)
                return response()
            result = runner.replay([record()], skip_done=[path], transport=transport, writer=io.StringIO())
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['skipped_done_calls'], 0)

    def test_invalid_paid_evidence_fails_closed(self):
        invalid = [dict(record(), replay_id='different'), dict(record(), job_id='other'),
                   dict(record(), call_index=True), dict(record(), replay_variant='other'),
                   dict(record(), variant='control'), {'replay_id': 'synthetic:0:filtered'}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'paid.jsonl'
            for evidence in invalid + [None, '{bad', '{"job_id": "a", "job_id": "b"}']:
                path.write_text((evidence if isinstance(evidence, str) else json.dumps(evidence)) + '\n')
                calls = []
                with self.assertRaises(ValueError):
                    runner.replay([record()], skip_done=[path], transport=lambda p: calls.append(p), writer=io.StringIO())
                self.assertEqual(calls, [])
            with self.assertRaises(OSError): runner.common.completed_replay_ids([path.with_name('missing')])

    def test_all_input_identity_validation_precedes_transport_and_skip(self):
        invalid = dict(record('control'), replay_id='synthetic:0:filtered')
        calls = []
        with self.assertRaises(ValueError):
            runner.replay([record(), invalid], limit=1, transport=lambda p: calls.append(p), writer=io.StringIO())
        self.assertEqual(calls, [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'paid.jsonl'
            path.write_text(json.dumps(record()) + '\n')
            with self.assertRaises(ValueError): runner.replay([record(), record()], skip_done=[path])
            value = record()
            value['request_json']['schema']['unsupported'] = True
            with self.assertRaises(ValueError): runner.replay([value], skip_done=[path])

    def test_cli_repeatable_multi_path_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            request_path = Path(directory) / 'requests.jsonl'
            request_path.write_text(json.dumps(record()) + '\n' + json.dumps(record('control')) + '\n')
            paths = [Path(directory) / f'{index}.jsonl' for index in range(3)]
            for path, value in zip(paths, (record(), record('control'), record())):
                path.write_text(json.dumps(value) + '\n')
            argv = ['--requests', str(request_path), '--skip-done', str(paths[0]), str(paths[1]),
                    '--skip-done', str(paths[2])]
            with patch.object(runner, 'OpenAITransport', side_effect=AssertionError), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(argv), 0)
            summary = json.loads(output.getvalue())
            self.assertEqual(summary['skipped_done_calls'], 2)
            self.assertEqual(summary['calls'], 0)
            request_path.write_text(json.dumps(record()) + '\n' + json.dumps(dict(record('control'), replay_id='wrong')) + '\n')
            with patch.object(runner, 'OpenAITransport', side_effect=AssertionError), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(argv + ['--limit', '0']), 1)

    def test_invalid_schema_prevents_transport(self):
        value = record()
        value['request_json']['schema']['unsupported'] = True
        with self.assertRaises(ValueError): runner.build_request(value)


if __name__ == '__main__':
    unittest.main()
