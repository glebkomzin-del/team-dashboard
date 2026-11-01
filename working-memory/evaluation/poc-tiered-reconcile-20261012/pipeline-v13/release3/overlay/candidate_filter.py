"""Deterministic Hot-Set selection; no I/O and no mutation of input objects."""
from collections.abc import Mapping
from datetime import date, datetime


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
        except ValueError:
            return None


def filter_work(work, query_hits, observations, meeting_date, exact_ids, *, age_days_max=30, rank_max=5, keep_waiting=False):
    """Keep age OR observation-query rank OR exact-ID OR enabled waiting matches.

    Hit sequences must be in Work-search rank order. Mapping values preserve
    insertion order; non-Work hits are ignored. Duplicate hits occupy their
    original rank slots but never increment a row's reason count twice.
    Missing/invalid dates (including meeting_date) conservatively satisfy age.
    Reason counts are independent and may overlap; they count retained rows.
    The waiting counter is present only when enabled, preserving OFF statistics.
    """
    if type(keep_waiting) is not bool:
        raise ValueError('keep_waiting must be a boolean')
    for value in (age_days_max, rank_max):
        if type(value) is not int or value < 0:
            raise ValueError('Hot-Set thresholds must be non-negative integers')
    meeting_day = _day(meeting_date)
    ranked_ids = set()
    for observation in observations:
        query = ' '.join([observation['title'], observation.get('subject', ''),
                          *observation.get('search_keywords', [])])
        hits = query_hits.get(query, ())
        if isinstance(hits, Mapping):
            hits = hits.values()
        work_hits = (hit for hit in hits if hit.get('kind', 'work') == 'work')
        for rank, hit in enumerate(work_hits):
            if rank >= rank_max:
                break
            ranked_ids.add(hit.get('target_id'))
    exact_ids = set(exact_ids)
    kept, dropped = [], []
    stats = {'n_in': 0, 'n_kept': 0, 'n_dropped': 0, 'age': 0, 'rank': 0, 'exact': 0,
             'age_days_max': age_days_max, 'rank_max': rank_max}
    if keep_waiting:
        stats['waiting'] = 0
    for item in work:
        changed = _day(item.get('last_changed'))
        age = meeting_day is None or changed is None or (meeting_day - changed).days <= age_days_max
        rank = item['id'] in ranked_ids
        exact = item['id'] in exact_ids
        waiting = keep_waiting and item.get('status') == 'waiting'
        stats['n_in'] += 1
        if age or rank or exact or waiting:
            kept.append(item)
            for reason, matches in (('age', age), ('rank', rank), ('exact', exact)):
                stats[reason] += int(matches)
            if keep_waiting:
                stats['waiting'] += int(waiting)
        else:
            dropped.append(item)
    stats.update(n_kept=len(kept), n_dropped=len(dropped))
    return kept, dropped, stats
