"""Read saved real calls; generate v2 using release code, without provider imports."""
import argparse
import contextlib
import importlib.util
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT.parents[2]
COMPACT_SOURCE = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/compact_calls.jsonl')
MARKER = '\nVorläufige Beobachtungen:\n'
REQUIRED = ('8bdacbe2', 'a8c4b587', '2d34a51a', 'b5e4fddb')

def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

common = load_file('build_common', ROOT/'replay_common.py')
replay = load_file('build_replay', ROOT/'replay_v2.py')
codec = load_file('build_codec', ROOT/'delta_codec.py')

def load_release(overlay):
    """Stubs cover import-time names only; called transformations are real release code."""
    overlay = Path(overlay)
    schema = load_file('release_v2_schema', overlay/'hybrid_schema.py')
    names = ('hybrid_index', 'hybrid_schema', 'memory', 'retrieval_context', 'reconcile')
    previous = {name: sys.modules.get(name) for name in names}
    try:
        for name in names:
            sys.modules[name] = types.ModuleType(name)
        sys.modules['hybrid_schema'] = schema
        sys.modules['hybrid_index'].encode = lambda x: x
        sys.modules['memory'].ValidationError = ValueError
        sys.modules['memory'].validate = lambda *a, **k: None
        sys.modules['retrieval_context'].pack_catalog = lambda x: x
        compact = load_file('release_v2_compact', overlay/'compact_reconcile.py')
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return schema, compact

def build_record(call, request, schemas, compact):
    if (call['job_id'], call['call_index']) != (request['job_id'], request['call_index']):
        raise ValueError('Identity mismatch')
    original = request['request_json']
    if original.get('model') != 'gpt-6.1-sol':
        raise ValueError('Reference model mismatch')
    prompt = compact.delta_prompt(original['prompt'])
    if prompt.split(MARKER, 1)[1] != original['prompt'].split(MARKER, 1)[1]:
        raise ValueError('Data section changed')
    full = common.parse_json(request['reference_text'])
    expected = {'observations': call['obs_out'], 'work_results': call['work_results'], 'open_ids': call['open_ids']}
    # compact_calls archive projects followup null to {}; full reference is authoritative.
    for key in ('observations', 'open_ids'):
        if not codec.equal(full.get(key), expected[key]):
            raise ValueError('Reference archive mismatch')
    if not full.get('open_ids') and not codec.equal(full.get('work_results'), expected['work_results']):
        raise ValueError('Reference lifecycle mismatch')
    cap = max(original['max_tokens'], 16000)
    generated = {**original, 'prompt': prompt, 'schema': schemas.delta_schema(original['schema']), 'max_tokens': cap}
    record = {'job_id': call['job_id'], 'call_index': call['call_index'],
        'meeting_date': call['meeting_date'], 'replay_id': f"{call['job_id']}:{call['call_index']}:delta-v2",
        'request_json': generated, 'reference_request_json': original,
        'reference_schema': original['schema'], 'reference_full': full,
        'reference_usage': request['reference_usage'], 'reference_micro_usd': request.get('reference_micro_usd'),
        'obs_in': call['obs_in'], 'work': call['work'], 'max_output_tokens': cap}
    record['next_round_reserved_micro_usd'] = replay.estimate(record)['reserved_micro_usd']
    return record

def positives(call):
    life = call.get('work_results') or {}
    return (sum(isinstance(x, dict) and x.get('action') != 'unchanged' for x in life.values()),
            sum(x.get('update_target') is not None for x in call.get('obs_out', [])))

def select(calls, requests):
    keyed = {(r['job_id'], r['call_index']): r for r in requests}
    candidates = [c for c in calls if 'work' in c and (c['job_id'], c['call_index']) in keyed and not c.get('open_ids')]
    chosen = []
    for prefix in REQUIRED:
        matches = [c for c in candidates if c['job_id'].startswith(prefix)]
        if len(matches) != 1:
            raise ValueError('Required final call ambiguous or missing')
        chosen.append(matches[0])
    small = sorted((c for c in candidates if positives(c) == (0, 0) and c not in chosen),
                   key=lambda c: (c['in_tok'], c['job_id'], c['call_index']))[:3]
    if len(small) != 3:
        raise ValueError('Three negative calls unavailable')
    chosen += small
    large = min((c for c in candidates if c not in chosen and 90000 <= c['in_tok'] <= 120000),
                key=lambda c: (abs(c['in_tok']-100000), c['in_tok']))
    return [(c, keyed[(c['job_id'], c['call_index'])]) for c in chosen+[large]]

