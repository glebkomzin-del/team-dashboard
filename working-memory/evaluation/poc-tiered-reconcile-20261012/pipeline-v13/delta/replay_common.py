"""Copied from ../model-replay/replay_common.py; output guard renamed for this package."""
"""Shared, side-effect-free stdlib helpers. No provider or credential imports."""
import json
import math
import re
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Control cap explicitly authorized by the requester on 2026-10-13.
CONTROL_CAP_MICRO_USD = 950000
RATES = {
    'gpt-6-luna': tuple(map(Decimal, ('0.10', '0.01', '0.50'))),
    'gpt-6.1-sol': tuple(map(Decimal, ('2.00', '0.10', '2.50', '10.00'))),
}


def output_path(path):
    result = Path(path).resolve()
    if result == ROOT or ROOT not in result.parents:
        raise ValueError('Output must be inside delta')
    return result


def parse_json(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    def invalid(_):
        raise ValueError('Nonfinite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = parse_json(line)
                if not isinstance(record, dict):
                    raise ValueError('Expected object')
            except (ValueError, TypeError) as error:
                raise ValueError('Invalid JSONL record at line ' + str(number)) from None
            yield record


def usage_micro_usd(usage, model):
    """USD/million equals micro-USD/token. Output already includes reasoning."""
    if model not in RATES or not isinstance(usage, dict):
        return None
    if any(type(usage.get(k)) is not int or usage[k] < 0
           for k in ('input_tokens', 'output_tokens')):
        return None
    details = usage.get('input_tokens_details', {})
    if not isinstance(details, dict):
        return None
    cached = details.get('cached_tokens', 0)
    written = details.get('cache_write_tokens', 0)
    if (type(cached) is not int or type(written) is not int or
            cached < 0 or written < 0 or cached + written > usage['input_tokens']):
        return None
    rates = RATES[model]
    if len(rates) == 3:
        if written:
            return None
        ip, cp, op = rates
        wp = ip
    else:
        ip, cp, wp, op = rates
    cost = ((usage['input_tokens'] - cached - written) * ip + cached * cp +
            written * wp + usage['output_tokens'] * op)
    return int(cost.to_integral_value(rounding=ROUND_CEILING))


def replay_identity(record):
    """Require positive agreement of all replay identity fields."""
    if not isinstance(record, dict):
        raise ValueError('Invalid replay identity')
    key = (record.get('job_id'), record.get('call_index'), record.get('replay_variant'))
    if (not isinstance(key[0], str) or not key[0] or type(key[1]) is not int or key[1] < 0
            or key[2] not in ('filtered', 'control')):
        raise ValueError('Invalid replay identity')
    canonical = f'{key[0]}:{key[1]}:{key[2]}'
    if record.get('replay_id') != canonical or ('variant' in record and record['variant'] != key[2]):
        raise ValueError('Contradictory replay identity')
    return key


def completed_replay_ids(paths):
    """All durable attempts are paid evidence, regardless of attempt status."""
    completed = set()
    for path in paths:
        for record in read_jsonl(path):
            replay_identity(record)
            completed.add(record['replay_id'])
    return completed


ANNOTATIONS = {'$schema', '$id', '$defs', 'definitions', 'title', 'description',
               'default', 'examples', 'deprecated', 'readOnly', 'writeOnly', '$comment'}
KEYWORDS = ANNOTATIONS | {'$ref', 'type', 'enum', 'const', 'anyOf', 'oneOf', 'allOf',
    'not', 'properties', 'required', 'additionalProperties', 'patternProperties',
    'items', 'prefixItems', 'minItems', 'maxItems', 'uniqueItems', 'minProperties',
    'maxProperties', 'minLength', 'maxLength', 'pattern', 'minimum', 'maximum',
    'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf'}


def validate_schema_structure(schema):
    """Offline structural validation of the copied validator's supported subset.

    This is not a complete JSON Schema metaschema implementation. Unsupported
    keywords and external references are rejected rather than silently ignored.
    """
    references = []
    def visit(node, depth=0):
        if depth > 100:
            raise ValueError('Schema nesting limit')
        if isinstance(node, bool):
            return
        if not isinstance(node, dict) or set(node) - KEYWORDS:
            raise ValueError('Unsupported or invalid schema structure')
        if 'type' in node:
            kinds = node['type'] if isinstance(node['type'], list) else [node['type']]
            if not kinds or any(not isinstance(k, str) or k not in
                    {'null', 'boolean', 'object', 'array', 'string', 'integer', 'number'} for k in kinds) or len(set(kinds)) != len(kinds):
                raise ValueError('Invalid schema type')
        if 'enum' in node:
            choices = node['enum']
            if not isinstance(choices, list) or not choices:
                raise ValueError('Invalid schema enum')
            keys = [json.dumps(c, sort_keys=True, allow_nan=False) for c in choices]
            if len(set(keys)) != len(keys):
                raise ValueError('Duplicate schema enum')
        for key in ('properties', 'patternProperties', '$defs', 'definitions'):
            if key in node:
                if not isinstance(node[key], dict):
                    raise ValueError('Invalid schema mapping')
                for name, child in node[key].items():
                    if not isinstance(name, str):
                        raise ValueError('Invalid schema property')
                    if key == 'patternProperties':
                        re.compile(name)
                    visit(child, depth + 1)
        if 'required' in node:
            required = node['required']
            if not isinstance(required, list) or any(not isinstance(k, str) for k in required) or len(set(required)) != len(required):
                raise ValueError('Invalid schema required')
        for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
            if key in node:
                if not isinstance(node[key], list) or not node[key]:
                    raise ValueError('Invalid schema combinator')
                for child in node[key]:
                    visit(child, depth + 1)
        for key in ('items', 'additionalProperties', 'not'):
            if key in node:
                visit(node[key], depth + 1)
        for key in ('minItems', 'maxItems', 'minProperties', 'maxProperties', 'minLength', 'maxLength'):
            if key in node and (type(node[key]) is not int or node[key] < 0):
                raise ValueError('Invalid schema size constraint')
        for key in ('minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf'):
            if key in node and (type(node[key]) not in (int, float) or not math.isfinite(node[key]) or (key == 'multipleOf' and node[key] <= 0)):
                raise ValueError('Invalid numeric schema constraint')
        if 'uniqueItems' in node and type(node['uniqueItems']) is not bool:
            raise ValueError('Invalid uniqueItems')
        if 'pattern' in node:
            if not isinstance(node['pattern'], str):
                raise ValueError('Invalid schema pattern')
            re.compile(node['pattern'])
        if '$ref' in node:
            if not isinstance(node['$ref'], str) or not node['$ref'].startswith('#/'):
                raise ValueError('Only local schema references supported')
            references.append(node['$ref'])
    try:
        json.dumps(schema, allow_nan=False)
        visit(schema)
        for ref in references:
            value = schema
            for part in ref[2:].split('/'):
                value = value[part.replace('~1', '/').replace('~0', '~')]
            if not isinstance(value, (dict, bool)):
                raise ValueError('Invalid reference target')
    except (TypeError, KeyError, re.error, OverflowError, RecursionError):
        raise ValueError('Invalid schema structure') from None
    return True


def schema_errors(value, schema):
    """Validate the recorded JSON Schema subset; unsupported keywords fail closed.

    Paths/diagnostics contain no answer values. Local refs only, no network.
    """
    errors = []
    def preflight(node, depth=0):
        if depth > 100:
            raise ValueError('Schema nesting limit')
        if isinstance(node, bool):
            return
        if not isinstance(node, dict):
            raise ValueError('Invalid schema node')
        if set(node) - KEYWORDS:
            raise ValueError('Unsupported schema keyword')
        for key in ('properties', 'patternProperties', '$defs', 'definitions'):
            for child in node.get(key, {}).values():
                preflight(child, depth + 1)
        for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
            for child in node.get(key, []):
                preflight(child, depth + 1)
        for key in ('items', 'additionalProperties', 'not'):
            if key in node:
                preflight(node[key], depth + 1)
        if '$ref' in node and not node['$ref'].startswith('#/'):
            raise ValueError('Only local schema refs supported')

    def walk(v, s, path='$', depth=0):
        if depth > 100:
            return [path + ': validation depth exceeded']
        if isinstance(s, bool):
            return [] if s else [path + ': forbidden value']
        failures = []
        if '$ref' in s:
            ref = schema
            for part in s['$ref'][2:].split('/'):
                ref = ref[part.replace('~1', '/').replace('~0', '~')]
            failures += walk(v, ref, path, depth + 1)
        for keyword in ('anyOf', 'oneOf', 'allOf'):
            if keyword in s:
                matches = sum(not walk(v, child, path, depth + 1) for child in s[keyword])
                if ((keyword == 'anyOf' and matches == 0) or
                    (keyword == 'oneOf' and matches != 1) or
                    (keyword == 'allOf' and matches != len(s[keyword]))):
                    failures.append(path + ': ' + keyword + ' failed')
        if 'not' in s and not walk(v, s['not'], path, depth + 1):
            failures.append(path + ': not failed')
        def kind(name):
            return {'null': v is None, 'boolean': type(v) is bool,
                'object': isinstance(v, dict), 'array': isinstance(v, list),
                'string': isinstance(v, str), 'integer': type(v) is int or
                    (type(v) is float and math.isfinite(v) and v.is_integer()),
                'number': type(v) in (int, float) and math.isfinite(v)}[name]
        if 'type' in s:
            types = s['type'] if isinstance(s['type'], list) else [s['type']]
            if not any(kind(t) for t in types):
                return failures + [path + ': wrong type']
        def equal(a, b):
            # JSON bool must not compare equal to numeric 0/1.
            if type(a) is bool or type(b) is bool:
                return type(a) is type(b) and a == b
            if isinstance(a, dict) and isinstance(b, dict):
                return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
            if isinstance(a, list) and isinstance(b, list):
                return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
            return a == b
        if 'enum' in s and not any(equal(v, item) for item in s['enum']):
            failures.append(path + ': enum failed')
        if 'const' in s and not equal(v, s['const']):
            failures.append(path + ': const failed')
        if isinstance(v, dict):
            if any(k not in v for k in s.get('required', [])):
                failures.append(path + ': required property missing')
            props = s.get('properties', {})
            for key, item in v.items():
                matched = key in props
                if matched:
                    failures += walk(item, props[key], path + '.*', depth + 1)
                for pattern, sub in s.get('patternProperties', {}).items():
                    if re.search(pattern, key):
                        matched = True
                        failures += walk(item, sub, path + '.*', depth + 1)
                if not matched:
                    failures += walk(item, s.get('additionalProperties', True), path + '.*', depth + 1)
            for keyword, condition in (('minProperties', len(v) < s.get('minProperties', 0)),
                                       ('maxProperties', len(v) > s.get('maxProperties', math.inf))):
                if condition: failures.append(path + ': ' + keyword + ' failed')
        if isinstance(v, list):
            prefix = s.get('prefixItems', [])
            for i, item in enumerate(v):
                sub = prefix[i] if i < len(prefix) else s.get('items', True)
                failures += walk(item, sub, path + '[]', depth + 1)
            if len(v) < s.get('minItems', 0) or len(v) > s.get('maxItems', math.inf):
                failures.append(path + ': array length failed')
            if s.get('uniqueItems') and any(equal(v[i], v[j]) for i in range(len(v)) for j in range(i)):
                failures.append(path + ': uniqueItems failed')
        if isinstance(v, str):
            if len(v) < s.get('minLength', 0) or len(v) > s.get('maxLength', math.inf):
                failures.append(path + ': string length failed')
            if 'pattern' in s and not re.search(s['pattern'], v):
                failures.append(path + ': pattern failed')
        if type(v) in (int, float):
            if not math.isfinite(v):
                failures.append(path + ': nonfinite number')
            for key, wrong in (('minimum', v < s.get('minimum', -math.inf)),
                ('maximum', v > s.get('maximum', math.inf)),
                ('exclusiveMinimum', v <= s.get('exclusiveMinimum', -math.inf)),
                ('exclusiveMaximum', v >= s.get('exclusiveMaximum', math.inf))):
                if wrong: failures.append(path + ': ' + key + ' failed')
            if 'multipleOf' in s and Decimal(str(v)) % Decimal(str(s['multipleOf'])):
                failures.append(path + ': multipleOf failed')
        return failures
    try:
        validate_schema_structure(schema)
        preflight(schema)
        errors = walk(value, schema)
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError):
        errors = ['$: unsupported or invalid schema']
    return errors

import http.client
import os
import time
import urllib.error
import urllib.request

def response_body(raw):
    """Parse retained raw SSE; terminal object is the provider's complete response."""
    try:
        body = parse_json(raw)
        if isinstance(body, dict):
            return body, None
    except ValueError:
        pass
    terminal = None
    error = None
    data = []
    def event(lines):
        nonlocal terminal, error
        if not lines or ''.join(lines).strip() == '[DONE]':
            return
        value = parse_json('\n'.join(lines))
        if not isinstance(value, dict):
            raise ValueError('Invalid SSE event')
        kind = value.get('type')
        if kind in ('response.completed', 'response.incomplete', 'response.failed'):
            if terminal is not None:
                raise ValueError('Duplicate terminal SSE event')
            terminal = value.get('response')
            if not isinstance(terminal, dict) or terminal.get('status') != kind.split('.')[1]:
                raise ValueError('Terminal SSE status mismatch')
        elif kind == 'error':
            error = value
    try:
        for line in raw.splitlines() + ['']:
            if line.startswith('data:'):
                data.append(line[5:].lstrip())
            elif not line:
                event(data)
                data = []
    except (ValueError, TypeError):
        return terminal, {'type': 'invalid_stream', 'message': 'Invalid SSE event stream'}
    if error is not None:
        return terminal, {'type': 'provider_stream_error', 'detail': error}
    if terminal is None:
        return None, {'type': 'incomplete_stream', 'message': 'No terminal response event'}
    return terminal, None


def answer_text(body):
    if not isinstance(body, dict):
        return None
    parts = []
    for item in body.get('output', []) if isinstance(body.get('output'), list) else []:
        if isinstance(item, dict) and item.get('type') == 'message':
            for block in item.get('content', []) if isinstance(item.get('content'), list) else []:
                if isinstance(block, dict) and block.get('type') == 'output_text' and isinstance(block.get('text'), str):
                    parts.append(block['text'])
    return ''.join(parts) if parts else None


def content_error(body, text, payload):
    if not isinstance(body, dict) or body.get('status') != 'completed':
        return 'Provider response not completed'
    if body.get('model') != payload['model']:
        return 'Unexpected provider model'
    if body.get('service_tier') != 'default':
        return 'Standard service tier not confirmed'
    messages = 0
    output = body.get('output')
    if not isinstance(output, list):
        return 'Missing output items'
    for item in output:
        if not isinstance(item, dict):
            return 'Invalid output item'
        if item.get('type') == 'reasoning':
            if item.get('status') not in (None, 'completed'):
                return 'Incomplete reasoning item'
            continue
        if item.get('type') != 'message' or item.get('role') != 'assistant' or item.get('status') != 'completed':
            return 'Invalid assistant message'
        messages += 1
        blocks = item.get('content')
        if not isinstance(blocks, list) or not blocks or any(
            not isinstance(b, dict) or b.get('type') != 'output_text' or not isinstance(b.get('text'), str)
            for b in blocks):
            return 'Refusal or invalid output content'
    if messages != 1 or text is None:
        return 'Missing structured output'
    try:
        value = parse_json(text)
    except (ValueError, TypeError):
        return 'Answer is not valid JSON'
    if schema_errors(value, payload['text']['format']['schema']):
        return 'Answer does not satisfy recorded schema'
    return None


class OpenAITransport:
    """Created solely by --execute; no credential files, no redirects."""
    def __init__(self):
        self.key = os.environ.get('OPENAI_API_KEY')
        if not self.key:
            raise ValueError('OPENAI_API_KEY environment variable missing')

    def redact(self, value):
        # Exceptional redaction takes precedence over raw-body fidelity.
        return value.replace(self.key, '[REDACTED_API_KEY]')

    def __call__(self, payload):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        request = urllib.request.Request('https://api.openai.com/v1/responses',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json',
                     'Accept': 'text/event-stream'})
        chunks = []
        status = None
        deadline = time.monotonic() + 420
        try:
            with opener.open(request, timeout=60) as response:
                status = response.status
                for line in response:
                    chunks.append(line)
                    if time.monotonic() > deadline:
                        raise TimeoutError('Total request deadline exceeded')
            return {'http_status': status, 'raw_response': self.redact(b''.join(chunks).decode('utf-8', 'replace'))}
        except urllib.error.HTTPError as error:
            error_chunks = []
            read_error = None
            try:
                while True:
                    chunk = error.read(65536)
                    if not chunk:
                        break
                    error_chunks.append(chunk)
            except (OSError, http.client.HTTPException) as reading_error:
                if isinstance(reading_error, http.client.IncompleteRead) and isinstance(reading_error.partial, bytes):
                    error_chunks.append(reading_error.partial)
                read_error = self.redact(str(reading_error))
            finally:
                error.close()
            raw = b''.join(error_chunks).decode('utf-8', 'replace')
            return {'http_status': error.code, 'raw_response': self.redact(raw),
                    'http_error': self.redact(str(error)), 'body_read_error': read_error}
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            if isinstance(error, http.client.IncompleteRead) and isinstance(error.partial, bytes):
                chunks.append(error.partial)
            return {'http_status': status,
                'raw_response': self.redact(b''.join(chunks).decode('utf-8', 'replace')),
                'transport_error': self.redact(str(error)), 'exception_type': type(error).__name__}

