"""Offline, numeric-only comparison of saved delta-v2 calls. No provider calls."""
import argparse
from copy import deepcopy
import functools
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
FIELDS = ('update_target', 'update', 'matter_id')


@functools.lru_cache(maxsize=None)
def load(name):
    spec = importlib.util.spec_from_file_location('v2_compare_' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def count(value):
    return value if type(value) is int and value >= 0 else None


def sum_known(values):
    values = list(values)
    return sum(values) if values and all(v is not None for v in values) else None


def rate(hits, total):
    return hits / total if hits is not None and total else None


def identity(row):
    job, index, rid = row.get('job_id'), row.get('call_index'), row.get('replay_id')
    if (not isinstance(job, str) or not job or type(index) is not int or index < 0
            or rid != f'{job}:{index}:delta-v2'):
        raise ValueError('identity')
    return rid


def full_schema(schema):
    """Retain recorded schema; equivalent zero-observation archive normalization."""
    value = deepcopy(schema)
    try:
        observations = value['properties']['observations']
        index = observations['items']['properties']['source_index']
        if index.get('enum') == []:
            del index['enum']
            observations['maxItems'] = 0
    except (KeyError, TypeError):
        pass
    return value


def observations(full):
    result = {}
    if not isinstance(full.get('observations'), list):
        raise ValueError('observations')
    for entry in full['observations']:
        index = entry.get('source_index') if isinstance(entry, dict) else None
        if type(index) is not int or index < 0 or index in result or any(k not in entry for k in FIELDS):
            raise ValueError('observation_identity')
        result[index] = entry
    return result


def lifecycle(full, work):
    values = full.get('work_results')
    if not isinstance(values, dict) or set(values) != {str(i) for i in range(len(work))}:
        raise ValueError('work_coverage')
    result = {}
    for i, entry in enumerate(work):
        if not isinstance(entry, dict):
            raise ValueError('work')
        # Recorded aliases identify work; slot identity remains valid if no alias exists.
        alias = entry.get('alias', entry.get('id', str(i)))
        if not isinstance(alias, str) or alias in result:
            raise ValueError('work_alias')
        value = values[str(i)]
        if type(value) is str and value == 'unchanged':
            action = value
        elif isinstance(value, dict) and isinstance(value.get('action'), str) and value['action'] != 'unchanged':
            action = value['action']
        else:
            raise ValueError('action')
        result[alias] = action
    return result


def compare_attempt(attempt, record, reservation=None):
    common = load('replay_common')
    reference_usage = record.get('reference_usage')
    row = dict(job_prefix=record['job_id'][:8], call_index=record['call_index'], errors=0, delta_schema_ok=0,
               decoded_schema_ok=0, reference_schema_ok=0, decoder_errors=0,
               final=0, followup=0, observation_coverage_ok=0,
               observation_total=None, covered_observations=None,
               missing_observations=None, extra_observations=None,
               decision_matches=None, lifecycle_matches=None, lifecycle_total=None,
               lifecycle_positive_matches=None, lifecycle_positive_total=None,
               additional_flags=None, output_tokens=None, reasoning_tokens=None,
               reference_output_tokens=count(reference_usage.get('output_tokens')) if isinstance(reference_usage, dict) else None,
               actual_micro_usd=None,
               reference_micro_usd=common.usage_micro_usd(record.get('reference_usage'), 'gpt-6.1-sol'),
               next_round_reserved_micro_usd=None, next_round_extra_input_tokens=None)
    row.update({field + '_matches': None for field in FIELDS})
    ref_obs = ref_work = schema = None
    try:
        schema = full_schema(record['reference_schema'])
        common.validate_schema_structure(schema)
        reference = record['reference_full']
        if common.schema_errors(reference, schema) or reference.get('open_ids') != []:
            raise ValueError('reference')
        ref_obs = observations(reference)
        ref_work = lifecycle(reference, record['work'])
        expected = {o.get('source_index', i) for i, o in enumerate(record['obs_in'])}
        if set(ref_obs) != expected:
            raise ValueError('reference_coverage')
        row.update(reference_schema_ok=1, observation_total=len(ref_obs),
                   lifecycle_total=len(ref_work),
                   lifecycle_positive_total=sum(a != 'unchanged' for a in ref_work.values()))
    except (ValueError, TypeError, KeyError, AttributeError):
        row['errors'] += 1
    if attempt is None:
        row['errors'] += 1
        return row
    usage = attempt.get('usage')
    if isinstance(usage, dict):
        row['output_tokens'] = count(usage.get('output_tokens'))
        details = usage.get('output_tokens_details')
        if isinstance(details, dict):
            row['reasoning_tokens'] = count(details.get('reasoning_tokens'))
            if ('reasoning_tokens' in details and (row['reasoning_tokens'] is None
                    or row['output_tokens'] is not None and row['reasoning_tokens'] > row['output_tokens'])):
                row['output_tokens'] = None
    try:
        raw, stream_error = common.response_body(attempt.get('raw_response', ''))
        body = attempt.get('response')
        if (stream_error or not equal(raw, body) or not isinstance(body, dict)
                or body.get('status') != 'completed' or body.get('model') != 'gpt-6.1-sol'
                or body.get('service_tier') != 'default' or not equal(body.get('usage'), usage)
                or not equal(common.answer_text(body), attempt.get('text'))):
            raise ValueError('provider_evidence')
        row['actual_micro_usd'] = common.usage_micro_usd(usage, 'gpt-6.1-sol')
        saved_cost = attempt.get('actual_micro_usd')
        if saved_cost is not None and not equal(saved_cost, row['actual_micro_usd']):
            raise ValueError('cost_conflict')
        if attempt.get('status') != 'ok':
            raise ValueError('status')
        delta = common.parse_json(attempt['text'])
        request_schema = record['request_json']['schema']
        common.validate_schema_structure(request_schema)
        if common.schema_errors(delta, request_schema):
            raise ValueError('delta_schema')
        row['delta_schema_ok'] = 1
        try:
            decoded = load('delta_codec').from_delta(delta, record['obs_in'], record['work'])
        except (ValueError, TypeError, KeyError, IndexError):
            row['decoder_errors'] = 1
            raise ValueError('decoder') from None
        if common.schema_errors(decoded, schema):
            raise ValueError('decoded_schema')
        row['decoded_schema_ok'] = 1
        if decoded.get('open_ids'):
            row['followup'] = 1
            estimate = record.get('next_round_reserved_micro_usd')
            if estimate is None and reservation is not None:
                estimate = reservation.get('reserved_micro_usd')
            row['next_round_reserved_micro_usd'] = estimate if count(estimate) is not None and estimate > 0 else None
            # Opened-item input is unavailable: this estimate is not a bound.
            return row
        if decoded.get('open_ids') != []:
            raise ValueError('endform')
        row['final'] = 1
        actual_obs = observations(decoded)
        actual_work = lifecycle(decoded, record['work'])
        if ref_obs is None or ref_work is None:
            return row
        covered = set(actual_obs) & set(ref_obs)
        row.update(covered_observations=len(covered),
                   missing_observations=len(set(ref_obs) - set(actual_obs)),
                   extra_observations=len(set(actual_obs) - set(ref_obs)),
                   observation_coverage_ok=int(set(actual_obs) == set(ref_obs)),
                   decision_matches=sum(all(equal(actual_obs[i][k], ref_obs[i][k]) for k in FIELDS) for i in covered),
                   lifecycle_matches=sum(actual_work.get(a) == action for a, action in ref_work.items()),
                   lifecycle_positive_matches=sum(action != 'unchanged' and actual_work.get(a) == action for a, action in ref_work.items()),
                   additional_flags=sum(action != 'unchanged' and ref_work.get(a) != action for a, action in actual_work.items()))
        for field in FIELDS:
            row[field + '_matches'] = sum(equal(actual_obs[i][field], ref_obs[i][field]) for i in covered)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        row['errors'] += 1
    return row


def control_rate(control):
    if not isinstance(control, dict):
        return None
    value = control.get('decision_agreement_rate')
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return value


def compare_records(requests, events, control=None):
    records, attempts, reservations = {}, {}, {}
    errors = duplicate_attempts = 0
    for request in requests:
        try:
            rid = identity(request)
            if rid in records:
                raise ValueError('duplicate_request')
            records[rid] = request
        except (ValueError, AttributeError):
            errors += 1
    for event in events:
        try:
            rid = identity(event)
            if rid not in records:
                raise ValueError('unknown_identity')
            phase = event.get('record_type')
            if phase == 'reservation':
                if (rid in reservations or rid in attempts or count(event.get('reserved_micro_usd')) is None
                        or event['reserved_micro_usd'] == 0):
                    raise ValueError('reservation')
                reservations[rid] = event
            elif phase == 'attempt':
                if rid in attempts:
                    duplicate_attempts += 1
                    # Repeated paid calls are invalid, even if content is identical.
                    raise ValueError('duplicate_attempt')
                attempts[rid] = event
                if rid not in reservations:
                    raise ValueError('unreserved_attempt')
                if not equal(event.get('reserved_micro_usd'), reservations[rid].get('reserved_micro_usd')):
                    raise ValueError('reservation_conflict')
            else:
                raise ValueError('event_type')
        except (ValueError, AttributeError):
            errors += 1
    rows = [compare_attempt(attempts.get(rid), record, reservations.get(rid)) for rid, record in records.items()]
    for call_number, row in enumerate(rows, 1):
        row['call_number'] = call_number
        for field in FIELDS:
            row[field + '_rate'] = rate(row[field + '_matches'], row['observation_total'])
        row.update(decision_agreement_rate=rate(row['decision_matches'], row['observation_total']),
                   lifecycle_agreement_rate=rate(row['lifecycle_matches'], row['lifecycle_total']),
                   lifecycle_positive_recall=rate(row['lifecycle_positive_matches'], row['lifecycle_positive_total']),
                   output_ratio=rate(row['output_tokens'], row['reference_output_tokens']),
                   observation_coverage_rate=rate(row['covered_observations'], row['observation_total'])
                   if row['observation_total'] else (1 if row['final'] and row['observation_coverage_ok'] else None),
                   cost_ratio=rate(row['actual_micro_usd'], row['reference_micro_usd']),
                   cost_delta_micro_usd=(row['actual_micro_usd']-row['reference_micro_usd'])
                   if row['actual_micro_usd'] is not None and row['reference_micro_usd'] is not None else None)
    metrics = ('observation_total', 'covered_observations', 'decision_matches',
               'lifecycle_matches', 'lifecycle_total', 'lifecycle_positive_matches',
               'lifecycle_positive_total', 'additional_flags', 'output_tokens',
               'reference_output_tokens', 'reasoning_tokens', 'actual_micro_usd', 'reference_micro_usd')
    totals = {k: sum_known(r[k] for r in rows) for k in metrics}
    totals.update({k + '_matches': sum_known(r[k + '_matches'] for r in rows) for k in FIELDS})
    for field in FIELDS:
        totals[field + '_rate'] = rate(totals[field + '_matches'], totals['observation_total'])
    totals.update(decision_agreement_rate=rate(totals['decision_matches'], totals['observation_total']),
                  lifecycle_agreement_rate=rate(totals['lifecycle_matches'], totals['lifecycle_total']),
                  lifecycle_positive_recall=rate(totals['lifecycle_positive_matches'], totals['lifecycle_positive_total']),
                  output_ratio=rate(totals['output_tokens'], totals['reference_output_tokens']),
                  cost_ratio=rate(totals['actual_micro_usd'], totals['reference_micro_usd']),
                  cost_delta_micro_usd=(totals['actual_micro_usd'] - totals['reference_micro_usd'])
                  if totals['actual_micro_usd'] is not None and totals['reference_micro_usd'] is not None else None,
                  selected=len(records), attempts=len(attempts), global_errors=errors,
                  duplicate_attempts=duplicate_attempts,
                  missing_attempts=len(set(records) - set(attempts)),
                  pending_reservations=len(set(reservations) - set(attempts)),
                  finals=sum(r['final'] for r in rows), followups=sum(r['followup'] for r in rows),
                  decoder_errors=sum(r['decoder_errors'] for r in rows),
                  errors=sum(r['errors'] for r in rows))
    baseline = control_rate(control)
    complete = isinstance(control, dict) and (control.get('complete') is True or type(control.get('controls_complete')) is int and control['controls_complete'] == 1)
    control_known = bool(complete and control.get('evidence_known') == 1 and type(control.get('evidence_known')) is int
                         and type(control.get('calls')) is int and control['calls'] > 0
                         and type(control.get('errors')) is int and control['errors'] == 0
                         and not control.get('missing_control_prefixes') and baseline is not None)
    agreement = totals['decision_agreement_rate']
    decisions_pass = int(agreement + 1e-12 >= baseline - .02) if control_known and agreement is not None else None
    coverage_pass = int(bool(rows) and all(r['final'] and r['observation_coverage_ok'] for r in rows))
    ratio = totals['output_ratio']
    output_known = bool(rows) and all(row['output_ratio'] is not None for row in rows)
    output_pass = int(all(row['output_ratio'] <= .4 + 1e-12 for row in rows)) if output_known else None
    schema_pass = int(bool(rows) and all(r['reference_schema_ok'] and r['delta_schema_ok'] and r['decoded_schema_ok'] for r in rows))
    known = int(bool(rows) and not errors and not totals['errors'] and not totals['missing_attempts']
                and not totals['pending_reservations'] and schema_pass and control_known
                and totals['actual_micro_usd'] is not None and totals['reference_micro_usd'] is not None
                and ratio is not None and agreement is not None)
    followups = [r for r in rows if r['followup']]
    return dict(calls=rows, total=totals, control_rate=baseline, control_evidence_known=int(control_known),
                evidence_known=known, schema_pass=schema_pass, observation_coverage_pass=coverage_pass,
                decision_agreement_pass=decisions_pass, output_pass=output_pass,
                next_round=dict(calls=len(followups), reserved_micro_usd=sum_known(r['next_round_reserved_micro_usd'] for r in followups) if followups else 0,
                                added_opened_input_tokens=None if followups else 0, complete_estimate=int(not followups), executed=0),
                passed=int(bool(known and schema_pass and coverage_pass and decisions_pass and output_pass and not totals['decoder_errors'])))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', type=Path, default=ROOT / 'selected_requests.jsonl')
    parser.add_argument('--results', type=Path, nargs='+', default=[ROOT / 'replay_ledger.jsonl'])
    parser.add_argument('--controls', type=Path, default=ROOT / 'control_metrics.json')
    args = parser.parse_args(argv)
    try:
        common = load('replay_common')
        controls = common.parse_json(args.controls.read_text()) if args.controls.exists() else None
        report = compare_records(common.read_jsonl(args.requests),
                                 (r for path in args.results for r in common.read_jsonl(path)), controls)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        print(json.dumps({'input_error': 1, 'passed': 0}))
        return 2
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