def controls(package):
    folder = package/'filtered-replay'
    ref = {(r['job_id'], r['call_index']): r for r in common.read_jsonl(package/'model-replay/requests.jsonl')}
    rows = []
    for name in ('results-filtered-run1.jsonl', 'results-filtered-run2.jsonl'):
        for r in common.read_jsonl(folder/name):
            if r.get('replay_variant') != 'control':
                continue
            reference = common.parse_json(ref[(r['job_id'], r['call_index'])]['reference_text'])
            actual = common.parse_json(r['text'])
            mapping = {o['source_index']: o for o in actual['observations']}
            fields = ('update_target', 'update', 'matter_id')
            if r.get('status') != 'ok' or actual.get('open_ids') != [] or set(mapping) != {o['source_index'] for o in reference['observations']}:
                raise ValueError('Incomplete control evidence')
            counts = {k: sum(k in o and k in mapping[o['source_index']] and codec.equal(o[k], mapping[o['source_index']][k]) for o in reference['observations']) for k in fields}
            combined = sum(all(k in o and k in mapping[o['source_index']] and codec.equal(mapping[o['source_index']][k], o[k]) for k in fields) for o in reference['observations'])
            lc = reference['work_results']; ac = actual['work_results']
            positive = [(k, v['action']) for k, v in lc.items() if isinstance(v, dict)]
            found = [(k, v['action']) for k, v in ac.items() if isinstance(v, dict)]
            rows.append({'job_prefix': r['job_id'][:8], 'call_index': r['call_index'], 'observations': len(reference['observations']),
                **{k+'_matches': v for k,v in counts.items()}, 'decision_matches': combined,
                'lifecycle_positive': len(positive), 'lifecycle_matches': len(set(positive)&set(found)),
                'additional_flags': len(set(found)-set(positive)), 'source_file': name})
    required = [r for r in rows if r['job_prefix'] in ('8bdacbe2', '2d34a51a', 'b5e4fddb')]
    missing = [p for p in ('8bdacbe2', '2d34a51a', 'b5e4fddb') if not any(r['job_prefix']==p for r in rows)]
    count = sum(r['observations'] for r in required)
    return {'decision_agreement_rate': sum(r['decision_matches'] for r in required)/count if count else None,
        'update_target_rate': sum(r['update_target_matches'] for r in required)/count if count else None,
        'calls': len(required), 'errors': 0, 'evidence_known': int(bool(count)), 'complete': not missing,
        'missing_control_prefixes': missing, 'per_call': required,
        'other_historical_controls': [r for r in rows if r not in required],
        'source_files': ['../../../filtered-replay/results-filtered-run1.jsonl', '../../../filtered-replay/results-filtered-run2.jsonl']}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calls', default=str(COMPACT_SOURCE))
    parser.add_argument('--requests', default=str(PACKAGE/'model-replay/requests.jsonl'))
    parser.add_argument('--overlay', default=str(ROOT.parent/'overlay'))
    args = parser.parse_args(argv)
    try:
        schemas, compact = load_release(args.overlay)
        selected = select(list(common.read_jsonl(args.calls)), list(common.read_jsonl(args.requests)))
        records = [build_record(c, r, schemas, compact) for c,r in selected]
        with (ROOT/'selected_requests.jsonl').open('x', encoding='utf-8') as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n')
        control = controls(PACKAGE)
        (ROOT/'control_metrics.json').write_text(json.dumps(control, indent=2)+'\n')
        reservation = sum(replay.estimate(r)['reserved_micro_usd'] for r in records)
        summary = {'calls': len(records), 'candidate_work': sum(len(r['work']) for r in records),
            'observations': sum(len(r['obs_in']) for r in records), 'required_calls': 4,
            'negative_calls': 3, 'large_calls': 1, 'reserved_micro_usd': reservation,
            'ceiling_micro_usd': replay.CAP, 'budget_fits': int(reservation <= replay.CAP),
            'input_tokens_reference': sum(r['reference_usage']['input_tokens'] for r in records),
            'reserved_output_tokens': sum(r['max_output_tokens'] for r in records),
            'controls_available': control['calls'], 'controls_required': 3,
            'selection': [{'job_prefix': r['job_id'][:8], 'call_index': r['call_index'], 'work':len(r['work']),
                'obs':len(r['obs_in']), **replay.estimate(r)} for r in records]}
        (ROOT/'selection_summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps({k:v for k,v in summary.items() if k!='selection'}, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, StopIteration):
        print('Build stopped: invalid or unavailable local source.', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
