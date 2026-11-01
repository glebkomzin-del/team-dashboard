"""Synthetic offline contracts; no provider, credentials, or filesystem writes."""
import contextlib
import copy
import http.client
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

spec = importlib.util.spec_from_file_location('replay_stage', Path(__file__).with_name('replay_stage.py'))
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)

SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
    'required': ['ok'], 'additionalProperties': False}


def record(index=0, stage='extract', length=10):
    return {'job_id': 'synthetic', 'call_index': index, 'stage': stage,
        'request_json': {'prompt': 'x' * length, 'schema': copy.deepcopy(SCHEMA), 'max_tokens': 10,
            'model': 'gpt-6.1-sol'}, 'reference_model': 'gpt-6.1-sol',
        'reference_stop_reason': 'end_turn', 'reference_text': '{"ok":true}'}


def records(count=10):
    return [record(i, stage, i + 1) for stage in replay.STAGES for i in range(count)]


def body(answer='{"ok": true}', usage=None):
    return {'model': 'gpt-6-luna', 'service_tier': 'default', 'status': 'completed',
        'usage': {'input_tokens': 100, 'output_tokens': 20,
            'input_tokens_details': {'cached_tokens': 10, 'cache_write_tokens': 20}} if usage is None else usage,
        'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': answer}]}]}


def sse(response):
    return 'event: response.completed\ndata: ' + json.dumps(
        {'type': 'response.completed', 'response': response}) + '\n\ndata: [DONE]\n\n'


class MemoryWriter(io.StringIO):
    """Synthetic durable boundary: records every flush before next transport."""
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1


class MockTransport:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        return next(self.outputs)


