"""Offline synthetic transport checks; no credentials, networking or source data.

Question: is production preserved and is retry permission positive and exact?
Passing permits local adapter acceptance; failure blocks adapter acceptance.
The sole dependency stub exposes exactly the production exception superclass.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import urllib.error

PRODUCTION = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/prod')
ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    dependency = sys.modules.get('durable_calls')
    if dependency is None:
        dependency = types.ModuleType('durable_calls')
        dependency.SharedProviderFailure = type('SharedProviderFailure', (RuntimeError,), {})
    with patch.dict(sys.modules, {'durable_calls': dependency}):
        spec.loader.exec_module(module)
    return module


provider = load('release_provider_test', ROOT / 'openai_provider.py')
production = load('production_provider_test', PRODUCTION / 'openai_provider.py')


def terminal(tier='default', **changes):
    response = {'id': 'synthetic', 'model': provider.MODEL, 'status': 'completed',
                'service_tier': tier, 'usage': {'input_tokens': 12, 'output_tokens': 2},
                'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                            'content': [{'type': 'output_text', 'text': '{}'}]}]}
    response.update(changes)
    return response


class Stream:
    def __init__(self, response=None, lines=None):
        self.lines = lines if lines is not None else [
            ('data: ' + json.dumps({'type': 'response.' + response['status'], 'response': response}) + '\n').encode(), b'\n']
    def __iter__(self):
        return iter(self.lines)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


def http(status=429, body=b'{"error":{"code":"flex_unavailable"}}'):
    return urllib.error.HTTPError('https://invalid.test', status, 'synthetic', {}, io.BytesIO(body))


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': 'default'}, clear=True)
        self.environment.start()
        self.keys = patch.object(provider, 'api_key', return_value='synthetic')
        self.keys.start()
    def tearDown(self):
        self.keys.stop()
        self.environment.stop()

    def call(self, effects, flex=True, **env):
        os.environ['DASHBOARD_SERVICE_TIER'] = 'flex_fallback' if flex else 'default'
        os.environ.update(env)
        with patch.object(provider.urllib.request, 'urlopen', side_effect=effects) as opened, patch.object(provider, '_backoff', return_value=False) as waited:
            result = provider.request('synthetic', provider.MODEL, 10, {})
        slept = types.SimpleNamespace(called=waited.called, call_args_list=[types.SimpleNamespace(args=(c.args[1],)) for c in waited.call_args_list])
        return result, opened, slept

    def test_default_bytes_and_metadata_match_production(self):
        captured = []
        def send(req, timeout):
            captured.append((req.data, timeout))
            return Stream(terminal())
        with patch.object(provider.urllib.request, 'urlopen', side_effect=send), patch.object(provider.time, 'monotonic', return_value=10):
            actual = provider.request('synthetic', provider.MODEL, 10, {})
        with patch.object(production, 'api_key', return_value='synthetic'), patch.object(production.urllib.request, 'urlopen', side_effect=send), patch.object(production.time, 'monotonic', return_value=10):
            expected = production.request('synthetic', production.MODEL, 10, {})
        self.assertEqual(captured[0], captured[1])
        self.assertEqual(captured[0][1], 60)
        self.assertEqual(json.loads(captured[0][0])['prompt_cache_options'], {'mode': 'explicit'})
        self.assertEqual(actual.pop('flex_attempts'), 0)
        self.assertEqual(actual, expected)
        os.environ.pop('DASHBOARD_SERVICE_TIER')
        with patch.object(provider.urllib.request, 'urlopen', side_effect=send):
            provider.request('synthetic', provider.MODEL, 10, {})
        self.assertEqual(captured[0], captured[2])

    def test_default_errors_validation_and_stream_deadline_match_production(self):
        effects = [lambda: http(500), lambda: TimeoutError(), lambda: urllib.error.URLError('synthetic'),
                   lambda: Stream(lines=[]), lambda: Stream(lines=[b'data: invalid\n', b'\n'])]
        for make in effects:
            with patch.object(provider.urllib.request, 'urlopen', side_effect=[make()]), patch.object(provider.time, 'monotonic', return_value=10):
                actual = provider.request('synthetic', provider.MODEL, 10, {})
            with patch.object(production, 'api_key', return_value='synthetic'), patch.object(production.urllib.request, 'urlopen', side_effect=[make()]), patch.object(production.time, 'monotonic', return_value=10):
                expected = production.request('synthetic', production.MODEL, 10, {})
            self.assertEqual(actual.pop('flex_attempts'), 0)
            self.assertEqual(actual, expected)
        for module in (provider, production):
            captured = []
            def collect(response, deadline, model):
                captured.append(deadline)
                return {}
            with patch.object(module, 'api_key', return_value='synthetic'), patch.object(module.urllib.request, 'urlopen', return_value=Stream(terminal())), patch.object(module.time, 'monotonic', return_value=10), patch.object(module, 'collect_stream', side_effect=collect):
                module.request('synthetic', module.MODEL, 10, {})
            self.assertEqual(captured, [430])
            for model, tokens, schema in [('invalid', 10, {}), (module.MODEL, True, {}), (module.MODEL, 0, {}), (module.MODEL, 10, None)]:
                with self.assertRaises(ValueError):
                    module.request('synthetic', model, tokens, schema)

    def test_original_normalization_cases(self):
        cases = [terminal(), terminal(status='incomplete'), terminal(model='wrong'), terminal(service_tier='flex'), terminal(output=[]), terminal(output=[None]), terminal(output=[{'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': [{'type':'refusal'}]}])]
        for response in cases:
            with self.subTest(case=cases.index(response)):
                self.assertEqual(provider.normalize(response, provider.MODEL), production.normalize(response, provider.MODEL))

    def test_flex_success_and_retry_backoffs_then_standard(self):
        result, opened, slept = self.call([Stream(terminal('flex'))])
        self.assertEqual(result['stop_reason'], 'end_turn')
        self.assertEqual(result['flex_attempts'], 1)
        self.assertEqual(json.loads(opened.call_args.args[0].data)['service_tier'], 'flex')
        result, opened, slept = self.call([http(), http(), http(), Stream(terminal())])
        self.assertEqual(result['flex_attempts'], 3)
        self.assertEqual(result['requested_service_tier'], 'default')
        self.assertEqual([c.args[0] for c in slept.call_args_list], [2, 5])
        self.assertEqual([json.loads(c.args[0].data)['service_tier'] for c in opened.call_args_list], ['flex'] * 3 + ['default'])

    def test_type_permission_and_extra_backoff(self):
        result, opened, slept = self.call([http(body=b'{"error":{"type":"resource_unavailable"}}'), Stream(terminal('flex'))])
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(result['stop_reason'], 'end_turn')
        _, opened, slept = self.call([http(), http(), http(), http(), Stream(terminal())], DASHBOARD_FLEX_RETRIES='3')
        self.assertEqual([c.args[0] for c in slept.call_args_list], [2, 5, 5])

    def test_unproven_retry_permission_never_resends(self):
        bodies = [b'flex_unavailable', b'{"error":{"message":"flex_unavailable resource_unavailable"}}', b'{"error":{"code":"flex_unavailable', b'{"error":{"code":"other"}}', b'{"error":{"code":"flex_unavailable","code":"other"}}', b'{"error":{"code":"flex_unavailable"},"error":{}}', b'[]', b'{"error":null}', b'{"error":{"code":"flex_unavailable"},"x":NaN}', b' ' * 65537, b'{"error":{"code":"FLEX_UNAVAILABLE"}}', b'{"error":{"code":"flex_unavailable "}}', b'\xff']
        for body in bodies:
            with self.subTest(case=bodies.index(body)):
                result, opened, slept = self.call([http(body=body)])
                self.assertEqual(opened.call_count, 1)
                self.assertEqual(result['usage_final'], False)
                self.assertIsNone(result['provider_error_code'])
                self.assertFalse(slept.called)

    def test_other_failures_never_retry(self):
        effects = [http(500), http(429, b'{"error":{"code":"rate_limit_exceeded"}}'), TimeoutError(), urllib.error.URLError('synthetic'), OSError(), Stream(terminal('default')), Stream(terminal('flex', status='incomplete')), Stream(lines=[b'data: {"type":"error"}\n', b'\n']), Stream(lines=[b'data: invalid\n', b'\n']), Stream(lines=[])]
        for effect in effects:
            with self.subTest(case=effects.index(effect)):
                result, opened, slept = self.call([effect])
                self.assertEqual(opened.call_count, 1)
                self.assertIn('error', result)
                self.assertFalse(slept.called)

    def test_fallback_failure_and_wrong_tier_never_retry(self):
        for effect in [http(500), http(), Stream(terminal('flex')), TimeoutError()]:
            result, opened, _ = self.call([http(), effect], DASHBOARD_FLEX_RETRIES='0')
            self.assertEqual(opened.call_count, 2)
            self.assertIn('error', result)

    def test_deadline_prevents_dispatch_and_late_stream_retry(self):
        class Clock:
            value = 0
            def now(self): return self.value
        clock = Clock()
        def delayed(req, timeout):
            clock.value = 481
            return Stream(terminal('flex'))
        with patch.object(provider.time, 'monotonic', clock.now):
            result, opened, _ = self.call(delayed)
        self.assertEqual(result['error'], 'TimeoutError')
        self.assertEqual(opened.call_count, 1)
        clock.value = 0
        def rejection(req, timeout):
            clock.value = 480
            raise http()
        with patch.object(provider.time, 'monotonic', clock.now):
            result, opened, _ = self.call(rejection)
        self.assertEqual(result['error'], 'TimeoutError')
        self.assertEqual(opened.call_count, 1)

    def test_configuration_limits_before_dispatch(self):
        for env in [{'DASHBOARD_FLEX_TIMEOUT_SECONDS': '900'}, {'DASHBOARD_FLEX_TIMEOUT_SECONDS': 'nan'}, {'DASHBOARD_FLEX_RETRIES': '-1'}]:
            with self.subTest(env=env), self.assertRaises(ValueError):
                self.call([], **env)

    def test_hard_deadline_with_blocked_line_forbids_late_fallback(self):
        import threading
        released, finished = threading.Event(), threading.Event()
        class BlockedStream(Stream):
            def __iter__(self):
                released.wait(1)
                yield b'data: {"type":"error"}\n'
                yield b'\n'
            def __exit__(self, *args):
                finished.set()
                return False
        os.environ.update({'DASHBOARD_SERVICE_TIER':'flex_fallback', 'DASHBOARD_FLEX_TIMEOUT_SECONDS':'0.03'})
        with patch.object(provider.urllib.request, 'urlopen', return_value=BlockedStream(lines=[])) as opened:
            result = provider.request('synthetic', provider.MODEL, 10, {})
            self.assertEqual(result['error'], 'TimeoutError')
            self.assertLess(result['elapsed_seconds'], 0.2)
            self.assertFalse(result['usage_final'])
            released.set()
            self.assertTrue(finished.wait(1))
            self.assertEqual(opened.call_count, 1)

    def test_hard_deadline_with_blocked_429_forbids_late_fallback(self):
        import threading
        released, finished = threading.Event(), threading.Event()
        class BlockedError(urllib.error.HTTPError):
            def read(self, size):
                released.wait(1)
                return b'{"error":{"code":"flex_unavailable"}}'
            def close(self):
                super().close()
                finished.set()
        os.environ.update({'DASHBOARD_SERVICE_TIER':'flex_fallback', 'DASHBOARD_FLEX_RETRIES':'0', 'DASHBOARD_FLEX_TIMEOUT_SECONDS':'0.03'})
        error = BlockedError('https://invalid.test', 429, 'synthetic', {}, io.BytesIO())
        with patch.object(provider.urllib.request, 'urlopen', side_effect=error) as opened:
            result = provider.request('synthetic', provider.MODEL, 10, {})
            self.assertEqual(result['error'], 'TimeoutError')
            released.set()
            self.assertTrue(finished.wait(1))
            self.assertEqual(opened.call_count, 1)

    def test_cancellation_before_atomic_admission_forbids_send(self):
        import threading
        paused, released, finished = threading.Event(), threading.Event(), threading.Event()
        dispatch = provider._dispatch
        def delayed(*args):
            paused.set()
            released.wait(1)
            try:
                return dispatch(*args)
            finally:
                finished.set()
        os.environ.update({'DASHBOARD_SERVICE_TIER':'flex_fallback', 'DASHBOARD_FLEX_TIMEOUT_SECONDS':'0.03'})
        with patch.object(provider, '_dispatch', side_effect=delayed), patch.object(provider.urllib.request, 'urlopen') as opened:
            result = provider.request('synthetic', provider.MODEL, 10, {})
            self.assertTrue(paused.is_set())
            self.assertEqual(result['error'], 'TimeoutError')
            self.assertEqual(result['flex_attempts'], 0)
            released.set()
            self.assertTrue(finished.wait(1))
            self.assertEqual(opened.call_count, 0)

    def test_already_admitted_retry_unknown_without_another_admission(self):
        import threading
        paused, released, finished = threading.Event(), threading.Event(), threading.Event()
        line = next(i for i, text in enumerate((ROOT / 'openai_provider.py').read_text().splitlines(), 1)
                    if 'response = urllib.request.urlopen(req, timeout=min(60, attempt_deadline - now))' in text)
        class Clock:
            value = 0
            def now(self): return self.value
        clock = Clock()
        admissions = []
        def trace(frame, event, arg):
            if event == 'line' and frame.f_code.co_filename == str(ROOT / 'openai_provider.py') and frame.f_lineno == line:
                admissions.append(1)
                if len(admissions) == 2:
                    paused.set()
                    clock.value = 481
                    frame.f_locals['wake'].set()
                    released.wait(1)
            return trace
        class LastError(urllib.error.HTTPError):
            def close(self):
                super().close()
                finished.set()
        errors = [http(), LastError('https://invalid.test', 429, 'synthetic', {}, io.BytesIO(b'{"error":{"code":"flex_unavailable"}}'))]
        os.environ.update({'DASHBOARD_SERVICE_TIER':'flex_fallback', 'DASHBOARD_FLEX_TIMEOUT_SECONDS':'480'})
        previous = threading.gettrace()
        threading.settrace(trace)
        try:
            with patch.object(provider.time, 'monotonic', clock.now), patch.object(provider, '_backoff', return_value=False), patch.object(provider.urllib.request, 'urlopen', side_effect=errors) as opened:
                result = provider.request('synthetic', provider.MODEL, 10, {})
                self.assertTrue(paused.is_set())
                self.assertEqual(result['error'], 'TimeoutError')
                self.assertEqual(result['flex_attempts'], 2)
                self.assertFalse(result['usage_final'])
                self.assertEqual(opened.call_count, 1)
                released.set()
                self.assertTrue(finished.wait(1))
                self.assertEqual(opened.call_count, 2)
                self.assertEqual(len(admissions), 2)
        finally:
            threading.settrace(previous)
            released.set()

    def test_caller_wakes_at_standard_420_deadline_inside_480_chain(self):
        import threading
        released, blocked, finished = threading.Event(), threading.Event(), threading.Event()
        real_wait = threading.Event.wait
        class Clock:
            value = 0
            def now(self): return self.value
        clock = Clock()
        waits = []
        def wait(event, timeout=None):
            if timeout in (420, 480):
                waits.append(timeout)
                if timeout == 420:
                    real_wait(blocked, 1)
                    clock.value = 421
                    return False
            return real_wait(event, timeout)
        class BlockedStandard(Stream):
            def __iter__(self):
                blocked.set()
                real_wait(released, 1)
                yield b'data: {"type":"error"}\n'
                yield b'\n'
            def __exit__(self, *args):
                finished.set()
                return False
        os.environ.update({'DASHBOARD_SERVICE_TIER':'flex_fallback', 'DASHBOARD_FLEX_RETRIES':'0'})
        with patch.object(provider.time, 'monotonic', clock.now), patch.object(threading.Event, 'wait', autospec=True, side_effect=wait), patch.object(provider.urllib.request, 'urlopen', side_effect=[http(), BlockedStandard(lines=[])]) as opened:
            result = provider.request('synthetic', provider.MODEL, 10, {})
            self.assertEqual(result['error'], 'TimeoutError')
            self.assertEqual(result['requested_service_tier'], 'default')
            self.assertEqual(result['flex_attempts'], 1)
            self.assertEqual(result['elapsed_seconds'], 421)
            self.assertIn(420, waits)
            released.set()
            self.assertTrue(real_wait(finished, 1))
            self.assertEqual(opened.call_count, 2)

    def test_counting_and_embedding_sources_unchanged(self):
        import ast
        def sources(path):
            text = path.read_text()
            lines = text.splitlines(keepends=True)
            return {node.name: ''.join(lines[node.lineno-1:node.end_lineno])
                    for node in ast.parse(text).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        actual, expected = sources(ROOT / 'openai_provider.py'), sources(PRODUCTION / 'openai_provider.py')
        for name in ('count_input_tokens', 'embedding_request', 'response_input', 'CounterUnavailable', 'api_key'):
            self.assertEqual(actual[name], expected[name])


if __name__ == '__main__':
    unittest.main()
