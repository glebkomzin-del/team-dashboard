"""Decode replay answers and report numeric quality/cost comparisons only."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

common = load('replay_common')
codec = load('delta_codec')
schemas = load('delta_schema')


def strict_equal(a, b):
    if type(a) is not type(b): return False
    if isinstance(a, dict):
        return set(a) == set(b) and all(strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(strict_equal(x, y) for x, y in zip(a, b))
    return a == b


def compare_full(actual, reference):
    """Positive checks; missing coverage can never count as matching decisions."""
    ao, ro = actual.get('observations'), reference.get('observations')
    if not isinstance(ao, list) or not isinstance(ro, list):
        return {'coverage': 0, 'decisions': 0, 'lifecycle': 0, 'final': 0}
    def indexes(items):
        result = {}
        for item in items:
            if not isinstance(item, dict) or type(item.get('source_index')) not in (int, str):
                return None
            idx = item['source_index']
            if idx in result: return None
            result[idx] = item
        return result
    am, rm = indexes(ao), indexes(ro)
    covered = am is not None and rm is not None and set(am) == set(rm)
    fields = ('update_target', 'update', 'matter_id')
    decisions = covered and all(all(k in am[i] and k in rm[i] and strict_equal(am[i][k], rm[i][k]) for k in fields) for i in rm)
    def changes(full):
        values = full.get('work_results')
        if not isinstance(values, dict): return None
        return {k: v for k, v in values.items() if v != 'unchanged'}
    ac, rc = changes(actual), changes(reference)
    lifecycle = ac is not None and rc is not None and strict_equal(ac, rc)
    # open_ids is a request for another phase: it does not establish final quality.
    final = actual.get('open_ids') == [] and reference.get('open_ids') == []
    return {'coverage': int(covered), 'decisions': int(decisions),
            'lifecycle': int(lifecycle), 'final': int(final)}


def compare_attempt(attempt, record):
    result = {'schema': 0, 'coverage': 0, 'decisions': 0, 'lifecycle': 0,
              'final': 0, 'accepted': 0, 'output_tokens': 0,
              'reference_output_tokens': record.get('reference_usage', {}).get('output_tokens', 0)}
    usage = attempt.get('usage', {})
    n = usage.get('output_tokens')
    if type(n) is int and n >= 0: result['output_tokens'] = n
    if attempt.get('status') != 'ok': return result
    try:
        delta = common.parse_json(attempt['text'])
        if common.schema_errors(delta, record['request_json']['schema']): return result
        full = codec.from_delta(delta, record['obs_in'], record['work'])
        if common.schema_errors(full, schemas.full_schema_for_validation(record['reference_schema'])): return result
        result['schema'] = 1
        result.update(compare_full(full, record['reference_full']))
        result['accepted'] = int(all(result[k] for k in ('schema','coverage','decisions','lifecycle','final')))
    except (ValueError, TypeError, KeyError, IndexError):
        pass
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', default=str(ROOT / 'selected_requests.jsonl'))
    parser.add_argument('--results', default=str(ROOT / 'replay_ledger.jsonl'))
    args = parser.parse_args(argv)
    try:
        records = {r['replay_id']: r for r in common.read_jsonl(args.requests)}
        rows = []
        seen = set()
        for attempt in common.read_jsonl(args.results):
            if attempt.get('record_type') != 'attempt': continue
            rid = attempt['replay_id']
            if rid in seen or rid not in records: raise ValueError('Invalid replay identity')
            seen.add(rid)
            rows.append(compare_attempt(attempt, records[rid]))
        totals = {k: sum(r[k] for r in rows) for k in ('schema','coverage','decisions','lifecycle','final','accepted','output_tokens','reference_output_tokens')}
        totals.update(attempts=len(rows), selected=len(records), missing=len(records)-len(rows))
        print(json.dumps(totals, sort_keys=True))
        return 0 if len(rows) == len(records) and totals['accepted'] == len(records) else 1
    except (ValueError, OSError, KeyError, TypeError):
        print('Comparison stopped: invalid local input.', file=__import__('sys').stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
