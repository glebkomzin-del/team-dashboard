"""Terra Responses adapter; one request, explicit effort, no provider fallback.

Translate only the transport envelope. All source, work and summary schemas and
validators remain in the existing pipeline. Partial output is never accepted.
"""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

MODEL = 'gpt-5.6-terra'
TEXT_MODELS = (MODEL, 'gpt-5.6-luna', 'gpt-6-sol', 'gpt-6-luna')
REASONING_EFFORT = 'none'  # Preserve the previous disabled-thinking baseline.


def normalize(response, model):
    result = {'provider': 'openai', 'id': response.get('id'),
              'model': response.get('model'), 'content': [],
              'usage': response.get('usage') or {}, 'usage_final': False,
              'stop_reason': None, 'reasoning_effort': REASONING_EFFORT}
    if response.get('model') != model:
        result['error'] = 'Unexpected provider model'
        return result
    status = response.get('status')
    result['usage_final'] = status in ('completed', 'incomplete', 'failed') and isinstance(response.get('usage'), dict)
    if status != 'completed':
        result['error'] = 'Provider response not completed'
        return result
    for item in response.get('output', []):
        if item.get('type') != 'message' or item.get('role') != 'assistant' or item.get('status') != 'completed':
            result['error'] = 'Unexpected output item'
            return result
        for block in item.get('content', []):
            if block.get('type') != 'output_text' or not isinstance(block.get('text'), str):
                result['error'] = 'Provider refused or returned unexpected content'
                return result
            result['content'].append({'type': 'text', 'text': block['text']})
    if not result['content']:
        result['error'] = 'Missing structured output'
    else:
        result['stop_reason'] = 'end_turn'
    return result


def collect_stream(response, deadline, model):
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
            return normalize(body, model)
        if kind == 'error':
            raise ValueError('Provider stream error')
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
                'usage_final': False, 'stop_reason': None, 'error': type(error).__name__}


def response_input(prompt, model, schema):
    return {'model': model, 'input': [{'role': 'user', 'content': prompt}],
            'reasoning': {'effort': REASONING_EFFORT}, 'truncation': 'disabled',
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
    if model not in TEXT_MODELS or not isinstance(schema, dict):
        raise ValueError('Unsupported counting input')
    req = urllib.request.Request('https://api.openai.com/v1/responses/input_tokens',
        data=json.dumps(response_input(prompt, model, schema)).encode(),
        headers={'Authorization': 'Bearer '+api_key(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response: result = json.load(response)
    count = result.get('input_tokens')
    if result.get('object') != 'response.input_tokens' or type(count) is not int or count <= 0:
        raise ValueError('Invalid provider token count; generation stopped')
    return count


def request(prompt, model, max_tokens=24000, schema=None):
    if model not in (*TEXT_MODELS, 'text-embedding-3-small'):
        raise ValueError('Unsupported OpenAI model')
    if type(max_tokens) is not int or not 1 <= max_tokens <= 128000:
        raise ValueError('Invalid output allowance')
    if not isinstance(schema, dict):
        raise ValueError('An explicit output schema is required')
    key = api_key()
    if model == 'text-embedding-3-small':
        return embedding_request(prompt,key)
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
