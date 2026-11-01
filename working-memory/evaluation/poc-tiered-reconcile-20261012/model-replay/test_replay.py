import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('replay', ROOT / 'replay.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)

SCHEMA = {'type': 'object', 'properties': {'observations': {'type': 'array'},
    'work_results': {'type': 'object'}}, 'required': ['observations', 'work_results'],
    'additionalProperties': False}
ANSWER = {'observations': [], 'work_results': {'0': 'unchanged'}}


def request(index=0, allowance=100):
    return {'job_id': 'synthetic', 'call_index': index, 'meeting_date': '2026-10-12',
        'request_json': {'prompt': 'Synthetic only.\nDatum: 2026-10-12', 'schema': SCHEMA,
            'model': 'reference', 'max_tokens': allowance, 'scope': 'synthetic'},
        'reference_text': json.dumps(ANSWER), 'reference_usage': {}, 'reference_micro_usd': 20}


def response(input_tokens=100, output_tokens=100, answer=None, status='completed'):
    body = {'status': status, 'model': 'gpt-6-luna', 'service_tier': 'default',
        'usage': {'input_tokens': input_tokens, 'output_tokens': output_tokens},
        'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': json.dumps(ANSWER if answer is None else answer)}]}]}
    return {'http_status': 200, 'raw_response': json.dumps(body)}


