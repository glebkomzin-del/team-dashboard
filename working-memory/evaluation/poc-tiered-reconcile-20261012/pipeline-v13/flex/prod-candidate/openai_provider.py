"""Sol Responses adapter; explicit effort and opt-in bounded flex fallback.

Translate only the transport envelope. All source, work and summary schemas and
validators remain in the existing pipeline. Partial output is never accepted.
"""
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from durable_calls import SharedProviderFailure

MODEL = 'gpt-6.1-sol'
REASONING_EFFORT = 'medium'  # Standard production reasoning; no provider fallback.


class CounterUnavailable(SharedProviderFailure):
    def __init__(self, kind, http_status=None, diagnostics=None):
        self.kind = kind
        self.http_status = http_status
        diagnostics = diagnostics or {}
        self.provider_error_code = diagnostics.get('provider_error_code')
        self.provider_error_type = diagnostics.get('provider_error_type')
        diagnostic = {'component': 'input_token_counter', 'type': kind,
                      'http_status': http_status, **diagnostics}
        print(json.dumps(diagnostic, separators=(',', ':')), file=sys.stderr, flush=True)
        super().__init__('Provider input token count unavailable')


def _metadata_text(value, limit=80):
    """Only bounded, non-prose terminal metadata; never copy error messages."""
    return value if isinstance(value, str) and 0 < len(value) <= limit and all(
        character.isascii() and (character.isalnum() or character in '._-') for character in value
    ) else None


def _error_metadata(body):
    detail = body.get('error') if isinstance(body, dict) else None
    detail = detail if isinstance(detail, dict) else {}
    return {'provider_error_code': _metadata_text(detail.get('code')),
            'provider_error_type': _metadata_text(detail.get('type'))}


def _http_metadata(error):
    try:
        return _error_metadata(json.loads(error.read(65536)))
    except Exception:
        return _error_metadata(None)
    finally:
        error.close()


def _is_timeout(error):
    return isinstance(error, TimeoutError) or (
        isinstance(error, urllib.error.URLError) and isinstance(error.reason, TimeoutError))


def _flex_config():
    mode = os.environ.get('DASHBOARD_SERVICE_TIER', 'default')
    if mode not in ('default', 'flex_fallback'):
        raise ValueError('Invalid service tier configuration')
    if mode == 'default':
        return mode, 0, 900
    try:
        retries_text = os.environ.get('DASHBOARD_FLEX_RETRIES', '2')
        if not retries_text.isascii() or not retries_text.isdecimal():
            raise ValueError()
        retries = int(retries_text)
        timeout = float(os.environ.get('DASHBOARD_FLEX_TIMEOUT_SECONDS', '900'))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError()
    except (ValueError, OverflowError):
        raise ValueError('Invalid flex transport configuration') from None
    return mode, retries, timeout


def normalize(response, model, requested_service_tier='default'):
    result = {'provider': 'openai', 'id': response.get('id'),
              'model': response.get('model'), 'content': [],
              'usage': response.get('usage') or {}, 'usage_final': False,
              'stop_reason': None, 'reasoning_effort': REASONING_EFFORT,
              'requested_service_tier': requested_service_tier,
              'returned_service_tier': _metadata_text(response.get('service_tier')),
              'terminal_status': _metadata_text(response.get('status')),
              'incomplete_reason': None, 'flex_attempts': 0, **_error_metadata(response)}
    details = response.get('incomplete_details')
    if isinstance(details, dict):
        result['incomplete_reason'] = _metadata_text(details.get('reason'))
    if response.get('model') != model:
        result['error'] = 'Unexpected provider model'
        return result
    status = response.get('status')
    result['usage_final'] = status in ('completed', 'incomplete', 'failed') and isinstance(response.get('usage'), dict)
    if status != 'completed':
        result['error'] = 'Provider response not completed'
        return result
    if result['returned_service_tier'] != requested_service_tier:
        result['error'] = ('Requested standard service tier not confirmed'
                           if requested_service_tier == 'default' else
                           'Requested flex service tier not confirmed')
        return result
    output = response.get('output')
    if not isinstance(output, list) or not output:
        result['error'] = 'Missing output items'
        return result
    messages = 0
    for item in output:
        if not isinstance(item, dict):
            result['error'] = 'Unexpected output item'
            return result
        if item.get('type') == 'reasoning':
            if (not isinstance(item.get('id'), str) or not item['id']
                    or item.get('status') not in (None, 'completed')
                    or not isinstance(item.get('summary'), list)
                    or any(not isinstance(part, dict) or part.get('type') != 'summary_text'
                           or not isinstance(part.get('text'), str) for part in item['summary'])
                    or (item.get('content') is not None and
                        (not isinstance(item['content'], list) or
                         any(not isinstance(part, dict) or part.get('type') != 'reasoning_text'
                             or not isinstance(part.get('text'), str) for part in item['content'])))
                    or (item.get('encrypted_content') is not None and
                        not isinstance(item['encrypted_content'], str))):
                result['error'] = 'Invalid or incomplete reasoning item'
                return result
            continue
        if item.get('type') != 'message' or item.get('role') != 'assistant' or item.get('status') != 'completed':
            result['error'] = 'Unexpected output item'
            return result
        messages += 1
        blocks = item.get('content')
        if not isinstance(blocks, list) or not blocks:
            result['error'] = 'Missing assistant content'
            return result
        for block in blocks:
            if not isinstance(block, dict):
                result['error'] = 'Provider refused or returned unexpected content'
                return result
            if block.get('type') != 'output_text' or not isinstance(block.get('text'), str):
                result['error'] = 'Provider refused or returned unexpected content'
                return result
            result['content'].append({'type': 'text', 'text': block['text']})
    if messages != 1 or not result['content']:
        result['error'] = 'Missing structured output'
    else:
        result['stop_reason'] = 'end_turn'
    return result


