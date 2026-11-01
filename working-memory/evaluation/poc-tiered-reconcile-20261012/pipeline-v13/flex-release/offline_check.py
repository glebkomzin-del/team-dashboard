"""Network-free container checks; --local permits one explicit missing-asset stub."""
import argparse
import contextlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
PROD = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/prod')
REFERENCES = ROOT.parent / 'flex'
SCHEMA = {'type': 'object', 'properties': {}, 'additionalProperties': False}


def assert_true(condition):
    if not condition:
        raise AssertionError('Offline check failed')


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def successful(tier='flex'):
    return {'id': 'synthetic', 'model': 'gpt-6.1-sol', 'status': 'completed',
            'service_tier': tier, 'usage': {'input_tokens': 1000, 'output_tokens': 100,
            'input_tokens_details': {'cached_tokens': 200, 'cache_write_tokens': 100}},
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': '{}'}]}]}


class Stream:
    def __init__(self, body=None, error=None):
        self.body, self.error = body or successful(), error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        if self.error:
            raise self.error
        event = {'type': 'response.' + self.body['status'], 'response': self.body}
        return iter([('data: ' + json.dumps(event) + '\n').encode(), b'\n'])


def rejection(status=429, code='flex_unavailable', kind='resource_unavailable'):
    raw = json.dumps({'error': {'code': code, 'type': kind, 'message': 'synthetic'}}).encode()
    return urllib.error.HTTPError('https://synthetic.invalid', status, 'synthetic', {}, io.BytesIO(raw))


def mocked_request(provider, outcomes, mode='flex_fallback'):
    with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': mode,
                    'DASHBOARD_FLEX_RETRIES': '2', 'DASHBOARD_FLEX_TIMEOUT_SECONDS': '480'}), \
         patch.object(provider, 'api_key', return_value='synthetic'), \
         patch.object(provider.urllib.request, 'urlopen', side_effect=outcomes) as transport, \
         patch.object(provider, '_backoff', return_value=False, create=True):
        result = provider.request('synthetic', provider.MODEL, max_tokens=100, schema=SCHEMA)
    bodies = [json.loads(call.args[0].data) for call in transport.call_args_list]
    return result, bodies, transport


def check_default(provider, local):
    expected = {'model': provider.MODEL, 'input': [{'role': 'user', 'content': 'synthetic'}],
                'reasoning': {'effort': 'medium'}, 'truncation': 'disabled',
                'service_tier': 'default', 'prompt_cache_options': {'mode': 'explicit'},
                'text': {'format': {'type': 'json_schema', 'name': 'meeting_result',
                                    'strict': True, 'schema': SCHEMA}},
                'max_output_tokens': 100, 'store': False, 'stream': True}
    result, bodies, transport = mocked_request(provider, [Stream(successful('default'))], 'default')
    assert_true(bodies == [expected] and transport.call_args.kwargs['timeout'] == 60)
    assert_true(transport.call_args.args[0].data == json.dumps(expected).encode())
    assert_true(result['flex_attempts'] == 0 and result['stop_reason'] == 'end_turn')
    if local:
        original = load_file('_production_reference', PROD / 'openai_provider.py')
        _, _, original_transport = mocked_request(original, [Stream(successful('default'))], 'default')
        assert_true(transport.call_args.args[0].data == original_transport.call_args.args[0].data)


def check_version(worker, provider, local):
    if local:
        # Real version functions and source files; only the absent correction asset is stubbed.
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if path.name == 'source-corrections.json' and not path.exists():
                return '{}'
            if path.name in ('openai_provider.py', 'call_budget.py'):
                return original_read(ROOT / path.name, *args, **kwargs)
            if path.name in ('hybrid_pipeline.py', 'compact_reconcile.py', 'durable_calls.py'):
                return original_read(PROD / path.name, *args, **kwargs)
            if path.parent == PROD or path.parent == PROD / 'evaluation':
                path = REFERENCES / path.relative_to(PROD)
            return original_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            version = worker.pipeline_version(provider.MODEL)
    else:
        version = worker.pipeline_version(provider.MODEL)
    assert_true(isinstance(version, str) and re.fullmatch(
        r'v11:compact1:gate1:gpt-6\.1-sol:[0-9a-f]{16}:canonical1:[0-9a-f]{16}', version))
    print(('pipeline_local_asset_stub ' if local else 'pipeline ') + version)


