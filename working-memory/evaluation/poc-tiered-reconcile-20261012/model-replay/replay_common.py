"""Shared, side-effect-free stdlib helpers. No provider or credential imports."""
import json
import math
import re
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RATES = {
    'gpt-6-luna': tuple(map(Decimal, ('0.10', '0.01', '0.50'))),
    'gpt-6.1-sol': tuple(map(Decimal, ('2.00', '0.10', '10.00'))),
}


def output_path(path):
    result = Path(path).resolve()
    if result == ROOT or ROOT not in result.parents:
        raise ValueError('Output must be inside model-replay')
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
    if type(cached) is not int or not 0 <= cached <= usage['input_tokens']:
        return None
    # Prices supplied by the mandate include cache reads, not cache writes.
    if details.get('cache_write_tokens', 0) != 0:
        return None
    ip, cp, op = RATES[model]
    cost = (usage['input_tokens'] - cached) * ip + cached * cp + usage['output_tokens'] * op
    return int(cost.to_integral_value(rounding=ROUND_CEILING))


ANNOTATIONS = {'$schema', '$id', '$defs', 'definitions', 'title', 'description',
               'default', 'examples', 'deprecated', 'readOnly', 'writeOnly', '$comment'}
KEYWORDS = ANNOTATIONS | {'$ref', 'type', 'enum', 'const', 'anyOf', 'oneOf', 'allOf',
    'not', 'properties', 'required', 'additionalProperties', 'patternProperties',
    'items', 'prefixItems', 'minItems', 'maxItems', 'uniqueItems', 'minProperties',
    'maxProperties', 'minLength', 'maxLength', 'pattern', 'minimum', 'maximum',
    'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf'}


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
        preflight(schema)
        errors = walk(value, schema)
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError):
        errors = ['$: unsupported or invalid schema']
    return errors