def collect_stream(response, deadline, model, requested_service_tier='default'):
    data = []
    def event(lines):
        if not lines:
            return None
        value = json.loads('\n'.join(lines))
        kind = value.get('type')
        if kind in ('response.completed', 'response.incomplete', 'response.failed'):
            body = value.get('response', {})
            if body.get('status') != kind.split('.')[1]:
                raise ValueError('Terminal response status mismatch')
            return normalize(body, model, requested_service_tier)
        if kind == 'error':
            return {'error': 'Provider stream error', 'usage_final': False,
                    'stop_reason': None, **_error_metadata({'error': value})}
        return None
    try:
        for raw_line in response:
            if time.monotonic() > deadline:
                raise TimeoutError('Total request deadline exceeded')
            line = raw_line.decode('utf-8').rstrip('\r\n')
            if line.startswith('data:'):
                data.append(line[5:].lstrip())
            elif not line:
                result = event(data)
                data = []
                if result is not None:
                    return result
        result = event(data)
        if result is not None:
            return result
        raise ValueError('Incomplete event stream')
    except Exception as error:
        # Never persist provider error bodies, which may contain private input.
        return {'provider': 'openai', 'content': [], 'usage': {},
                'usage_final': False, 'stop_reason': None, 'error': type(error).__name__,
                'requested_service_tier': requested_service_tier, 'returned_service_tier': None,
                'terminal_status': None, 'incomplete_reason': None,
                'provider_error_code': None, 'provider_error_type': None,
                'flex_attempts': 0, '_transport_timeout': _is_timeout(error),
                'reasoning_effort': REASONING_EFFORT}


def response_input(prompt, model, schema):
    return {'model': model, 'input': [{'role': 'user', 'content': prompt}],
            'reasoning': {'effort': REASONING_EFFORT}, 'truncation': 'disabled',
            'service_tier': 'default',
            'prompt_cache_options': {'mode': 'explicit'},
            'text': {'format': {'type': 'json_schema', 'name': 'meeting_result',
                                'strict': True, 'schema': schema}}}


def api_key():
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        path = Path(__file__).parent / '.local/model-keys.json'
        if path.exists(): key = json.loads(path.read_text()).get('OPENAI_API_KEY')
    if not key: raise RuntimeError('OPENAI_API_KEY missing')
    return key


