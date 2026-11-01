"""Offline A=30,k=5 filtering. Shared JSON/schema helpers copied by lead from model-replay.
Rank decisions use saved codex-rank/metrics.json production validation, not fresh search.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('filtered_common_build', ROOT / 'replay_common.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
DEFAULT_METRICS = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/codex-rank/metrics.json')


def unpack_prompt(prompt):
    marker = 'Kandidaten:\n'
    at = prompt.index(marker) + len(marker)
    packed, end = json.JSONDecoder().raw_decode(prompt[at:])
    return prompt[:at], packed, prompt[at + end:]


def aliases(packed):
    table = packed['tables']['work']
    fields = table['fields']
    texts = packed['texts']
    result = {}
    for row in table['rows']:
        if len(row) != len(fields):
            raise ValueError('Invalid row width')
        alias = row[fields.index('id')]
        idx = row[fields.index('work_index')]
        if 'work_index' in table['text_fields'] and idx is not None:
            idx = texts[idx]
        if not isinstance(alias, str) or alias in result or str(idx) in result.values():
            raise ValueError('Duplicate/invalid alias or work index')
        result[alias] = str(idx)
    return result


def is_final_used(record):
    try:
        answer = common.parse_json(record['reference_text'])
        if common.schema_errors(answer, record['request_json']['schema']):
            return False
        work = answer.get('work_results')
        obs = answer.get('observations')
        if not isinstance(work, dict) or not isinstance(obs, list) or answer.get('open_ids') != []:
            return False
        _, packed, _ = unpack_prompt(record['request_json']['prompt'])
        mapping = aliases(packed)
        if set(work) != set(mapping.values()):
            return False
        return any(v != 'unchanged' for v in work.values()) or any(o.get('update_target') for o in obs)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def validate_schema(schema):
    common.validate_schema_structure(schema)


def filter_record(record, removed):
    out = copy.deepcopy(record)
    original = copy.deepcopy(record['request_json'])
    before = original['prompt']
    prefix, packed, suffix = unpack_prompt(before)
    mapping = aliases(packed)
    removed = set(removed)
    if not removed <= set(mapping):
        raise ValueError('Decision contains unknown aliases')
    kept = set(mapping) - removed
    table = packed['tables']['work']
    ai = table['fields'].index('id')
    table['rows'] = [row for row in table['rows'] if row[ai] in kept]
    # Outer text pool only: archive_navigation is its own packed namespace.
    refs = set()
    for tab in packed['tables'].values():
        columns = [tab['fields'].index(f) for f in tab['text_fields']]
        for row in tab['rows']:
            for col in columns:
                idx = row[col]
                if idx is not None and idx != {'missing': True}:
                    if type(idx) is not int or not 0 <= idx < len(packed['texts']):
                        raise ValueError('Invalid text index')
                    refs.add(idx)
    reindex = {old: new for new, old in enumerate(sorted(refs))}
    oldtexts = packed['texts']
    packed['texts'] = [oldtexts[i] for i in sorted(refs)]
    for tab in packed['tables'].values():
        for row in tab['rows']:
            for field in tab['text_fields']:
                col = tab['fields'].index(field)
                if row[col] is not None and row[col] != {'missing': True}:
                    row[col] = reindex[row[col]]
    schema = out['request_json']['schema']
    def prune(node, work=False):
        if isinstance(node, dict):
            if 'enum' in node:
                node['enum'] = [x for x in node['enum'] if x not in removed]
            if work and 'properties' in node:
                keys = removed | {mapping[a] for a in removed}
                node['properties'] = {k:v for k,v in node['properties'].items() if k not in keys}
                if 'required' in node:
                    node['required'] = [k for k in node['required'] if k not in keys]
            for key, value in node.items():
                if key == 'properties':
                    for name, child in value.items():
                        prune(child, work or name == 'work_results')
                elif isinstance(value, (dict, list)):
                    prune(value, work)
        elif isinstance(node, list):
            for child in node:
                prune(child, work)
    prune(schema)
    validate_schema(schema)
    # Each alias belongs to exactly one update-target enum; index slots remain stable.
    enum_aliases = []
    workkeys = []
    def inspect(node, work=False):
        if isinstance(node, dict):
            enum_aliases.extend(x for x in node.get('enum', []) if isinstance(x, str) and x in mapping)
            if work and 'properties' in node:
                workkeys.extend(node['properties'])
                if set(node.get('required', [])) != set(node['properties']):
                    raise ValueError('Work slots not required exactly once')
            for key,value in node.items():
                if key=='properties':
                    for name, child in value.items(): inspect(child, work or name=='work_results')
                elif isinstance(value,(dict,list)): inspect(value,work)
        elif isinstance(node,list):
            for child in node: inspect(child,work)
    inspect(schema)
    if set(enum_aliases) != kept or len(enum_aliases) != len(kept):
        raise ValueError('Alias schema coverage mismatch')
    if set(workkeys) != {mapping[a] for a in kept} or len(workkeys) != len(kept):
        raise ValueError('Work-index schema coverage mismatch')
    if aliases(packed) != {a:i for a,i in mapping.items() if a in kept}:
        raise ValueError('Retained identities changed')
    after = prefix + json.dumps(packed, ensure_ascii=False, separators=(',', ':')) + suffix
    if removed and len(after) >= len(before):
        raise ValueError('Prompt did not shrink')
    out['request_json']['prompt'] = after
    out['original_request_json'] = original
    out['replay_variant'] = 'filtered'
    out['replay_id'] = f"{record['job_id']}:{record['call_index']}:filtered"
    out['filter_metadata'] = {'kept_aliases': sorted(kept), 'removed_aliases': sorted(removed),
        'alias_work_indices': mapping, 'candidates_before': len(mapping), 'candidates_after': len(kept),
        'prompt_characters_before': len(before), 'prompt_characters_after': len(after)}
    return out


def decision_rows(metrics, records):
    bykey = {}
    for row in metrics['rows']:
        key = (row['job'], row['index'])
        group = bykey.setdefault(key, {})
        alias = row['alias']
        if alias in group:
            raise ValueError('Duplicate decision alias')
        age, rank, exact = row.get('age'), row.get('best'), row.get('exact')
        if type(age) not in (int, float) or type(rank) is not int or type(exact) is not bool:
            raise ValueError('Unknown filter evidence')
        group[alias] = age <= 30 or rank < 5 or exact
    output = []
    seen_keys = set()
    for record in records:
        if not is_final_used(record):
            continue
        key = (record['job_id'][:8], record['call_index'])
        if key in seen_keys:
            raise ValueError('Ambiguous eligible call prefix/index')
        seen_keys.add(key)
        group = bykey.get(key)
        _, packed, _ = unpack_prompt(record['request_json']['prompt'])
        mapping = aliases(packed)
        if group is None or set(group) != set(mapping):
            raise ValueError('Missing or incomplete decisions for eligible call')
        output.append({'job_id':record['job_id'], 'call_index':record['call_index'],
                       'removed_aliases':sorted(a for a,k in group.items() if not k)})
    return output


def write_jsonl(path, rows):
    path = common.output_path(path)
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests',type=Path,default=ROOT.parent/'model-replay/requests.jsonl')
    parser.add_argument('--metrics',type=Path,default=DEFAULT_METRICS)
    parser.add_argument('--decisions',type=Path)
    args=parser.parse_args()
    records=list(common.read_jsonl(args.requests))
    if args.decisions:
        decisions=list(common.read_jsonl(args.decisions))
    else:
        decisions=decision_rows(common.parse_json(args.metrics.read_text()),records)
        provenance={'requests_sha256':hashlib.sha256(args.requests.read_bytes()).hexdigest(),
                    'metrics_sha256':hashlib.sha256(args.metrics.read_bytes()).hexdigest(),
                    'metrics_source':str(args.metrics), 'A_days':30, 'k_exclusive':5}
        for d in decisions:d['provenance']=provenance
    bykey={(d['job_id'],d['call_index']):d for d in decisions}
    if len(bykey)!=len(decisions):raise ValueError('Duplicate decision call')
    filtered=[]
    for r in records:
        if not is_final_used(r):continue
        d=bykey.get((r['job_id'],r['call_index']))
        if d is None:raise ValueError('Missing eligible-call decision')
        filtered.append(filter_record(r,d['removed_aliases']))
    write_jsonl(ROOT/'filter-decisions.jsonl',decisions)
    write_jsonl(ROOT/'filtered_requests.jsonl',filtered)
    print(json.dumps({'eligible_final_used_calls':len(filtered),'input_calls':len(records),
                      'candidates_before':sum(r['filter_metadata']['candidates_before'] for r in filtered),
                      'candidates_after':sum(r['filter_metadata']['candidates_after'] for r in filtered)}))

if __name__=='__main__':main()