def check_identity(durable, provider):
    seen = []
    class Store:
        def call(self, operation, **fields):
            assert_true(operation == 'reserve_call')
            seen.append(fields['request_json'])
            result = provider.normalize(successful('default'), provider.MODEL)
            text = durable.encode(result)
            return {'request_hash': durable.sha(fields['request_json']),
                    'response_json': text, 'response_hash': durable.sha(text)}
    job = {'id': 'synthetic', 'lease_token': 'synthetic', 'pipeline': 'synthetic', 'expected_revision': 1}
    for mode in ('default', 'flex_fallback'):
        with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': mode}):
            calls = durable.DurableCalls(Store(), job, lambda *a, **k: None, SCHEMA,
                                         ROOT / 'unused-outbox', prior_calls=[])
            calls('synthetic', provider.MODEL, max_tokens=100)
    assert_true(len(seen) == 2 and seen[0] == seen[1] and durable.sha(seen[0]) == durable.sha(seen[1]))
    value = json.loads(seen[0])
    assert_true(value['transport'] == {'reasoning_effort': 'medium', 'service_tier': 'default',
                                      'prompt_cache_options': {'mode': 'explicit'}})


def run_checks(provider, budget, durable, worker, local=False):
    checks = []
    def add(name, function):
        checks.append((name, function))
    def syntax():
        for module in (provider, budget, durable, worker):
            source = Path(module.__file__)
            compile(source.read_bytes(), str(source), 'exec')
    add('syntax', syntax)
    add('pipeline_version', lambda: check_version(worker, provider, local))
    add('default_body', lambda: check_default(provider, local))
    def flex_success():
        result, bodies, _ = mocked_request(provider, [Stream()])
        assert_true([b['service_tier'] for b in bodies] == ['flex'])
        assert_true(all(b['prompt_cache_options'] == {'mode': 'explicit'} for b in bodies))
        assert_true(result['flex_attempts'] == 1 and budget.usage_micro_usd(result, provider.MODEL) == 1335)
    add('flex_200_cost', flex_success)
    def retry():
        result, bodies, _ = mocked_request(provider, [rejection(), Stream()])
        assert_true(len(bodies) == 2 and result['flex_attempts'] == 2 and result['stop_reason'] == 'end_turn')
    add('flex_429_retry', retry)
    def fallback():
        result, bodies, _ = mocked_request(provider, [rejection(), rejection(), rejection(), Stream(successful('default'))])
        assert_true([b['service_tier'] for b in bodies] == ['flex', 'flex', 'flex', 'default'])
        assert_true(all(b['prompt_cache_options'] == {'mode': 'explicit'} for b in bodies))
        assert_true(result['requested_service_tier'] == 'default' and result['flex_attempts'] == 3)
        assert_true(budget.usage_micro_usd(result, provider.MODEL) == 2670)
    add('flex_429x3_standard_once', fallback)
    def no_repeat(outcome):
        result, bodies, _ = mocked_request(provider, [outcome])
        assert_true(len(bodies) == 1 and 'error' in result)
    add('timeout_once', lambda: no_repeat(TimeoutError('synthetic')))
    add('stream_timeout_once', lambda: no_repeat(Stream(error=TimeoutError('synthetic'))))
    add('connection_once', lambda: no_repeat(ConnectionResetError('synthetic')))
    add('http_5xx_once', lambda: no_repeat(rejection(503)))
    add('http_other_429_once', lambda: no_repeat(rejection(429, 'rate_limit', 'rate_limit')))
    add('wrong_tier_error', lambda: no_repeat(Stream(successful('default'))))
    def reserve():
        amounts = []
        for mode in ('default', 'flex_fallback'):
            with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': mode}):
                amounts.append(budget.reserve_micro_usd('synthetic', provider.MODEL, 100, SCHEMA))
        assert_true(type(amounts[0]) is int and amounts[0] == amounts[1] and amounts[0] > 2670)
        unknown = provider.normalize(successful(), provider.MODEL, 'flex')
        unknown['returned_service_tier'] = 'unknown'
        assert_true(budget.usage_micro_usd(unknown, provider.MODEL) is None)
    add('reserve_actual_unknown', reserve)
    add('durable_identity', lambda: check_identity(durable, provider))
    passed = 0
    for name, function in checks:
        # Failures expose only the check name, never provider payloads or exception text.
        try:
            function()
        except Exception:
            print('fail ' + name)
        else:
            passed += 1
            print('ok ' + name)
    print(f'{passed}/{len(checks)}')
    return 0 if passed == len(checks) else 1


def no_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
        raise RuntimeError('Offline network guard')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true')
    args = parser.parse_args(argv)
    sys.addaudithook(no_network)
    with contextlib.ExitStack() as stack:
        if args.local:
            sys.path[:0] = [str(ROOT), str(PROD), str(REFERENCES)]
        else:
            sys.path.insert(0, '/app')  # -I intentionally ignores PYTHONPATH.
        stack.enter_context(patch.dict(os.environ, {'MEMORY_PROMPT_VERSION': 'v11', 'MEMORY_ACTION_GATE': '1'}))
        try:
            provider = importlib.import_module('openai_provider')
            budget = importlib.import_module('call_budget')
            durable = importlib.import_module('durable_calls')
            worker = importlib.import_module('canonical_worker')
        except Exception:
            print('fail imports')
            return 1
        return run_checks(provider, budget, durable, worker, args.local)


if __name__ == '__main__':
    raise SystemExit(main())
