import sys, json, collections
targets = collections.defaultdict(set); dates = {}
for line in sys.stdin:
    if '"search_document"' not in line[:40]: continue
    d = json.loads(json.loads(line)['record_json'])
    if d['kind'] != 'work': continue
    targets[d['target_id']].add(d['event_date'])
    dates[d['target_id']] = max(dates.get(d['target_id'], ''), d['event_date'] or '')
print('distinct work targets', len(targets))
byday = collections.Counter(v for v in dates.values())
cum = 0
for day in sorted(byday)[-14:]:
    pass
# stock size as of each meeting date (targets whose first event_date <= day)
first = {t: min(v) for t, v in targets.items() if v}
for day in ['2026-09-15', '2026-09-30', '2026-10-05', '2026-10-08', '2026-10-12']:
    print(day, 'stock', sum(1 for f in first.values() if f <= day))