class SelectionTests(unittest.TestCase):
    def test_stratified_extremes_and_middle(self):
        selected = replay.select_records(records())
        for stage in replay.STAGES:
            self.assertEqual([r['call_index'] for r in selected if r['stage'] == stage], [0, 1, 4, 5, 8, 9])

    def test_stratified_six_covers_all(self):
        self.assertEqual(len(replay.select_records(records(6))), 12)

    def test_deterministic_tie_order(self):
        source = [record(i, length=1) for i in reversed(range(8))]
        self.assertEqual([r['call_index'] for r in replay.select_records(source, 'extract')], [0, 1, 3, 4, 6, 7])

    def test_smallest_each_stage(self):
        selected = replay.select_records(records(), select='smallest:2')
        self.assertEqual([(r['stage'], r['call_index']) for r in selected],
            [('extract', 0), ('extract', 1), ('gate', 0), ('gate', 1)])

    def test_insufficient_coverage(self):
        with self.assertRaises(ValueError):
            replay.select_records(records(5))

    def test_duplicate_source(self):
        with self.assertRaises(ValueError):
            replay.select_records([record(), record()], 'extract', 'all')

    def test_invalid_identity(self):
        for change in ({'call_index': True}, {'job_id': ''}, {'stage': 'compact'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay.select_records([{**record(), **change}], 'extract', 'all')

    def test_selection_list_exact_coverage(self):
        chosen = [{'job_id': 'synthetic', 'call_index': 8, 'stage': s} for s in replay.STAGES]
        self.assertEqual([r['call_index'] for r in replay.select_records(records(), select=chosen)], [8, 8])

    def test_missing_duplicate_or_wrong_stage_selection(self):
        for selection in ([record(99)], [record(), record()], [record(0, 'gate')]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                replay.select_records(records(), stage='extract', select=selection)

    def test_selection_both_requires_both(self):
        with self.assertRaises(ValueError):
            replay.select_records(records(), select=[record()])

    def test_identity_file_selection(self):
        with patch.object(replay.common, 'read_jsonl', return_value=iter([record(), record(stage='gate')])):
            self.assertEqual(len(replay.select_records(records(), select='identities.jsonl')), 2)

    def test_limit_never_truncates_selection(self):
        with self.assertRaises(ValueError):
            replay.select_records(records(), limit=11)
        self.assertEqual(len(replay.select_records(records(), limit=12)), 12)

    def test_auto_excludes_foreign_missing_and_invalid_references(self):
        foreign, missing, invalid = record(90), record(91), record(92)
        foreign['request_json']['model'] = 'gpt-5.6-terra'
        missing['reference_stop_reason'] = None
        invalid['reference_text'] = '{"ok":1}'
        source = records() + [foreign, missing, invalid]
        self.assertEqual(len(replay.select_records(source)), 12)
        counts = replay.eligibility_counts(source)
        self.assertEqual(counts['stages']['extract'], {'total': 13, 'eligible': 10, 'excluded': 3})

    def test_explicit_ineligible_reference_is_blocked(self):
        for change in ({'reference_model': None}, {'reference_stop_reason': None},
                       {'reference_text': None}, {'reference_text': '{"ok":1}'}):
            bad = {**record(), **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay.select_records([bad], 'extract', 'all')

    def test_successful_flag_without_sol_reference_is_blocked(self):
        bad = record()
        bad['reference_model'] = 'gpt-5.6-terra'
        bad['reference_stop_reason'] = 'end_turn'
        with self.assertRaises(ValueError):
            replay.select_records([bad], 'extract', 'all')


class PayloadBudgetTests(unittest.TestCase):
    def test_production_request_shape(self):
        request = replay.build_request(record())
        self.assertEqual(request, {'model': 'gpt-6-luna',
            'input': [{'role': 'user', 'content': 'x' * 10}],
            'reasoning': {'effort': 'medium'}, 'truncation': 'disabled', 'service_tier': 'default',
            'text': {'format': {'type': 'json_schema', 'name': 'meeting_result', 'strict': True, 'schema': SCHEMA}},
            'max_output_tokens': 16000, 'stream': True, 'store': False,
            'prompt_cache_options': {'mode': 'explicit'}})

    def test_explicit_reference_reasoning(self):
        source = record()
        source['reference_usage'] = {'reasoning_effort': 'high'}
        self.assertEqual(replay.build_request(source)['reasoning']['effort'], 'high')
        source['request_json']['transport'] = {'reasoning_effort': 'low'}
        with self.assertRaises(ValueError):
            replay.build_request(source)

    def test_invalid_reasoning_or_schema_or_allowance(self):
        cases = []
        for field, value in [('max_tokens', True), ('max_tokens', 0), ('schema', {'format': 'unknown'})]:
            source = record()
            source['request_json'][field] = value
            cases.append(source)
        source = record()
        source['reference_usage'] = {'reasoning_effort': []}
        cases.append(source)
        for source in cases:
            with self.subTest(source=source), self.assertRaises(ValueError):
                replay.build_request(source)

    def test_utf8_framing_cache_write_reserve(self):
        source = record()
        source['request_json']['prompt'] = '\u00e4\U0001f600'
        payload = replay.build_request(source)
        prediction = replay.estimate(payload)
        self.assertEqual(prediction['prompt_utf8_bytes'], 6)
        expected = 6 + len(json.dumps(SCHEMA, ensure_ascii=False).encode()) + 4096
        self.assertEqual(prediction['estimated_input_tokens'], expected)
        self.assertEqual(prediction['estimated_micro_usd'], replay.common.usage_micro_usd(
            {'input_tokens': expected, 'input_tokens_details': {'cache_write_tokens': expected},
             'output_tokens': 16000}, 'gpt-6-luna'))

    def test_all_four_cache_rates(self):
        self.assertEqual(replay.common.usage_micro_usd({'input_tokens': 100,
            'output_tokens': 100, 'input_tokens_details': {'cached_tokens': 20, 'cache_write_tokens': 40}},
            'gpt-6-luna'), 60)

    def test_cap_preflight_zero_calls_and_no_write(self):
        transport, writer = MockTransport([]), MemoryWriter()
        with self.assertRaises(ValueError):
            replay.replay(records(), max_micro_usd=1, transport=transport, writer=writer)
        self.assertEqual(transport.calls, [])
        self.assertEqual(writer.getvalue(), '')

    def test_late_duplicate_preflight_zero_calls(self):
        source = records() + [record()]
        transport = MockTransport([])
        with self.assertRaises(ValueError):
            replay.replay(source, transport=transport, writer=MemoryWriter())
        self.assertEqual(transport.calls, [])


class ResponseTests(unittest.TestCase):
    def run_replay(self, raw_result, count=2):
        transport = MockTransport([raw_result] * count)
        writer = MemoryWriter()
        summary = replay.replay([record(i) for i in range(count)], stage='extract', select='all',
            transport=transport, writer=writer)
        return summary, transport, writer, [json.loads(line) for line in writer.getvalue().splitlines()]

    def test_completed_sse_and_schema(self):
        raw = sse(body())
        summary, transport, writer, saved = self.run_replay({'http_status': 200, 'raw_response': raw})
        self.assertEqual(summary['attempts'], 2)
        self.assertEqual(writer.flushes, 2)
        self.assertEqual(saved[0]['raw_response'], raw)
        self.assertEqual(saved[0]['status'], 'ok')
        self.assertEqual(saved[0]['stage'], 'extract')
        self.assertEqual(saved[0]['text'], '{"ok": true}')

    def test_schema_invalid_saved_as_error(self):
        _, _, _, saved = self.run_replay({'http_status': 200, 'raw_response': sse(body('{"ok": 1}'))}, 1)
        self.assertEqual(saved[0]['status'], 'content_error')

    def test_duplicate_json_answer_saved_as_error(self):
        _, _, _, saved = self.run_replay({'http_status': 200, 'raw_response': sse(body('{"ok":true,"ok":false}'))}, 1)
        self.assertEqual(saved[0]['status'], 'content_error')

    def test_unknown_usage_stops_after_durable_save(self):
        summary, transport, writer, saved = self.run_replay({'http_status': 200, 'raw_response': sse(body(usage={}))})
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(summary['stopped'], 'uncertain_budget')
        self.assertEqual(writer.flushes, 1)
        self.assertEqual(saved[0]['status'], 'unknown_cost')
        self.assertIsNone(saved[0]['actual_micro_usd'])
        self.assertIsNotNone(saved[0]['error'])

    def test_invalid_cache_usage_unknown(self):
        summary, transport, _, _ = self.run_replay({'http_status': 200, 'raw_response': sse(body(usage={
            'input_tokens': 10, 'output_tokens': 1, 'input_tokens_details': {'cached_tokens': 11}}))})
        self.assertEqual(summary['unknown_cost_attempts'], 1)
        self.assertEqual(len(transport.calls), 1)

    def test_partial_body_transport_error_saved_no_retry(self):
        raw = 'data: {"type":"response.output_text.delta","delta":"partial"}\n\n'
        summary, transport, writer, saved = self.run_replay({'http_status': 200, 'raw_response': raw,
            'transport_error': 'synthetic timeout', 'exception_type': 'TimeoutError'})
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(writer.flushes, 1)
        self.assertEqual(saved[0]['raw_response'], raw)
        self.assertEqual(saved[0]['error']['type'], 'TimeoutError')
        self.assertEqual(summary['stopped'], 'uncertain_budget')

    def test_http_error_body_saved(self):
        raw = '{"error":{"code":"synthetic"}}'
        _, _, writer, saved = self.run_replay({'http_status': 429, 'raw_response': raw,
            'http_error': 'HTTP 429', 'body_read_error': 'partial'}, 1)
        self.assertEqual(saved[0]['status'], 'http_error')
        self.assertEqual(saved[0]['raw_response'], raw)
        self.assertEqual(saved[0]['error']['body_read_error'], 'partial')
        self.assertEqual(writer.flushes, 1)

    def test_missing_http_status_not_success(self):
        _, _, _, saved = self.run_replay({'raw_response': sse(body())}, 1)
        self.assertEqual(saved[0]['status'], 'http_error')

    def test_duplicate_terminal_and_missing_terminal(self):
        for raw in (sse(body()) + sse(body()), 'data: {}\n\n'):
            _, error = replay.response_body(raw)
            self.assertIsNotNone(error)

    def test_write_failure_stops_before_next_call(self):
        writer = MemoryWriter()
        writer.flush = MagicMock(side_effect=OSError('synthetic flush failure'))
        transport = MockTransport([{'http_status': 200, 'raw_response': sse(body())}] * 2)
        with self.assertRaises(OSError):
            replay.replay([record(0), record(1)], stage='extract', select='all', transport=transport, writer=writer)
        self.assertEqual(len(transport.calls), 1)

    def test_unexpected_model_unknown_cost(self):
        response = body()
        response['model'] = 'other'
        summary, transport, _, _ = self.run_replay({'http_status': 200, 'raw_response': sse(response)})
        self.assertEqual(summary['stopped'], 'uncertain_budget')
        self.assertEqual(len(transport.calls), 1)


class CLITests(unittest.TestCase):
    def test_dry_run_no_credentials_no_transport(self):
        with patch.object(replay.common, 'read_jsonl', return_value=iter(records())), \
             patch.object(replay, 'OpenAITransport', side_effect=AssertionError('transport constructed')), \
             patch.object(replay.os, 'environ', {}), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(replay.main([]), 0)
        summary = json.loads(out.getvalue())
        self.assertEqual(summary['mode'], 'DRY-RUN')
        self.assertEqual(summary['attempts'], 0)
        self.assertEqual(summary['selected_calls'], 12)

    def test_execute_preflight_before_constructor(self):
        with patch.object(replay.common, 'read_jsonl', return_value=iter(records())), \
             patch.object(replay, 'OpenAITransport', side_effect=AssertionError('transport constructed')), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(replay.main(['--execute', '--max-usd', '0.000001']), 1)

    def test_results_exclusive_no_calls_if_exists(self):
        transport = MockTransport([])
        path = MagicMock()
        path.open.side_effect = FileExistsError('existing')
        with patch.object(replay.common, 'read_jsonl', return_value=iter(records())), \
             patch.object(replay.common, 'output_path', return_value=path), \
             patch.object(replay, 'OpenAITransport', return_value=transport), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(replay.main(['--execute']), 1)
        path.open.assert_called_once_with('x', encoding='utf-8')
        self.assertEqual(transport.calls, [])

    def test_durable_writer_flush_then_fsync(self):
        events = []
        handle = MagicMock()
        handle.flush.side_effect = lambda: events.append('flush')
        handle.fileno.return_value = 77
        with patch.object(replay.os, 'fsync', side_effect=lambda fd: events.append(('fsync', fd))):
            replay.DurableWriter(handle).flush()
        self.assertEqual(events, ['flush', ('fsync', 77)])

    def test_transport_preserves_partial_read_without_network(self):
        fake = MagicMock()
        fake.status = 200
        fake.__iter__.side_effect = http.client.IncompleteRead(b'partial', 10)
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = fake
        with patch.object(replay.os, 'environ', {'OPENAI_API_KEY': 'synthetic-key'}), \
             patch.object(replay.urllib.request, 'build_opener', return_value=opener):
            result = replay.OpenAITransport()(replay.build_request(record()))
        self.assertEqual(result['raw_response'], 'partial')
        self.assertEqual(result['exception_type'], 'IncompleteRead')


if __name__ == '__main__':
    unittest.main()
