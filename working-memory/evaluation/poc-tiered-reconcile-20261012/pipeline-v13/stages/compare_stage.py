#!/usr/bin/env python3
"""Offline heuristic comparison; output contains counts, ratios and categories only.

Use selected_requests.jsonl for a bounded replay, or --select selection.json (a
JSON list of {job_id, call_index, stage}). Missing expected executions always
block the decision. Text matching is lexical, never a semantic quality proof.
"""
import argparse
import difflib
import importlib.util
import json
import math
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location('stage_common', Path(__file__).with_name('stage_common.py'))
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
parse_json = _common.parse_json
read_jsonl = _common.read_jsonl
schema_errors = _common.schema_errors

LUNA = 'gpt-6-luna'
SOL = 'gpt-6.1-sol'
STAGES = {'extract', 'gate'}


def identity(record):
    job = record.get('job_id')
    call = record.get('call_index')
    stage = record.get('stage')
    if not isinstance(job, str) or not job or type(call) is not int or call < 0 or stage not in STAGES:
        raise ValueError('invalid_identity')
    return job, call, stage


def indexed(records):
    result = {}
    for record in records:
        key = identity(record)
        if key in result:
            raise ValueError('duplicate_identity')
        result[key] = record
    return result


def request_contract(record):
    request = record.get('request_json')
    if isinstance(request, str):
        request = parse_json(request)
    if not isinstance(request, dict) or not isinstance(request.get('schema'), dict):
        raise ValueError('invalid_request_schema')
    if request.get('model') != SOL:
        raise ValueError('invalid_reference_model')
    if record.get('reference_model') != SOL:
        raise ValueError('invalid_reference_model')
    if record.get('reference_stop_reason') != 'end_turn':
        raise ValueError('incomplete_reference')
    schema = request['schema']
    required = {'observations', 'meeting_summary'} if record['stage'] == 'extract' else {'verdicts'}
    if not required.issubset(set(schema.get('required', []))) or not required.issubset(schema.get('properties', {})):
        raise ValueError('invalid_stage_schema')
    return request, schema


def validated(text, schema, stage):
    if not isinstance(text, str):
        return None, 'missing_text'
    try:
        value = parse_json(text)
    except (ValueError, TypeError, RecursionError):
        return None, 'invalid_json'
    if schema_errors(value, schema):
        return None, 'invalid_schema'
    if not isinstance(value, dict):
        return None, 'invalid_shape'
    if stage == 'extract':
        observations = value.get('observations')
        summary = value.get('meeting_summary')
        if (not isinstance(observations, list) or not isinstance(summary, list) or
                any(not isinstance(o, dict) or not isinstance(o.get('kind'), str) or
                    not isinstance(o.get('commitment_strength'), str) or
                    not all(isinstance(o.get(k), str) for k in ('title', 'claim'))
                    for o in observations) or
                any(not isinstance(p, dict) or not isinstance(p.get('text'), str) for p in summary)):
            return None, 'invalid_shape'
    else:
        verdicts = value.get('verdicts')
        if (not isinstance(verdicts, list) or
                any(not isinstance(v, dict) or type(v.get('index')) is not int or
                    not isinstance(v.get('verdict'), str) for v in verdicts)):
            return None, 'invalid_shape'
    return value, None


