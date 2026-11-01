"""Offline transport contract: synthetic fixtures, no keys/network/sleeps/writes.
Question: do retries require positive allowed-error evidence and stop after one
standard fallback? Criterion: exact tiers/counts, original standard wire bytes,
strict returned tier, bounded diagnostics. Failure blocks package acceptance.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, call
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent))
import openai_provider as provider

SCHEMA = {'type': 'object', 'properties': {}, 'additionalProperties': False}

def body(tier='flex'):
    return {'id': 'synthetic', 'model': provider.MODEL, 'status': 'completed',
            'service_tier': tier, 'usage': {'input_tokens': 1, 'output_tokens': 1},
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': '{}'}]}]}

class Stream:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def __iter__(self):
        if self.error: raise self.error
        yield ('data: ' + json.dumps(self.value or
            {'type': 'response.completed', 'response': body()})).encode() + b'\n'
        yield b'\n'

def success(tier='flex', **updates):
    value = body(tier)
    value.update(updates)
    return Stream({'type': 'response.' + value['status'], 'response': value})

def http(status=429, code='flex_unavailable', kind='resource_unavailable', message='private sentinel'):
    return urllib.error.HTTPError('https://synthetic.invalid', status, 'synthetic', {},
        io.BytesIO(json.dumps({'error': {'code': code, 'type': kind, 'message': message}}).encode()))

class FlexTransport(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.stack.enter_context(patch.object(provider, 'api_key', return_value='synthetic-key'))
        self.open = self.stack.enter_context(patch.object(provider.urllib.request, 'urlopen'))
        self.sleep = self.stack.enter_context(patch.object(provider.time, 'sleep'))
        self.stack.enter_context(patch.object(provider.time, 'monotonic', return_value=100))
        os.environ['DASHBOARD_SERVICE_TIER'] = 'flex_fallback'
    def run_request(self, outcomes):
        self.open.side_effect = outcomes
        return provider.request('synthetic input', provider.MODEL, schema=SCHEMA)
    def tiers(self):
        return [json.loads(c.args[0].data)['service_tier'] for c in self.open.call_args_list]
    def test_flex_success(self):
        result = self.run_request([success()])
        self.assertNotIn('error', result)
        self.assertEqual((result['requested_service_tier'], result['returned_service_tier'], result['flex_attempts']), ('flex', 'flex', 1))
        self.assertEqual(self.open.call_args.kwargs['timeout'], 900)
        self.sleep.assert_not_called()
    def test_retry_success(self):
        result = self.run_request([http(), success()])
        self.assertEqual(result['flex_attempts'], 2)
        self.assertEqual(self.tiers(), ['flex', 'flex'])
        self.sleep.assert_has_calls([call(2)])
    def test_three_429_then_standard(self):
        result = self.run_request([http(), http(), http(), success('default')])
        self.assertEqual(self.tiers(), ['flex', 'flex', 'flex', 'default'])
        self.assertEqual(result['flex_attempts'], 3)
        self.assertEqual(result['requested_service_tier'], 'default')
        self.assertEqual([c.kwargs['timeout'] for c in self.open.call_args_list], [900, 900, 900, 60])
        self.assertEqual(self.sleep.call_args_list, [call(2), call(5)])
    def test_allowed_429_variants(self):
        for code, kind in [('resource_unavailable', 'other'), ('flex_unavailable', 'other'), ('other', 'resource_unavailable')]:
            with self.subTest(code=code, kind=kind):
                self.open.reset_mock(); self.sleep.reset_mock()
                result = self.run_request([http(code=code, kind=kind), success()])
                self.assertEqual(result['flex_attempts'], 2)
    def test_5xx_and_timeouts(self):
        for error in [http(500, None, None), http(599, None, None), TimeoutError('private sentinel'), urllib.error.URLError(TimeoutError('private sentinel'))]:
            with self.subTest(error=type(error).__name__):
                self.open.reset_mock()
                result = self.run_request([error, success()])
                self.assertEqual(result['flex_attempts'], 2)
                self.assertNotIn('error', result)
    def test_stream_timeouts(self):
        for error in [TimeoutError('private sentinel'), urllib.error.URLError(TimeoutError('private sentinel'))]:
            with self.subTest(error=type(error).__name__):
                self.open.reset_mock()
                result = self.run_request([Stream(error=error), success()])
                self.assertEqual(result['flex_attempts'], 2)
                self.assertNotIn('_transport_timeout', result)
    def test_fallback_never_repeats(self):
        os.environ['DASHBOARD_FLEX_RETRIES'] = '0'
        for error in [http(), http(503), TimeoutError('synthetic')]:
            with self.subTest(error=type(error).__name__):
                self.open.reset_mock()
                result = self.run_request([http(), error])
                self.assertEqual(self.tiers(), ['flex', 'default'])
                self.assertIn('error', result)
    def test_wrong_or_missing_tier_never_falls_back(self):
        for tier in ['default', None, 'auto', 'flex wrong']:
            with self.subTest(tier=tier):
                self.open.reset_mock()
                result = self.run_request([success(tier)])
                self.assertIn('error', result)
                self.assertEqual(self.open.call_count, 1)
    def test_wrong_fallback_tier(self):
        os.environ['DASHBOARD_FLEX_RETRIES'] = '0'
        result = self.run_request([http(), success('flex')])
        self.assertIn('error', result)
        self.assertEqual(self.tiers(), ['flex', 'default'])
    def test_disallowed_http_and_transport(self):
        for error in [http(429, 'rate_limit', 'rate_limit'), http(429, None, None), http(400), http(401), http(499), http(600), urllib.error.URLError('synthetic'), OSError('synthetic')]:
            with self.subTest(error=type(error).__name__):
                self.open.reset_mock()
                result = self.run_request([error])
                self.assertIn('error', result)
                self.assertEqual(self.open.call_count, 1)
    def test_content_failures_never_retry(self):
        cases = [success(status='incomplete'), success(status='failed'), success(output=[]), success(model='wrong'), Stream({'type': 'error', 'code': 'resource_unavailable', 'message': 'private sentinel'}), Stream({'type': 'response.completed', 'response': {'status': 'failed'}}), Stream(error=ValueError('private sentinel'))]
        for outcome in cases:
            with self.subTest(outcome=type(outcome).__name__):
                self.open.reset_mock()
                result = self.run_request([outcome])
                self.assertIn('error', result)
                self.assertEqual(self.open.call_count, 1)
                self.assertNotIn('private sentinel', json.dumps(result))
    def test_sanitized_http_diagnostics(self):
        for value, expected in [('A.b_-09', 'A.b_-09'), ('a'*80, 'a'*80), ('a'*81, None), ('private sentinel', None), ('ä', None), (1, None), ('', None), (None, None)]:
            with self.subTest(value=value):
                result = self.run_request([http(400, value, value)])
                self.assertEqual(result['provider_error_code'], expected)
                self.assertEqual(result['provider_error_type'], expected)
                self.assertNotIn('private sentinel', json.dumps(result))
    def test_counter_http_sanitized_and_no_tier(self):
        self.open.side_effect = [http(400, 'bad_input', 'invalid_request')]
        diagnostic = io.StringIO()
        with contextlib.redirect_stderr(diagnostic), self.assertRaises(provider.CounterUnavailable) as caught:
            provider.count_input_tokens('synthetic', provider.MODEL, SCHEMA)
        self.assertEqual(caught.exception.provider_error_code, 'bad_input')
        self.assertEqual(caught.exception.provider_error_type, 'invalid_request')
        self.assertNotIn('private sentinel', diagnostic.getvalue())
        self.assertNotIn('service_tier', json.loads(self.open.call_args.args[0].data))
        self.assertEqual(self.open.call_count, 1)
    def test_embedding_http_sanitized_no_retry(self):
        result = self.run_embedding([http(429, 'resource_unavailable', 'resource_unavailable')])
        self.assertEqual(result['provider_error_code'], 'resource_unavailable')
        self.assertEqual(result['flex_attempts'], 0)
        self.assertEqual(self.open.call_count, 1)
        self.assertNotIn('private sentinel', json.dumps(result))
        self.assertNotIn('service_tier', json.loads(self.open.call_args.args[0].data))
    def run_embedding(self, outcomes):
        self.open.side_effect = outcomes
        return provider.request('["synthetic"]', 'text-embedding-3-small', schema=SCHEMA)
    def test_configuration(self):
        for name, value in [('DASHBOARD_SERVICE_TIER', 'flex'), ('DASHBOARD_FLEX_RETRIES', '-1'), ('DASHBOARD_FLEX_RETRIES', '2.5'), ('DASHBOARD_FLEX_RETRIES', '²'), ('DASHBOARD_FLEX_TIMEOUT_SECONDS', '0'), ('DASHBOARD_FLEX_TIMEOUT_SECONDS', 'nan'), ('DASHBOARD_FLEX_TIMEOUT_SECONDS', 'inf'), ('DASHBOARD_FLEX_TIMEOUT_SECONDS', 'bad')]:
            with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                with self.assertRaises(ValueError): self.run_request([])
                self.open.assert_not_called()
    def test_default_ignores_unused_flex_settings(self):
        os.environ.update(DASHBOARD_SERVICE_TIER='default',
            DASHBOARD_FLEX_RETRIES='invalid', DASHBOARD_FLEX_TIMEOUT_SECONDS='invalid')
        result = self.run_request([success('default')])
        self.assertNotIn('error', result)
        self.assertEqual(self.open.call_args.kwargs['timeout'], 60)
    def test_non_json_http_body_never_retries_429(self):
        error = urllib.error.HTTPError('https://synthetic.invalid', 429, 'synthetic', {},
            io.BytesIO(b'private sentinel'))
        result = self.run_request([error])
        self.assertIsNone(result['provider_error_code'])
        self.assertIsNone(result['provider_error_type'])
        self.assertEqual(self.open.call_count, 1)
        self.assertNotIn('private sentinel', json.dumps(result))
    def test_counter_and_embedding_reject_prose_diagnostics(self):
        self.open.side_effect = [http(400, 'private sentinel', 'ä')]
        diagnostic = io.StringIO()
        with contextlib.redirect_stderr(diagnostic), self.assertRaises(provider.CounterUnavailable) as caught:
            provider.count_input_tokens('synthetic', provider.MODEL, SCHEMA)
        self.assertIsNone(caught.exception.provider_error_code)
        self.assertIsNone(caught.exception.provider_error_type)
        self.assertNotIn('private sentinel', diagnostic.getvalue())
        result = self.run_embedding([http(400, 'private sentinel', 'ä')])
        self.assertIsNone(result['provider_error_code'])
        self.assertIsNone(result['provider_error_type'])
        self.assertNotIn('private sentinel', json.dumps(result))
    def test_custom_retries_delays_timeout(self):
        os.environ.update(DASHBOARD_FLEX_RETRIES='3', DASHBOARD_FLEX_TIMEOUT_SECONDS='123')
        result = self.run_request([http(), http(), http(), http(), success('default')])
        self.assertEqual(result['flex_attempts'], 4)
        self.assertEqual(self.sleep.call_args_list, [call(2), call(5), call(5)])
        self.assertEqual([c.kwargs['timeout'] for c in self.open.call_args_list], [123]*4+[60])
    def test_stream_deadline_and_default_deadline(self):
        for mode, deadline, socket in [('flex_fallback', 1000, 900), ('default', 520, 60)]:
            with self.subTest(mode=mode), patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': mode}), patch.object(provider, 'collect_stream', return_value={'error': 'synthetic'}) as collect:
                self.run_request([Stream()])
                self.assertEqual(collect.call_args.args[1], deadline)
                self.assertEqual(self.open.call_args.kwargs['timeout'], socket)
    def test_actual_deadline_timeout_retries(self):
        self.open.side_effect = [success(), success()]
        with patch.object(provider.time, 'monotonic', side_effect=[0, 0, 901, 901, 901, 901, 901]):
            result = provider.request('synthetic', provider.MODEL, schema=SCHEMA)
        self.assertEqual(result['flex_attempts'], 2)
        self.assertNotIn('error', result)
    def test_default_body_matches_original_and_no_retry(self):
        source = Path(__file__).resolve().parents[3] / 'sol-operational-release-20261006/backend/openai_provider.py'
        spec = importlib.util.spec_from_file_location('original_provider', source)
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        os.environ['DASHBOARD_SERVICE_TIER'] = 'default'
        self.open.side_effect = [success('default')]
        with patch.object(original, 'api_key', return_value='synthetic-key'):
            original.request('synthetic input', original.MODEL, schema=SCHEMA)
        original_data = self.open.call_args.args[0].data
        self.open.reset_mock()
        result = self.run_request([success('default')])
        self.assertEqual(self.open.call_args.args[0].data, original_data)
        self.assertEqual(result['flex_attempts'], 0)
        self.assertEqual(self.open.call_args.kwargs['timeout'], 60)
        self.open.reset_mock()
        self.run_request([http(503)])
        self.assertEqual(self.open.call_count, 1)
        self.sleep.assert_not_called()

if __name__ == '__main__': unittest.main()
