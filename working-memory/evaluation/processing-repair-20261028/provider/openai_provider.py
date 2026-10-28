"""Sol Responses adapter; production Standard or opt-in bounded Flex fallback.

Translate only the transport envelope. All source, work and summary schemas and
validators remain in the existing pipeline. Partial output is never accepted.
"""
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request
from durable_calls import SharedProviderFailure

MODEL = 'gpt-6.1-sol'
REASONING_EFFORT = 'medium'  # Standard production reasoning; no provider fallback.

# Only recognized technical codes may leave a failed stream; messages stay private.
_STREAM_ERROR_CODES = frozenset(('flex_unavailable', 'resource_unavailable', 'server_error',
    'rate_limit_exceeded', 'invalid_request_error', 'invalid_json_schema',
    'context_length_exceeded', 'unsupported_parameter', 'invalid_value',
    'model_not_found', 'insufficient_quota'))


class CounterUnavailable(SharedProviderFailure):
    def __init__(self, kind, http_status=None):
        self.kind = kind
        self.http_status = http_status
        diagnostic = {'component': 'input_token_counter', 'type': kind,
                      'http_status': http_status}
        print(json.dumps(diagnostic, separators=(',', ':')), file=sys.stderr, flush=True)
        super().__init__('Provider input token count unavailable')


def _metadata_text(value, limit=80):
    """Only bounded, non-prose terminal metadata; never copy error messages."""
    return value if isinstance(value, str) and 0 < len(value) <= limit and all(
        character.isascii() and (character.isalnum() or character in '._-') for character in value
    ) else None


