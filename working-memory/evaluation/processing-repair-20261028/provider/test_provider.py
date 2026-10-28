"""Offline error-envelope regressions. No credentials or network."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
dependency = types.ModuleType('durable_calls')
dependency.SharedProviderFailure = type('SharedProviderFailure', (RuntimeError,), {})
spec = importlib.util.spec_from_file_location('diagnostic_provider', ROOT / 'openai_provider.py')
provider = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'durable_calls': dependency}):
    spec.loader.exec_module(provider)


def stream(event):
    return [('data: ' + json.dumps(event) + '\n').encode(), b'\n']


class StreamDiagnostics(unittest.TestCase):
    def collect(self, lines):
        return provider.collect_stream(lines, time.monotonic() + 60, provider.MODEL, 'flex')

    def test_provider_error_preserves_only_allowlisted_code(self):
        result = self.collect(stream({'type': 'error', 'code': 'flex_unavailable',
                                     'message': 'PRIVATE MESSAGE', 'param': 'PRIVATE PARAM'}))
        self.assertEqual(result['error'], 'ValueError')
        self.assertEqual(result['stream_error_kind'], 'provider_error')
        self.assertEqual(result['provider_error_code'], 'flex_unavailable')
        self.assertNotIn('PRIVATE', json.dumps(result))
        result = self.collect(stream({'type': 'error', 'code': 'SECRETALPHANUMERIC'}))
        self.assertIsNone(result['provider_error_code'])

    def test_eof_is_distinct_and_not_accepted(self):
        result = self.collect(stream({'type': 'response.created', 'response': {}}))
        self.assertEqual(result['stream_error_kind'], 'incomplete_stream')
        self.assertEqual(result['error'], 'ValueError')
        self.assertFalse(result['usage_final'])
        self.assertEqual(result['content'], [])

    def test_status_mismatch_is_distinct(self):
        result = self.collect(stream({'type': 'response.completed', 'response': {'status': 'failed'}}))
        self.assertEqual(result['stream_error_kind'], 'terminal_status_mismatch')
        self.assertEqual(result['error'], 'ValueError')

    def test_malformed_event_fails_closed(self):
        result = self.collect([b'data: malformed\n', b'\n'])
        self.assertEqual(result['stream_error_kind'], 'malformed_event')
        self.assertEqual(result['error'], 'JSONDecodeError')
        self.assertEqual(result['content'], [])
        result = self.collect(stream([]))
        self.assertEqual(result['stream_error_kind'], 'invalid_event')
        self.assertEqual(result['content'], [])

    def test_completed_contract_is_unchanged(self):
        body = {'id': 'synthetic', 'model': provider.MODEL, 'status': 'completed',
                'service_tier': 'flex', 'usage': {'input_tokens': 10, 'output_tokens': 2},
                'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                            'content': [{'type': 'output_text', 'text': '{}'}]}]}
        result = self.collect(stream({'type': 'response.completed', 'response': body}))
        self.assertEqual(result, provider.normalize(body, provider.MODEL, 'flex'))
        self.assertEqual(result['stop_reason'], 'end_turn')

    def test_stream_error_never_adds_retry_or_fallback(self):
        response = io.BytesIO(b''.join(stream({'type': 'error', 'code': 'flex_unavailable'})))
        with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': 'flex_fallback'}, clear=True), \
                patch.object(provider, 'api_key', return_value='synthetic'), \
                patch.object(provider.urllib.request, 'urlopen', return_value=response) as opened, \
                patch.object(provider, '_backoff') as backoff:
            result = provider.request('synthetic', provider.MODEL, 10, {})
        self.assertEqual(opened.call_count, 1)
        backoff.assert_not_called()
        self.assertEqual(result['flex_attempts'], 1)
        self.assertEqual(result['error'], 'ValueError')
        self.assertEqual(result['provider_error_code'], 'flex_unavailable')


if __name__ == '__main__':
    unittest.main()
