"""Offline numeric-only comparison. Helpers adapted from ../model-replay/compare.py.

No model prose, job IDs or aliases are emitted. Unknown evidence blocks acceptance.
Lifecycle identity uses the original alias/index mapping and the exact action.
"""
import argparse
import functools
import importlib.util
import json
from pathlib import Path
import sys


@functools.lru_cache(maxsize=1)
def _common():
    spec = importlib.util.spec_from_file_location('filtered_compare_common', Path(__file__).with_name('replay_common.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _decode(text):
    if not isinstance(text, str):
        raise ValueError('missing_text')
    value = _common().parse_json(text)
    if not isinstance(value, dict):
        raise ValueError('output_not_object')
    return value


def _observations(value):
    entries = value.get('observations')
    if not isinstance(entries, list):
        raise ValueError('invalid_observations')
    result = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('invalid_observation')
        index = entry.get('source_index')
        if type(index) is not int or index < 0 or index in result:
            raise ValueError('invalid_source_index')
        if any(field not in entry for field in ('update_target', 'update', 'kind')):
            raise ValueError('missing_decision')
        result[index] = entry
    return result


def _literal_equal(left, right):
    return type(left) is type(right) and left == right


def _known_cost(value):
    return type(value) is int and value >= 0


def _sum_known(values):
    return sum(values) if all(v is not None for v in values) else None


def _work(value, mapping, aliases):
    entries = value.get('work_results')
    if not isinstance(entries, dict):
        raise ValueError('invalid_work')
    expected = {str(mapping[a]): a for a in aliases}
    if len(expected) != len(aliases) or set(entries) != set(expected):
        raise ValueError('work_coverage')
    result = {}
    for index, entry in entries.items():
        if entry == 'unchanged':
            action = 'unchanged'
        elif isinstance(entry, dict) and isinstance(entry.get('action'), str) and entry['action'] != 'unchanged':
            action = entry['action']
        else:
            raise ValueError('invalid_action')
        result[expected[index]] = action
    return result


def _key(record):
    if not isinstance(record, dict) or not isinstance(record.get('replay_id'), str) or not record['replay_id']:
        raise ValueError('invalid_id')
    return record['replay_id']


def compare_records(requests, results, *, schema_validator=None):
    schema_validator = schema_validator or _common().schema_errors
    requests, results = list(requests), list(results)
    reqs, attempts, global_errors = {}, {}, 0
    for request in requests:
        try:
            key = _key(request)
            if key in reqs:
                global_errors += 1
            else:
                reqs[key] = request
        except ValueError:
            global_errors += 1
    for result in results:
        try:
            key = _key(result)
            attempts.setdefault(key, []).append(result)
        except ValueError:
            global_errors += 1
    global_errors += len(set(attempts) - set(reqs))
    if not reqs:
        global_errors += 1
    rows = []
    for ordinal, (key, request) in enumerate(reqs.items(), 1):
        saved = attempts.get(key, [])
        row = dict(call_number=ordinal, control=int(request.get('replay_variant') == 'control'),
                   attempts=len(saved), errors=0, reference_schema_ok=0, schema_ok=0,
                   reference_endform_ok=0, endform_ok=0,
                   recall_hits=None, recall_total=None, lifecycle_filter_loss=None,
                   observation_filter_loss=None, filter_loss=None, additional_flags=None,
                   update_target_matches=None, update_matches=None, kind_matches=None,
                   observation_total=None, missing_observations=None, extra_observations=None,
                   actual_micro_usd=_sum_known([r.get('actual_micro_usd') if _known_cost(r.get('actual_micro_usd')) else None for r in saved]) if saved else None,
                   cost_unknown_attempts=sum(not _known_cost(r.get('actual_micro_usd')) for r in saved),
                   error_attempts=sum(r.get('status') != 'ok' for r in saved),
                   reference_micro_usd=request.get('reference_micro_usd') if _known_cost(request.get('reference_micro_usd')) else None)
        ref = candidate = None
        try:
            if request.get('replay_variant') not in ('control', 'filtered'):
                raise ValueError('invalid_variant')
            metadata = request['filter_metadata']
            mapping = metadata['alias_work_indices']
            kept, removed = metadata['kept_aliases'], metadata['removed_aliases']
            if (not isinstance(mapping, dict) or not isinstance(kept, list) or not isinstance(removed, list)
                or len(set(kept)) != len(kept) or len(set(removed)) != len(removed)
                or set(kept) & set(removed) or set(mapping) != set(kept) | set(removed)
                or len(set(map(str, mapping.values()))) != len(mapping)
                or (row['control'] and removed)):
                raise ValueError('invalid_metadata')
            ref = _decode(request.get('reference_text'))
            original = request['original_request_json']['schema']
            if not isinstance(original, dict) or schema_validator(ref, original):
                raise ValueError('reference_schema')
            row['reference_schema_ok'] = 1
            ref_obs = _observations(ref)
            ref_work = _work(ref, mapping, list(mapping))
            if ref.get('open_ids') != []:
                raise ValueError('reference_not_endform')
            row['reference_endform_ok'] = 1
            retained_changes = {a: action for a, action in ref_work.items() if a in kept and action != 'unchanged'}
            lifecycle_loss = {a for a in removed if ref_work[a] != 'unchanged'}
            observation_loss = {o['update_target'] for o in ref_obs.values() if o['update_target'] in removed}
            row.update(recall_total=len(retained_changes), lifecycle_filter_loss=len(lifecycle_loss),
                       observation_filter_loss=len(observation_loss), filter_loss=len(lifecycle_loss | observation_loss),
                       observation_total=len(ref_obs))
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            ref = None
            row['errors'] += 1
        if len(saved) != 1:
            # There is no automatic retry; duplicates cannot silently supply a best answer.
            row['errors'] += 1
        else:
            final = saved[0]
            try:
                if final.get('status') != 'ok' or not isinstance(final.get('response'), dict) or final['response'].get('status') != 'completed':
                    raise ValueError('nonterminal_result')
                candidate = _decode(final.get('text'))
                schema = request['request_json']['schema']
                if not isinstance(schema, dict) or schema_validator(candidate, schema):
                    raise ValueError('candidate_schema')
                row['schema_ok'] = 1
                actual_obs = _observations(candidate)
                actual_work = _work(candidate, mapping, kept)
                row['missing_observations'] = len(set(ref_obs) - set(actual_obs)) if ref is not None else None
                row['extra_observations'] = len(set(actual_obs) - set(ref_obs)) if ref is not None else None
                if candidate.get('open_ids') != [] or ref is None or set(actual_obs) != set(ref_obs):
                    raise ValueError('candidate_not_endform')
                row['endform_ok'] = 1
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError, UnboundLocalError):
                candidate = None
                row['errors'] += 1
        if ref is not None and candidate is not None:
            row['recall_hits'] = sum(actual_work.get(a) == action for a, action in retained_changes.items())
            row['additional_flags'] = sum(action != 'unchanged' and ref_work.get(a) != action for a, action in actual_work.items())
            for field in ('update_target', 'update', 'kind'):
                row[field + '_matches'] = sum(_literal_equal(o[field], actual_obs[i][field]) for i, o in ref_obs.items())
        row['cost_delta_micro_usd'] = row['actual_micro_usd'] - row['reference_micro_usd'] if row['actual_micro_usd'] is not None and row['reference_micro_usd'] is not None else None
        rows.append(row)
    fields = ('recall_hits', 'recall_total', 'lifecycle_filter_loss', 'observation_filter_loss', 'filter_loss',
              'additional_flags', 'update_target_matches', 'update_matches', 'kind_matches', 'observation_total',
              'actual_micro_usd', 'reference_micro_usd', 'cost_delta_micro_usd')
    groups = {}
    for label, control in (('filtered', 0), ('control', 1)):
        population = [r for r in rows if r['control'] == control]
        group = {field: _sum_known([r[field] for r in population]) if population else None for field in fields}
        group.update(calls=len(population), errors=sum(r['errors'] for r in population))
        group['update_target_rate'] = group['update_target_matches'] / group['observation_total'] if group['update_target_matches'] is not None and group['observation_total'] else None
        groups[label] = group
    f, c = groups['filtered'], groups['control']
    known = (bool(f['calls']) and c['calls'] == 3 and not global_errors and not f['errors'] and not c['errors']
             and all(r['reference_schema_ok'] and r['schema_ok'] and r['reference_endform_ok'] and r['endform_ok'] for r in rows)
             and f['update_target_rate'] is not None and c['update_target_rate'] is not None)
    recall_pass = int(f['recall_hits'] == f['recall_total']) if f['recall_hits'] is not None and f['recall_total'] is not None else None
    loss_pass = int(f['filter_loss'] == 0) if f['filter_loss'] is not None else None
    target_pass = int(f['update_target_rate'] + 1e-12 >= c['update_target_rate'] - .02) if f['update_target_rate'] is not None and c['update_target_rate'] is not None else None
    all_costs = [r.get('actual_micro_usd') if isinstance(r, dict) and _known_cost(r.get('actual_micro_usd')) else None for r in results]
    quality_pass = int(known and recall_pass and loss_pass and target_pass)
    cost_complete = int(bool(results) and all(v is not None for v in all_costs)
                        and all(r['reference_micro_usd'] is not None for r in rows))
    return dict(calls=rows, filtered=f, control=c, total=dict(attempts=len(results), global_errors=global_errors,
                actual_micro_usd=_sum_known(all_costs) if results else None,
                cost_unknown_attempts=sum(v is None for v in all_costs),
                error_attempts=sum(not isinstance(r, dict) or r.get('status') != 'ok' for r in results)),
                evidence_known=int(known), recall_pass=recall_pass, filter_loss_pass=loss_pass,
                update_target_pass=target_pass, quality_pass=quality_pass, cost_complete=cost_complete,
                passed=int(quality_pass and cost_complete))


def merged_results(paths):
    """Count identical saved results once; conflicting evidence fails closed.

    Derive a previously unknown historical cost from confirmed standard-tier
    final usage, without rewriting the source file or inventing missing usage.
    """
    def identical(left,right):
        # Python equality equates False/0 and True/1; JSON evidence must not.
        return json.dumps(left,sort_keys=True,allow_nan=False)==json.dumps(right,sort_keys=True,allow_nan=False)
    saved={}
    for path in paths:
        for result in _common().read_jsonl(path):
            key=_key(result)
            if key in saved:
                if not identical(saved[key],result):
                    raise ValueError('conflicting_result_identity')
                continue
            saved[key]=result
    merged=[]
    for result in saved.values():
        result=dict(result)
        body=result.get('response')
        if (result.get('actual_micro_usd') is None and isinstance(body,dict)
            and body.get('status')=='completed' and body.get('service_tier')=='default'
            and body.get('model')==result.get('model')=='gpt-6.1-sol'
            and identical(body.get('usage'),result.get('usage'))):
            result['actual_micro_usd']=_common().usage_micro_usd(result.get('usage'),result['model'])
        merged.append(result)
    return merged


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', type=Path, default=Path('selected_requests.jsonl'))
    parser.add_argument('--results', type=Path, nargs='+', action='append')
    args = parser.parse_args(argv)
    try:
        paths=[path for group in args.results for path in group] if args.results else [Path('results.jsonl')]
        report = compare_records(_common().read_jsonl(args.requests), merged_results(paths))
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'input_error': 1, 'passed': 0}))
        return 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
