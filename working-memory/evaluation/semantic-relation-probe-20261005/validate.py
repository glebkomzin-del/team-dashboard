"""Deterministic structural and source-coverage checks; semantic verdict still needs human review."""
import json
from pathlib import Path

PRIVATE = Path('/private/tmp/semantic-relation-probe-20261005')
EXPECTED_FIELDS = {'action_id', 'earlier_owner', 'earlier_object', 'earlier_condition',
                   'earlier_evidence', 'later_evidence', 'relation', 'object_link_reason',
                   'final_statement', 'review_required'}
RELATIONS = {'expressly_withdrawn', 'replaced', 'independent', 'confirmed', 'unclear'}

def inspect(result, expected, source_map, compare_expected=True):
    errors = []
    if not isinstance(result, dict) or set(result) != {'cases'} or not isinstance(result['cases'], list):
        return ['missing/invalid cases']
    seen_cases = set()
    expected_cases = expected['cases']
    for case in result['cases']:
        if not isinstance(case, dict) or set(case) != {'case_id', 'relations'}:
            errors.append('invalid case shape'); continue
        cid = case['case_id']
        if cid not in expected_cases or cid in seen_cases:
            errors.append(f'unknown/duplicate case {cid}'); continue
        seen_cases.add(cid)
        if not isinstance(case['relations'], list):
            errors.append(f'{cid}: invalid relations'); continue
        seen_actions = set()
        for relation in case['relations']:
            if not isinstance(relation, dict) or set(relation) != EXPECTED_FIELDS:
                errors.append(f'{cid}: invalid relation shape'); continue
            aid = relation['action_id']
            key = f'{cid}/{aid}'
            if aid not in expected_cases[cid] or aid in seen_actions:
                errors.append(f'{key}: unknown/duplicate action'); continue
            seen_actions.add(aid)
            for field in ('earlier_owner', 'earlier_object', 'object_link_reason', 'final_statement'):
                if not isinstance(relation[field], str) or not relation[field].strip():
                    errors.append(f'{key}: empty {field}')
            if not isinstance(relation['earlier_condition'], str):
                errors.append(f'{key}: invalid earlier_condition')
            for side in ('earlier', 'later'):
                evidences = relation[f'{side}_evidence']
                if not isinstance(evidences, list) or not evidences:
                    errors.append(f'{key}: missing {side} evidence'); continue
                seen_units = set()
                for evidence in evidences:
                    if not isinstance(evidence, dict) or set(evidence) != {'unit_id', 'quote'}:
                        errors.append(f'{key}: invalid {side} evidence'); continue
                    uid, quote = evidence['unit_id'], evidence['quote']
                    if uid in seen_units:
                        errors.append(f'{key}: duplicate {side} unit {uid}')
                    seen_units.add(uid)
                    if uid not in source_map[cid]:
                        errors.append(f'{key}: unknown {side} ID {uid}'); continue
                    if not isinstance(quote, str) or not quote.strip() or quote not in source_map[cid][uid]:
                        errors.append(f'{key}: ungrounded {side} quote')
                if not set(expected['required_evidence'][key][side]).issubset(seen_units):
                    errors.append(f'{key}: missing required {side} unit')
            if relation['relation'] not in RELATIONS:
                errors.append(f'{key}: invalid relation')
            if not isinstance(relation['review_required'], bool):
                errors.append(f'{key}: invalid review_required')
            if compare_expected:
                if relation['relation'] != expected_cases[cid][aid]:
                    errors.append(f'{key}: expected relation mismatch')
                if relation['review_required'] != (key in expected['required_review']):
                    errors.append(f'{key}: expected review flag mismatch')
        if seen_actions != set(expected_cases[cid]):
            errors.append(f'{cid}: action omission')
    if seen_cases != set(expected_cases):
        errors.append('case omission')
    return errors

def main():
    import sys
    if len(sys.argv) != 2:
        raise SystemExit('usage: validate.py response.json')
    result = json.loads(Path(sys.argv[1]).read_text())
    expected = json.loads((PRIVATE / 'expected-private.json').read_text())
    source_map = json.loads((PRIVATE / 'source-map.json').read_text())
    errors = inspect(result, expected, source_map)
    print(json.dumps({'passed': not errors, 'errors': errors}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))

if __name__ == '__main__':
    main()