def count_input_tokens(prompt, model, schema):
    if model != MODEL or not isinstance(schema, dict):
        raise ValueError('Unsupported counting input')
    # The count endpoint accepts only this subset of the generation request.
    # In particular, service_tier belongs to generation, not token counting.
    generation = response_input(prompt, model, schema)
    counting = {name: generation[name] for name in ('model', 'input', 'reasoning', 'text', 'truncation')}
    try:
        key = api_key()
    except (RuntimeError, ValueError, OSError):
        raise CounterUnavailable('credential') from None
    req = urllib.request.Request('https://api.openai.com/v1/responses/input_tokens',
        data=json.dumps(counting).encode(),
        headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response: result = json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code if type(error.code) is int else None
        diagnostics = _http_metadata(error)
        raise CounterUnavailable('http', status, diagnostics) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise CounterUnavailable('transport') from None
    count = result.get('input_tokens') if isinstance(result, dict) else None
    if not isinstance(result, dict) or result.get('object') != 'response.input_tokens' or type(count) is not int or count <= 0:
        raise CounterUnavailable('invalid_count')
    return count


def request(prompt, model, max_tokens=24000, schema=None):
    if model not in (MODEL, 'text-embedding-3-small'):
        raise ValueError('Unsupported OpenAI model')
    if type(max_tokens) is not int or not 1 <= max_tokens <= 128000:
        raise ValueError('Invalid output allowance')
    if not isinstance(schema, dict):
        raise ValueError('An explicit output schema is required')
    key = api_key()
    if model == 'text-embedding-3-small':
        return embedding_request(prompt,key)
    mode, retries, flex_timeout = _flex_config()
    started = time.monotonic()
    flex_attempts = 0
    tier = 'flex' if mode == 'flex_fallback' else 'default'
    while True:
        if tier == 'flex':
            flex_attempts += 1
        payload = {**response_input(prompt, model, schema), 'max_output_tokens': max_tokens,
                   'store': False, 'stream': True}
        payload['service_tier'] = tier
        req = urllib.request.Request('https://api.openai.com/v1/responses',
            data=json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        retryable = False
        attempt_started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=flex_timeout if tier == 'flex' else 60) as response:
                result = collect_stream(response,
                    attempt_started + (flex_timeout if tier == 'flex' else 420), model, tier)
            retryable = result.pop('_transport_timeout', False)
        except urllib.error.HTTPError as error:
            status = error.code
            diagnostics = _http_metadata(error)
            result = {'error': 'HTTP ' + str(status), 'usage_final': False,
                      'stop_reason': None, **diagnostics}
            retryable = (type(status) is int and 500 <= status <= 599) or (
                status == 429 and (diagnostics['provider_error_code'] in
                    ('flex_unavailable', 'resource_unavailable') or
                    diagnostics['provider_error_type'] == 'resource_unavailable'))
        except Exception as error:
            result = {'error': type(error).__name__, 'usage_final': False, 'stop_reason': None}
            retryable = _is_timeout(error)
        if tier == 'flex' and retryable:
            if flex_attempts <= retries:
                time.sleep(2 if flex_attempts == 1 else 5)
            else:
                tier = 'default'
            continue
        for name in ('returned_service_tier', 'terminal_status', 'incomplete_reason',
                     'provider_error_code', 'provider_error_type'):
            result.setdefault(name, None)
        result['requested_service_tier'] = tier
        result['flex_attempts'] = flex_attempts
        result.setdefault('reasoning_effort', REASONING_EFFORT)
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        return result


def embedding_request(prompt, key):
    inputs=json.loads(prompt)
    if not isinstance(inputs,list) or not 1<=len(inputs)<=32 or any(not isinstance(t,str) or not t.strip() or len(t.encode())>8000 for t in inputs):
        raise ValueError('Invalid embedding inputs')
    payload={'model':'text-embedding-3-small','input':inputs,'dimensions':1536,'encoding_format':'float'}
    req=urllib.request.Request('https://api.openai.com/v1/embeddings',data=json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    started=time.monotonic()
    try:
        with urllib.request.urlopen(req,timeout=60) as response: raw=json.load(response)
        data=raw.get('data',[])
        if raw.get('model')!='text-embedding-3-small' or sorted(d.get('index',-1) for d in data)!=list(range(len(inputs))):
            raise ValueError('Embedding response identity mismatch')
        result={'model':raw['model'],'embeddings':[d['embedding'] for d in sorted(data,key=lambda d:d['index'])],
                'stop_reason':'end_turn','usage_final':True,
                'usage':{'input_tokens':raw['usage']['prompt_tokens'],'output_tokens':0}}
    except urllib.error.HTTPError as error:
        result={'error':'HTTP '+str(error.code),'stop_reason':None,'usage_final':False,
                **_http_metadata(error)}
    except Exception as error:result={'error':type(error).__name__,'stop_reason':None,'usage_final':False}
    for name in ('provider_error_code', 'provider_error_type', 'returned_service_tier'):
        result.setdefault(name, None)
    result['requested_service_tier'] = 'default'
    result['flex_attempts'] = 0
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result
