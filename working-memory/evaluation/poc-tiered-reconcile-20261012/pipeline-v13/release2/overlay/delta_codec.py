"""Delta output v2. Pure stdlib; original aliases are expanded only afterwards.

Each observation explicitly retains its source_index and response order. Changes
are typed single-field objects, avoiding optional keys in strict provider schemas.
Absent changes retain the extraction value; an explicit null replaces it. Arrays
replace as a whole. Missing full-response fields cannot represent deletion: the
original contract requires every observation field, so this is rejected.
"""
from copy import deepcopy

VERSION = 'delta2'
DECISION_FIELDS = frozenset(('update_target', 'update', 'matter_id'))
OBSERVATION_FIELDS = frozenset(('matter', 'matter_id', 'kind', 'title', 'claim',
    'owner', 'commitment_strength', 'due_text', 'update_target', 'update',
    'uncertainty', 'required_review', 'evidence_ids', 'action_uncertainty',
    'condition_text', 'work_state', 'state_evidence_ids', 'subject',
    'search_keywords', 'assignment_score', 'change_score', 'confidence_reason'))


def equal(a, b):
    """Type-strict JSON equality, including nested bool/int distinctions."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def _sources(obs_in):
    result = {}
    for position, obs in enumerate(obs_in):
        if not isinstance(obs, dict):
            raise ValueError('Invalid extraction observation')
        index = obs.get('source_index', position)
        if type(index) is not int or index < 0 or index in result:
            raise ValueError('Invalid or duplicate extraction index')
        result[index] = {**deepcopy(obs), 'source_index': index}
    return result


def _slots(work_list):
    # The production lifecycle validator enumerates list positions, not work IDs.
    result = [str(i) for i in range(len(work_list))]
    for index, work in enumerate(work_list):
        if not isinstance(work, dict) or ('work_index' in work and work['work_index'] != str(index)):
            raise ValueError('Invalid work slot order')
    return result


def to_delta(full_response, obs_in, work_list, *, archive=False):
    sources, slots = _sources(obs_in), _slots(work_list)
    if not isinstance(full_response, dict) or not isinstance(full_response.get('observations'), list):
        raise ValueError('Invalid full response')
    result = deepcopy(full_response)
    result['observations'] = []
    seen = set()
    for item in full_response['observations']:
        index = item.get('source_index') if isinstance(item, dict) else None
        if type(index) is not int or index not in sources or index in seen:
            raise ValueError('Unknown or duplicate source index')
        seen.add(index)
        base = sources[index]
        if set(base) - set(item):
            raise ValueError('Full response removed an extraction field')
        if not DECISION_FIELDS <= item.keys():
            raise ValueError('Missing explicit observation decision')
        changes = [{key: deepcopy(value)} for key, value in item.items()
                   if key != 'source_index' and key not in DECISION_FIELDS and (key not in base or not equal(value, base[key]))]
        result['observations'].append({'source_index': index, 'decision': {key: deepcopy(item[key]) for key in sorted(DECISION_FIELDS)}, 'changes': changes})
    life = full_response.get('work_results')
    if archive and full_response.get('open_ids') and life == {}:
        # Archived compact_calls projects null to {}; never emitted by the live schema.
        result['_archived_empty_work_results'] = True
        life = None
    if life is None:
        result['work_results'] = None
        result['unchanged_work_indices'] = None
    else:
        if not isinstance(life, dict) or set(life) != set(slots):
            raise ValueError('Full lifecycle slot coverage mismatch')
        result['unchanged_work_indices'] = [key for key, value in life.items() if value == 'unchanged']
        result['work_results'] = [{'work_index': key, 'result': deepcopy(value)}
                                  for key, value in life.items() if value != 'unchanged']
        if any(not isinstance(v['result'], dict) or v['result'].get('action') == 'unchanged'
               for v in result['work_results']):
            raise ValueError('Invalid lifecycle change')
    # Validate the generated representation using the same strict decoder.
    from_delta(result, obs_in, work_list, archive=archive)
    return result


def from_delta(delta, obs_in, work_list, *, archive=False):
    sources, slots = _sources(obs_in), _slots(work_list)
    if not isinstance(delta, dict) or not isinstance(delta.get('observations'), list):
        raise ValueError('Invalid delta response')
    result = deepcopy(delta)
    result['observations'] = []
    seen = set()
    for patch in delta['observations']:
        if not isinstance(patch, dict) or set(patch) != {'source_index', 'decision', 'changes'}:
            raise ValueError('Invalid observation patch')
        index = patch['source_index']
        if type(index) is not int or index not in sources or index in seen:
            raise ValueError('Unknown or duplicate source index')
        seen.add(index)
        if not isinstance(patch['changes'], list):
            raise ValueError('Invalid changes list')
        decision = patch['decision']
        if not isinstance(decision, dict) or set(decision) != DECISION_FIELDS:
            raise ValueError('Missing or invalid explicit observation decision')
        item = deepcopy(sources[index])
        item.update(deepcopy(decision))
        keys = set()
        for change in patch['changes']:
            if not isinstance(change, dict) or len(change) != 1:
                raise ValueError('Change must contain exactly one field')
            key = next(iter(change))
            if key == 'source_index' or key in DECISION_FIELDS or key in keys or key not in OBSERVATION_FIELDS:
                raise ValueError('Unknown or duplicate changed field')
            keys.add(key)
            item[key] = deepcopy(change[key])
        result['observations'].append(item)
    if '_archived_empty_work_results' in result and not archive:
        raise ValueError('Archive projection marker is not a live response field')
    archived_empty = result.pop('_archived_empty_work_results', False)
    if type(archived_empty) is not bool:
        raise ValueError('Invalid archive projection marker')
    requested = delta.get('open_ids', [])
    life = delta.get('work_results')
    unchanged = delta.get('unchanged_work_indices')
    if not isinstance(requested, list):
        raise ValueError('Invalid archive expansion')
    if requested:
        if delta['observations'] or life is not None or unchanged not in (None, []):
            raise ValueError('Expansion cannot publish a partial result')
        result['work_results'] = {} if archived_empty else None
    else:
        if archived_empty:
            raise ValueError('Archive projection marker requires expansion')
        if seen != set(sources):
            raise ValueError('Delta observation coverage mismatch')
        if not isinstance(life, list) or not isinstance(unchanged, list):
            raise ValueError('Final lifecycle coverage must be explicit')
        if any(type(key) is not str for key in unchanged) or len(set(unchanged)) != len(unchanged):
            raise ValueError('Invalid or duplicate unchanged slot')
        if not set(unchanged) <= set(slots):
            raise ValueError('Unknown unchanged slot')
        results = {}
        for entry in life:
            if not isinstance(entry, dict) or set(entry) != {'work_index', 'result'}:
                raise ValueError('Invalid lifecycle patch')
            key, value = entry['work_index'], entry['result']
            if type(key) is not str or key not in slots or key in results or key in unchanged:
                raise ValueError('Unknown, duplicate or overlapping lifecycle slot')
            if not isinstance(value, dict) or value.get('action') == 'unchanged':
                raise ValueError('Invalid lifecycle change')
            results[key] = deepcopy(value)
        if set(results) | set(unchanged) != set(slots):
            raise ValueError('Final lifecycle coverage mismatch')
        result['work_results'] = {key: results.get(key, 'unchanged') for key in slots}
    result.pop('unchanged_work_indices', None)
    return result