def normalized(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


def similarity(left, right):
    a, b = normalized(left), normalized(right)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def claim_text(observation):
    return ' '.join(observation.get(k, '') for k in ('title', 'claim'))


def source_ids(observation):
    return {item for key in ('evidence_ids', 'state_evidence_ids')
            for item in observation.get(key, []) if isinstance(item, str)}


def spans(observation):
    result = []
    for span in observation.get('source_spans', []):
        if isinstance(span, dict) and type(span.get('start')) is int and type(span.get('end')) is int and span['start'] < span['end']:
            result.append((span['start'], span['end']))
    return result


def quote_text(observation):
    quotes = list(observation.get('quotes', []))
    quotes += [s.get('quote', '') for s in observation.get('source_spans', []) if isinstance(s, dict)]
    return ' '.join(q for q in quotes if isinstance(q, str))


def match_score(left, right, threshold):
    li, ri, ls, rs = source_ids(left), source_ids(right), spans(left), spans(right)
    overlap = bool(li & ri) or any(max(a, c) < min(b, d) for a, b in ls for c, d in rs)
    text_score = similarity(claim_text(left), claim_text(right))
    quote_score = similarity(quote_text(left), quote_text(right))
    # Shared source/quote alone is insufficient: a source unit can hold several claims.
    # Text threshold protects against pairing unrelated claims from that same unit.
    if li or ri or ls or rs:
        if not overlap or text_score < threshold:
            return None
        return 1.0 + text_score + quote_score / 10
    if text_score < threshold:
        return None
    return text_score + quote_score / 10


def match_observations(sol, luna, threshold=0.55):
    """Deterministic maximum-cardinality bipartite matching, score-ordered edges.

    Maximizes presence coverage, with lexical similarity guiding tie traversal;
    does not claim global maximum similarity or semantic equivalence.
    """
    edges = {}
    for i, left in enumerate(sol):
        candidates = []
        for j, right in enumerate(luna):
            score = match_score(left, right, threshold)
            if score is not None:
                candidates.append((j, score))
        edges[i] = [j for j, _ in sorted(candidates, key=lambda p: (-p[1], p[0]))]
    paired = {}
    def assign(i, visited):
        for j in edges[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in paired or assign(paired[j], visited):
                paired[j] = i
                return True
        return False
    for i in sorted(edges, key=lambda k: (len(edges[k]), k)):
        assign(i, set())
    return sorted((i, j) for j, i in paired.items())


def expected_indices(prompt, reference):
    """Bind to JSON Kandidaten section if present; otherwise valid Sol indices."""
    if not isinstance(prompt, str):
        return None, 'invalid_prompt'
    marker = re.search(r'(?:^|\n)Kandidaten(?:\s*\([^\n]*\))?\s*:\s*', prompt)
    if marker:
        tail = prompt[marker.end():].lstrip()
        # Locate a complete JSON value without accepting trailing prompt sections.
        decoder = json.JSONDecoder()
        try:
            _, end = decoder.raw_decode(tail)
            candidates = parse_json(tail[:end])
        except (ValueError, TypeError, RecursionError):
            return None, 'invalid_candidates'
        if (not isinstance(candidates, list) or
                any(not isinstance(c, dict) or type(c.get('index')) is not int or c['index'] < 0 for c in candidates)):
            return None, 'invalid_candidates'
        indices = [c['index'] for c in candidates]
        if len(set(indices)) != len(indices):
            return None, 'duplicate_candidates'
        return set(indices), None
    if reference is None:
        return None, 'unknown_denominator'
    indices = [v['index'] for v in reference['verdicts']]
    if any(i < 0 for i in indices) or len(set(indices)) != len(indices):
        return None, 'invalid_reference_indices'
    return set(indices), None


def gate_map(value, expected):
    if value is None:
        return {}, False
    verdicts = value['verdicts']
    indices = [v['index'] for v in verdicts]
    # Duplicates do not yield an arbitrary first/last winner.
    repeated = {i for i in indices if indices.count(i) > 1}
    mapping = {v['index']: v['verdict'] for v in verdicts if v['index'] not in repeated}
    valid = not repeated and set(indices) == expected
    return mapping, valid


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def compare(requests, results, *, selection=None, match_threshold=0.55,
            extract_recall=0.95, gate_agreement=0.95, max_gate_losses=1):
    """Return redacted aggregate/per-row metrics; no prompt, text, IDs or errors."""
    if (any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not 0 <= v <= 1
            for v in (match_threshold, extract_recall, gate_agreement)) or
            type(max_gate_losses) is not int or max_gate_losses < 0):
        raise ValueError('invalid_threshold')
    reqs, replay = indexed(requests), indexed(results)
    if selection is not None:
        chosen = set(indexed(selection))
        if not chosen or not chosen.issubset(reqs):
            raise ValueError('invalid_selection')
        reqs = {k: v for k, v in reqs.items() if k in chosen}
    if not reqs:
        raise ValueError('empty_requests')
    if not set(replay).issubset(reqs):
        raise ValueError('unexpected_execution')
    for result in replay.values():
        if result.get('model') != LUNA:
            raise ValueError('invalid_result_model')
    counts = {'extract_requests': 0, 'gate_requests': 0, 'executions': len(replay),
              'missing_executions': len(reqs) - len(replay), 'reference_valid': 0,
              'luna_valid': 0, 'extract_luna_valid': 0, 'sol_observations': 0,
              'luna_observations': 0, 'matched_observations': 0,
              'sol_commitments': 0, 'recalled_commitments': 0,
              'commitment_presence': 0, 'additional_luna_observations': 0,
              'kind_agreement': 0, 'strength_agreement': 0,
              'sol_summary_present': 0, 'luna_summary_present': 0,
              'sol_summary_characters': 0, 'luna_summary_characters': 0,
              'gate_candidates': 0, 'gate_exact_agreement': 0,
              'sol_supported_luna_different': 0, 'luna_supported_sol_different': 0}
    rows = []
    blockers = set()
    for number, (key, request) in enumerate(sorted(reqs.items()), 1):
        stage = key[2]
        counts[stage + '_requests'] += 1
        row = {'ordinal': number, 'stage': stage, 'reference_valid': False, 'luna_valid': False}
        try:
            contract, schema = request_contract(request)
        except (ValueError, TypeError, RecursionError):
            blockers.add('invalid_request_contract')
            rows.append(row)
            continue
        sol, sol_error = validated(request.get('reference_text'), schema, stage)
        result = replay.get(key)
        if result is None:
            luna, luna_error = None, 'missing_execution'
        elif result.get('status') != 'ok':
            luna, luna_error = None, 'unsuccessful_execution'
        else:
            luna, luna_error = validated(result.get('text'), schema, stage)
        if sol_error:
            blockers.add('reference_' + sol_error)
        if luna_error:
            blockers.add('luna_' + luna_error)
        row.update(reference_valid=sol is not None, luna_valid=luna is not None)
        counts['reference_valid'] += sol is not None
        counts['luna_valid'] += luna is not None
        if stage == 'extract':
            counts['extract_luna_valid'] += luna is not None
            so = sol['observations'] if sol else []
            lu = luna['observations'] if luna else []
            pairs = match_observations(so, lu, match_threshold) if sol and luna else []
            commitments = {i for i, o in enumerate(so) if o['kind'] == 'commitment'}
            recalled = sum(i in commitments and lu[j]['kind'] == 'commitment' for i, j in pairs)
            present = sum(i in commitments for i, _ in pairs)
            extraction = {'sol_observations': len(so), 'luna_observations': len(lu),
                'matched_observations': len(pairs), 'sol_commitments': len(commitments),
                'recalled_commitments': recalled, 'commitment_presence': present,
                'additional_luna_observations': len(lu) - len(pairs),
                'kind_agreement': sum(so[i]['kind'] == lu[j]['kind'] for i, j in pairs),
                'strength_agreement': sum(so[i]['commitment_strength'] == lu[j]['commitment_strength'] for i, j in pairs)}
            for prefix, value in (('sol', sol), ('luna', luna)):
                text = '\n'.join(p['text'] for p in value['meeting_summary']) if value else ''
                extraction[prefix + '_summary_present'] = int(bool(text.strip()))
                extraction[prefix + '_summary_characters'] = len(text)
            for k, value in extraction.items():
                counts[k] += value
            row.update(extraction)
            if sol and not extraction['sol_summary_present']:
                blockers.add('reference_summary_missing')
            if luna and not extraction['luna_summary_present']:
                blockers.add('luna_summary_missing')
        else:
            expected, error = expected_indices(contract.get('prompt'), sol)
            if error:
                blockers.add(error)
                rows.append(row)
                continue
            sm, sv = gate_map(sol, expected)
            lm, lv = gate_map(luna, expected)
            if not sv:
                blockers.add('invalid_reference_gate_coverage')
            if not lv:
                blockers.add('invalid_luna_gate_coverage')
            gate = {'gate_candidates': len(expected),
                'gate_exact_agreement': sum(i in sm and i in lm and sm[i] == lm[i] for i in expected),
                'sol_supported_luna_different': sum(sm.get(i) == 'supported' and lm.get(i) != 'supported' for i in expected),
                'luna_supported_sol_different': sum(lm.get(i) == 'supported' and sm.get(i) != 'supported' for i in expected)}
            for k, value in gate.items():
                counts[k] += value
            candidate_verdicts = [{'index': i, 'sol_verdict': sm.get(i),
                'luna_verdict': lm.get(i),
                'same_verdict': i in sm and i in lm and sm[i] == lm[i],
                'sol_supported_luna_different': sm.get(i) == 'supported' and lm.get(i) != 'supported',
                'luna_supported_sol_different': lm.get(i) == 'supported' and sm.get(i) != 'supported'}
                for i in sorted(expected)]
            row.update(gate, reference_coverage_valid=sv, luna_coverage_valid=lv,
                       candidate_verdicts=candidate_verdicts)
        rows.append(row)
    metrics = {'extract_schema_valid_rate': ratio(counts['extract_luna_valid'], counts['extract_requests']),
        'commitment_recall': ratio(counts['recalled_commitments'], counts['sol_commitments']),
        'commitment_presence_rate': ratio(counts['commitment_presence'], counts['sol_commitments']),
        'kind_agreement_rate': ratio(counts['kind_agreement'], counts['matched_observations']),
        'strength_agreement_rate': ratio(counts['strength_agreement'], counts['matched_observations']),
        'summary_length_ratio': ratio(counts['luna_summary_characters'], counts['sol_summary_characters']),
        'gate_agreement': ratio(counts['gate_exact_agreement'], counts['gate_candidates'])}
    if not counts['extract_requests'] or metrics['commitment_recall'] is None:
        blockers.add('unknown_extract_denominator')
    if not counts['gate_requests'] or metrics['gate_agreement'] is None:
        blockers.add('unknown_gate_denominator')
    if metrics['commitment_recall'] is not None and metrics['commitment_recall'] < extract_recall:
        blockers.add('extract_recall_below_threshold')
    if metrics['gate_agreement'] is not None and metrics['gate_agreement'] < gate_agreement:
        blockers.add('gate_agreement_below_threshold')
    if counts['sol_supported_luna_different'] > max_gate_losses:
        blockers.add('gate_losses_above_limit')
    return {'version': 1, 'passed': not blockers, 'counts': counts, 'metrics': metrics,
        'blockers': sorted(blockers), 'rows': rows,
        'criteria': {'extract_recall': extract_recall, 'gate_agreement': gate_agreement,
                     'max_gate_losses': max_gate_losses},
        'matching': {'method': 'deterministic_maximum_cardinality_lexical',
            'threshold': match_threshold, 'source_requires_claim_similarity': True,
            'semantic_equivalence_proven': False},
        'compact_model': SOL}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', default=str(Path(__file__).with_name('stage_requests.jsonl')))
    parser.add_argument('--results', required=True)
    parser.add_argument('--output', default=str(Path(__file__).with_name('comparison.json')))
    parser.add_argument('--select', help='JSON list of exact {job_id,call_index,stage} identities')
    parser.add_argument('--match-threshold', type=float, default=0.55)
    parser.add_argument('--extract-recall', type=float, default=0.95)
    parser.add_argument('--gate-agreement', type=float, default=0.95)
    parser.add_argument('--max-gate-losses', type=int, default=1)
    args = parser.parse_args(argv)
    try:
        output = _common.output_path(args.output)
        selection = parse_json(Path(args.select).read_text()) if args.select else None
        if selection is not None and not isinstance(selection, list):
            raise ValueError('invalid_selection')
        report = compare(list(read_jsonl(args.requests)), list(read_jsonl(args.results)),
            selection=selection, match_threshold=args.match_threshold,
            extract_recall=args.extract_recall, gate_agreement=args.gate_agreement,
            max_gate_losses=args.max_gate_losses)
        output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'counts': report['counts'],
                          'metrics': report['metrics'], 'blockers': report['blockers']}))
        return 0 if report['passed'] else 1
    except (ValueError, TypeError, OSError, RecursionError):
        # Do not propagate exception strings: malformed input can contain prose.
        print(json.dumps({'passed': False, 'error': 'invalid_input_or_output'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