class ReplayTests(unittest.TestCase):
    def run_mock(self, records, replies, budget=1500000):
        writer = io.StringIO()
        transport = mock.Mock(side_effect=replies)
        summary = replay.replay(records, max_micro_usd=budget, transport=transport, writer=writer)
        return summary, [json.loads(line) for line in writer.getvalue().splitlines()], transport

    def test_exact_request_and_generous_allowance(self):
        source = request(allowance=24000)
        payload = replay.build_request(source, 'gpt-6-luna')
        self.assertEqual(payload['input'][0]['content'], source['request_json']['prompt'])
        self.assertEqual(payload['text']['format']['schema'], SCHEMA)
        self.assertEqual(payload['max_output_tokens'], 24000)
        self.assertEqual(payload['reasoning'], {'effort': 'low'})
        self.assertEqual(payload['service_tier'], 'default')
        self.assertTrue(payload['stream'])
        self.assertFalse(payload['store'])
        self.assertEqual(replay.build_request(request(), 'gpt-6-luna')['max_output_tokens'], 16000)

    def test_dry_run_costs_no_network_or_key(self):
        with mock.patch.object(replay.urllib.request, 'build_opener', side_effect=AssertionError('network')), \
             mock.patch.object(replay.os.environ, 'get', side_effect=AssertionError('credential read')), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            summary = replay.replay([request()])
        row = json.loads(out.getvalue())
        chars = len(request()['request_json']['prompt']) + len(json.dumps(SCHEMA, ensure_ascii=False))
        self.assertEqual(row['characters'], chars)
        self.assertEqual(row['estimated_input_tokens'], __import__('math').ceil(chars / 3.6))
        self.assertEqual(row['estimated_micro_usd'], __import__('math').ceil(row['estimated_input_tokens'] * .1 + 16000 * .5))
        self.assertEqual(summary['estimated_micro_usd'], row['estimated_micro_usd'])
        self.assertEqual(summary['attempts'], 0)

    def test_cached_prices_and_rounding(self):
        usage = {'input_tokens': 1000000, 'output_tokens': 1000000,
                 'input_tokens_details': {'cached_tokens': 500000}}
        self.assertEqual(replay.common.usage_micro_usd(usage, 'gpt-6-luna'), 555000)
        self.assertEqual(replay.common.usage_micro_usd(usage, 'gpt-6.1-sol'), 11050000)
        self.assertEqual(replay.common.usage_micro_usd({'input_tokens': 1, 'output_tokens': 0}, 'gpt-6-luna'), 1)
        self.assertIsNone(replay.common.usage_micro_usd({}, 'gpt-6-luna'))
        self.assertIsNone(replay.common.usage_micro_usd({'input_tokens': True, 'output_tokens': 0}, 'gpt-6-luna'))
        usage['input_tokens_details']['cached_tokens'] = 1000001
        self.assertIsNone(replay.common.usage_micro_usd(usage, 'gpt-6-luna'))

    def test_dry_estimated_budget_and_limit(self):
        with contextlib.redirect_stdout(io.StringIO()):
            summary = replay.replay([request(), request(1)], max_micro_usd=10000)
            limited = replay.replay([request(), request(1)], limit=0)
        self.assertEqual(summary['calls'], 1)
        self.assertEqual(summary['stopped'], 'estimated_budget')
        self.assertEqual(limited['calls'], 0)

    def test_budget_stops_immediately_after_actual_cap(self):
        summary, rows, transport = self.run_mock([request(), request(1)], [response(0, 20000)], budget=10000)
        self.assertEqual(summary['stopped'], 'actual_budget')
        self.assertEqual(summary['actual_micro_usd'], 10000)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(len(rows), 1)

    def test_reservation_refuses_first_call(self):
        summary, rows, transport = self.run_mock([request()], [], budget=1)
        self.assertEqual(summary['stopped'], 'estimated_budget')
        self.assertEqual(transport.call_count, 0)
        self.assertEqual(rows, [])

    def test_transport_retry_two_only_and_full_logging(self):
        bad = {'http_status': None, 'raw_response': 'partial-SSE',
               'transport_error': 'synthetic wire failure', 'exception_type': 'TimeoutError'}
        summary, rows, transport = self.run_mock([request()], [bad, bad, bad])
        self.assertEqual(transport.call_count, 3)
        self.assertEqual([r['attempt'] for r in rows], [1, 2, 3])
        self.assertEqual(rows[0]['raw_response'], 'partial-SSE')
        self.assertEqual(rows[0]['error']['message'], 'synthetic wire failure')
        self.assertIsNone(rows[0]['actual_micro_usd'])
        self.assertEqual(summary['unknown_cost_attempts'], 3)
        self.assertGreater(summary['budget_charged_micro_usd'], 0)

    def test_retry_budget_preserves_unknown_cost(self):
        bad = {'http_status': None, 'raw_response': '', 'transport_error': 'offline'}
        summary, rows, transport = self.run_mock([request()], [bad], budget=10000)
        self.assertEqual(summary['stopped'], 'retry_budget')
        self.assertEqual(transport.call_count, 1)
        self.assertIsNone(rows[0]['actual_micro_usd'])

    def test_http_error_no_retry_full_body_and_usage(self):
        body = {'error': {'message': 'synthetic API error'}, 'usage': {'input_tokens': 7, 'output_tokens': 0}}
        reply = {'http_status': 429, 'http_error': 'HTTP 429', 'raw_response': json.dumps(body)}
        summary, rows, transport = self.run_mock([request(), request(1)], [reply, response()])
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(rows[0]['status'], 'http_error')
        self.assertEqual(rows[0]['http_status'], 429)
        self.assertEqual(rows[0]['raw_response'], json.dumps(body))
        self.assertEqual(rows[0]['usage'], body['usage'])
        self.assertEqual(rows[1]['attempt'], 1)

    def test_content_failure_no_retry_continue(self):
        summary, rows, transport = self.run_mock([request(), request(1)], [response(answer={'wrong': 1}), response()])
        self.assertEqual([r['status'] for r in rows], ['content_error', 'ok'])
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(summary['actual_micro_usd'], 120)

    def test_incomplete_keeps_usage_and_raw(self):
        reply = response(status='incomplete')
        summary, rows, transport = self.run_mock([request()], [reply])
        self.assertEqual(rows[0]['status'], 'content_error')
        self.assertEqual(rows[0]['actual_micro_usd'], 60)
        self.assertEqual(rows[0]['raw_response'], reply['raw_response'])

    def test_sse_complete_raw_preserved(self):
        body = json.loads(response()['raw_response'])
        raw = 'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"synthetic"}\n\n'
        raw += 'data: ' + json.dumps({'type': 'response.completed', 'response': body}) + '\n\n'
        summary, rows, transport = self.run_mock([request()], [{'http_status': 200, 'raw_response': raw}])
        self.assertEqual(rows[0]['status'], 'ok')
        self.assertEqual(rows[0]['raw_response'], raw)
        self.assertEqual(rows[0]['response'], body)

    def test_stream_error_and_truncation_no_retry(self):
        replies = [{'http_status': 200, 'raw_response': 'data: {"type":"error","message":"synthetic"}\n\n'},
                   {'http_status': 200, 'raw_response': 'data: {"type":"response.output_text.delta"}\n\n'}]
        _, rows, transport = self.run_mock([request(), request(1)], replies)
        self.assertEqual([r['status'] for r in rows], ['content_error', 'content_error'])
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(rows[0]['error']['detail']['message'], 'synthetic')

    def test_duplicate_identity_and_bad_limits(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            replay.replay([request(), request()])
        with self.assertRaises(ValueError):
            replay.replay([], limit=-1)

    def test_schema_refs_and_unknown_keywords_fail_closed(self):
        schema = {'type': 'object', '$defs': {'v': {'anyOf': [{'type': 'null'}, {'type': 'integer', 'enum': [1]}]}},
                  'properties': {'v': {'$ref': '#/$defs/v'}}, 'required': ['v'], 'additionalProperties': False}
        self.assertEqual(replay.common.schema_errors({'v': 1}, schema), [])
        self.assertTrue(replay.common.schema_errors({'v': True}, schema))
        self.assertTrue(replay.common.schema_errors({'v': 2}, schema))
        self.assertTrue(replay.common.schema_errors({'v': 1}, {'anyOf': [schema, {'format': 'unknown'}]}))
        self.assertTrue(replay.common.schema_errors({}, {'$ref': 'https://example.invalid/schema'}))

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError): replay.common.parse_json(text)

    def test_model_or_tier_mismatch_unknown_cost(self):
        bad = response()
        body = json.loads(bad['raw_response'])
        body['service_tier'] = 'flex'
        bad['raw_response'] = json.dumps(body)
        _, rows, _ = self.run_mock([request()], [bad])
        self.assertEqual(rows[0]['status'], 'content_error')
        self.assertIsNone(rows[0]['actual_micro_usd'])

    def test_mock_real_transport_redacts_key_and_no_redirects(self):
        class Wire:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def __iter__(self): return iter([b'{"error":"synthetic-key"}'])
        opener = mock.Mock()
        opener.open.return_value = Wire()
        with mock.patch.object(replay.os.environ, 'get', return_value='synthetic-key'), \
             mock.patch.object(replay.urllib.request, 'build_opener', return_value=opener):
            transport = replay.OpenAITransport()
            raw = transport(replay.build_request(request(), 'gpt-6-luna'))
        self.assertNotIn('synthetic-key', raw['raw_response'])
        self.assertIn('[REDACTED_API_KEY]', raw['raw_response'])
        wire_request = opener.open.call_args[0][0]
        self.assertEqual(wire_request.get_header('Authorization'), 'Bearer synthetic-key')

    def test_cli_isolated_dry_run(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            fixture = Path(temp) / 'requests.jsonl'
            fixture.write_text(json.dumps(request()) + '\n', encoding='utf-8')
            result = subprocess.run([sys.executable, '-I', str(ROOT / 'replay.py'),
                '--requests', str(fixture), '--model', 'gpt-6-luna'], capture_output=True, text=True,
                cwd=ROOT, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(summary['mode'], 'DRY-RUN')
        self.assertEqual(summary['attempts'], 0)

    def test_extract_replay_compare_integration_offline(self):
        def load(name):
            spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        extractor, compare = load('extract_requests'), load('compare')
        source = request()
        answer = {'observations': [{'source_index': 0, 'update_target': 'W0',
                                   'update': 'update', 'kind': 'work'}],
                  'work_results': {'0': {'action': 'done'}, '1': 'unchanged'}}
        source['request_json']['prompt'] += '\nBereits geöffnete Original-IDs: []'
        queue_call = {'job_id': source['job_id'], 'call_index': 0,
            'request_json': source['request_json'],
            'response_json': {'content': [{'text': json.dumps(answer)}],
                              'usage': {'input_tokens': 500, 'output_tokens': 100}},
            'actual_micro_usd': 1000}
        output = io.StringIO()
        counts = extractor.extract_lines([json.dumps({'kind': 'call', 'sequence': 0,
            'record_json': json.dumps(queue_call)}) + '\n'], output)
        extracted = [json.loads(line) for line in output.getvalue().splitlines()]
        _, rows, transport = self.run_mock(extracted, [response(answer=answer)])
        report = compare.compare_records(extracted, rows)
        self.assertEqual(counts['written_calls'], 1)
        self.assertEqual(transport.call_count, 1)
        self.assertTrue(report['passed'])
        self.assertEqual(report['total']['recall_hits'], 1)
        self.assertEqual(report['total']['actual_micro_usd'], 60)

    def test_mock_real_transport_http_and_network_errors(self):
        opener = mock.Mock()
        http_error = replay.urllib.error.HTTPError('https://example.invalid', 500, 'synthetic', {},
            io.BytesIO(b'{"error":"synthetic failure"}'))
        with mock.patch.object(replay.os.environ, 'get', return_value='synthetic-key'), \
             mock.patch.object(replay.urllib.request, 'build_opener', return_value=opener):
            transport = replay.OpenAITransport()
            opener.open.side_effect = http_error
            http = transport(replay.build_request(request(), 'gpt-6-luna'))
            opener.open.side_effect = replay.urllib.error.URLError('synthetic wire error')
            network = transport(replay.build_request(request(), 'gpt-6-luna'))
        self.assertEqual(http['http_status'], 500)
        self.assertEqual(http['raw_response'], '{"error":"synthetic failure"}')
        self.assertIn('transport_error', network)

    def test_http_incomplete_read_preserves_buffer_and_partial_bytes(self):
        opener = mock.Mock()
        error = replay.urllib.error.HTTPError('https://example.invalid', 500, 'synthetic', {}, io.BytesIO())
        error.read = mock.Mock(side_effect=[b'first-http-chunk',
            replay.http.client.IncompleteRead(b'partial-error-body')])
        opener.open.side_effect = error
        with mock.patch.object(replay.os.environ, 'get', return_value='synthetic-key'), \
             mock.patch.object(replay.urllib.request, 'build_opener', return_value=opener):
            result = replay.OpenAITransport()(replay.build_request(request(), 'gpt-6-luna'))
        self.assertEqual(result['raw_response'], 'first-http-chunkpartial-error-body')
        self.assertEqual(result['http_status'], 500)
        self.assertIn('IncompleteRead', result['body_read_error'])
        _, rows, transport = self.run_mock([request()], [result])
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(rows[0]['error']['body_read_error'], result['body_read_error'])

    def test_stream_incomplete_read_preserves_all_received_bytes(self):
        class Wire:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def __iter__(self):
                yield b'data: first-event\n\n'
                raise replay.http.client.IncompleteRead(b'data: second-partial-event')
        opener = mock.Mock()
        opener.open.return_value = Wire()
        with mock.patch.object(replay.os.environ, 'get', return_value='synthetic-key'), \
             mock.patch.object(replay.urllib.request, 'build_opener', return_value=opener):
            result = replay.OpenAITransport()(replay.build_request(request(), 'gpt-6-luna'))
        self.assertEqual(result['raw_response'], 'data: first-event\n\ndata: second-partial-event')
        self.assertEqual(result['exception_type'], 'IncompleteRead')


if __name__ == '__main__':
    unittest.main()