def normalize(response, model, requested_service_tier='default'):
    result = {'provider': 'openai', 'id': response.get('id'),
              'model': response.get('model'), 'content': [],
              'usage': response.get('usage') or {}, 'usage_final': False,
              'stop_reason': None, 'reasoning_effort': REASONING_EFFORT,
              'requested_service_tier': requested_service_tier,
              'returned_service_tier': _metadata_text(response.get('service_tier')),
              'terminal_status': _metadata_text(response.get('status')),
              'incomplete_reason': None, 'provider_error_code': None}
    details = response.get('incomplete_details')
    if isinstance(details, dict):
        result['incomplete_reason'] = _metadata_text(details.get('reason'))
    error_detail = response.get('error')
    if isinstance(error_detail, dict):
        result['provider_error_code'] = _metadata_text(error_detail.get('code'))
    if response.get('model') != model:
        result['error'] = 'Unexpected provider model'
        return result
    status = response.get('status')
    result['usage_final'] = status in ('completed', 'incomplete', 'failed') and isinstance(response.get('usage'), dict)
    if status != 'completed':
        result['error'] = 'Provider response not completed'
        return result
    if result['returned_service_tier'] != requested_service_tier:
        result['error'] = ('Requested standard service tier not confirmed' if requested_service_tier == 'default'
                           else 'Requested flex service tier not confirmed')
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
    stream_error_kind = None
    provider_error_code = None
    def event(lines):
        nonlocal stream_error_kind, provider_error_code
        if not lines:
            return None
        stream_error_kind = 'malformed_event'
        value = json.loads('\n'.join(lines))
        stream_error_kind = 'invalid_event'
        if not isinstance(value, dict):
            raise ValueError('Invalid stream event')
        kind = value.get('type')
        if kind in ('response.completed', 'response.incomplete', 'response.failed'):
            body = value.get('response', {})
            if not isinstance(body, dict):
                raise ValueError('Invalid terminal response')
            if body.get('status') != kind.split('.')[1]:
                stream_error_kind = 'terminal_status_mismatch'
                raise ValueError('Terminal response status mismatch')
            return normalize(body, model, requested_service_tier)
        if kind == 'error':
            stream_error_kind = 'provider_error'
            code = value.get('code')
            provider_error_code = code if isinstance(code, str) and code in _STREAM_ERROR_CODES else None
            raise ValueError('Provider stream error')
        stream_error_kind = None
        return None
    try:
        for raw_line in (response if requested_service_tier == 'default' else _deadline_lines(response, deadline)):
            if time.monotonic() > deadline:
                stream_error_kind = 'deadline_exceeded'
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
        stream_error_kind = 'incomplete_stream'
        raise ValueError('Incomplete event stream')
    except Exception as error:
        # Never persist provider error bodies, which may contain private input.
        return {'provider': 'openai', 'content': [], 'usage': {},
                'usage_final': False, 'stop_reason': None, 'error': type(error).__name__,
                'requested_service_tier': requested_service_tier, 'returned_service_tier': None,
                'terminal_status': None, 'incomplete_reason': None,
                'provider_error_code': provider_error_code, 'reasoning_effort': REASONING_EFFORT,
                'stream_error_kind': stream_error_kind or 'transport_error'}


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
        error.close()
        raise CounterUnavailable('http', status) from None
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
    tier = os.environ.get('DASHBOARD_SERVICE_TIER', 'default')
    if tier not in ('default', 'flex_fallback'):
        raise ValueError('Invalid service tier policy')
    if tier == 'flex_fallback':
        return _flex_request(prompt, model, max_tokens, schema, key)
    payload = {**response_input(prompt, model, schema), 'max_output_tokens': max_tokens,
               'store': False, 'stream': True}
    req = urllib.request.Request('https://api.openai.com/v1/responses',
        data=json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = collect_stream(response, started + 420, model)
    except urllib.error.HTTPError as error:
        result = {'error': 'HTTP ' + str(error.code), 'usage_final': False, 'stop_reason': None}
        error.close()
    except Exception as error:
        result = {'error': type(error).__name__, 'usage_final': False, 'stop_reason': None}
    for name in ('returned_service_tier','terminal_status','incomplete_reason','provider_error_code'):
        result.setdefault(name, None)
    result.setdefault('requested_service_tier','default')
    result.setdefault('reasoning_effort',REASONING_EFFORT)
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    result['flex_attempts'] = 0
    return result


# HTTP bodies are inspected only for this exact, bounded retry decision.
_ERROR_BODY_LIMIT = 65536


def _strict_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate JSON key')
        result[name] = value
    return result


def _socket_deadline(response, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Total request deadline exceeded')
    # urllib's HTTPResponse owns this socket; synthetic offline responses need none.
    owner = getattr(response, 'fp', None)
    if owner is not None and getattr(owner, 'raw', None) is None:
        owner = getattr(owner, 'fp', None)
    socket = getattr(getattr(owner, 'raw', None), '_sock', None)
    if socket is not None:
        socket.settimeout(min(60, remaining))


def _deadline_lines(response, deadline):
    iterator = iter(response)
    while True:
        _socket_deadline(response, deadline)
        try:
            line = next(iterator)
        except StopIteration:
            return
        if time.monotonic() > deadline:
            raise TimeoutError('Total request deadline exceeded')
        yield line


def _flex_unavailable(error, deadline):
    if error.code != 429:
        return False
    _socket_deadline(error, deadline)
    raw = error.read(_ERROR_BODY_LIMIT + 1)
    if time.monotonic() > deadline:
        raise TimeoutError('Total request deadline exceeded')
    if len(raw) > _ERROR_BODY_LIMIT:
        return False
    try:
        body = json.loads(raw, object_pairs_hook=_strict_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON constant')))
    except (ValueError, UnicodeError):
        return False
    detail = body.get('error') if isinstance(body, dict) else None
    return isinstance(detail, dict) and (detail.get('code') == 'flex_unavailable'
                                        or detail.get('type') == 'resource_unavailable')


def _flex_request(prompt, model, max_tokens, schema, key):
    # A slow partial SSE line can evade socket inactivity timeouts. Admission
    # and cancellation are serialized, but an admitted request is not aborted.
    timeout = float(os.environ.get('DASHBOARD_FLEX_TIMEOUT_SECONDS', '480'))
    retries = int(os.environ.get('DASHBOARD_FLEX_RETRIES', '2'))
    if retries < 0 or not 0 < timeout <= 480:
        raise ValueError('Invalid Flex retry or timeout configuration')
    started = time.monotonic()
    cancelled, done, wake = threading.Event(), threading.Event(), threading.Event()
    gate = threading.Lock()
    state = {'flex_attempts': 0, 'requested_service_tier': 'flex',
             'deadline': started + timeout, 'inflight': False}
    def run():
        try:
            result = _flex_chain(prompt, model, max_tokens, schema, key,
                                 retries, started, started + timeout, cancelled, state, gate, wake)
            with gate:
                state['result'] = result
        except Exception as error:
            with gate:
                state['exception'] = error
        finally:
            with gate:
                done.set()
                wake.set()
    threading.Thread(target=run, daemon=True, name='flex-transport').start()
    while True:
        with gate:
            if done.is_set():
                if 'exception' in state:
                    raise state['exception']
                return state['result']
            remaining = state['deadline'] - time.monotonic()
            if remaining <= 0:
                cancelled.set()
                return {'error': 'TimeoutError', 'usage_final': False, 'stop_reason': None,
                        'returned_service_tier': None, 'terminal_status': None,
                        'incomplete_reason': None, 'provider_error_code': None,
                        'requested_service_tier': state['requested_service_tier'],
                        'reasoning_effort': REASONING_EFFORT, 'flex_attempts': state['flex_attempts'],
                        'elapsed_seconds': round(time.monotonic() - started, 3)}
            wake.clear()
        # Admission of Standard tightens this wait to its own 420s deadline.
        wake.wait(remaining)


def _dispatch(req, requested, state, gate, cancelled, wake, chain_deadline):
    """Atomically admit at most one active attempt before cancellation.

    Once admitted the attempt is outcome-unknown on timeout; thread scheduling
    may delay its first network bytes. Cancellation forbids later admissions,
    not physical continuation of this already admitted request.
    """
    with gate:
        now = time.monotonic()
        if cancelled.is_set() or now >= chain_deadline:
            raise TimeoutError('Total request deadline exceeded')
        if requested == 'flex':
            state['flex_attempts'] += 1
        state['requested_service_tier'] = requested
        state['inflight'] = True
        state['deadline'] = chain_deadline if requested == 'flex' else min(now + 420, chain_deadline)
        attempt_deadline = state['deadline']
        wake.set()
    response = urllib.request.urlopen(req, timeout=min(60, attempt_deadline - now))
    return response, attempt_deadline


def _backoff(cancelled, delay):
    return cancelled.wait(delay)


def _flex_chain(prompt, model, max_tokens, schema, key, retries, started, deadline, cancelled, state, gate, wake):
    flex_attempts = 0
    requested = 'flex'
    result = None
    for attempt in range(retries + 2):
        requested = 'flex' if attempt <= retries else 'default'
        try:
            remaining = deadline - time.monotonic()
            if cancelled.is_set() or remaining <= 0:
                raise TimeoutError('Total request deadline exceeded')
            payload = {**response_input(prompt, model, schema), 'max_output_tokens': max_tokens,
                       'store': False, 'stream': True}
            payload['service_tier'] = requested
            req = urllib.request.Request('https://api.openai.com/v1/responses',
                data=json.dumps(payload).encode(),
                headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
            response, attempt_deadline = _dispatch(req, requested, state, gate, cancelled, wake, deadline)
            flex_attempts = state['flex_attempts']
            with response:
                # Both Flex and the sole Standard fallback obey the shared deadline.
                stream = response if requested == 'flex' else _deadline_lines(response, attempt_deadline)
                result = collect_stream(stream, attempt_deadline, model, requested)
            break
        except urllib.error.HTTPError as error:
            try:
                retry = requested == 'flex' and _flex_unavailable(error, deadline)
                result = {'error': 'HTTP ' + str(error.code), 'usage_final': False, 'stop_reason': None}
            except Exception as read_error:
                retry = False
                result = {'error': type(read_error).__name__, 'usage_final': False, 'stop_reason': None}
            finally:
                error.close()
                with gate:
                    state['inflight'] = False
            if cancelled.is_set():
                result = {'error': 'TimeoutError', 'usage_final': False, 'stop_reason': None}
                break
            if not retry:
                break
            if attempt < retries:
                delay = 2 if attempt == 0 else 5
                if time.monotonic() + delay >= deadline:
                    result = {'error': 'TimeoutError', 'usage_final': False, 'stop_reason': None}
                    break
                if _backoff(cancelled, delay):
                    result = {'error': 'TimeoutError', 'usage_final': False, 'stop_reason': None}
                    break
        except Exception as error:
            result = {'error': type(error).__name__, 'usage_final': False, 'stop_reason': None}
            break
    for name in ('returned_service_tier', 'terminal_status', 'incomplete_reason', 'provider_error_code'):
        result.setdefault(name, None)
    result.setdefault('requested_service_tier', requested)
    result.setdefault('reasoning_effort', REASONING_EFFORT)
    result['flex_attempts'] = state['flex_attempts']
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
        result={'error':'HTTP '+str(error.code),'stop_reason':None,'usage_final':False};error.close()
    except Exception as error:result={'error':type(error).__name__,'stop_reason':None,'usage_final':False}
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result
