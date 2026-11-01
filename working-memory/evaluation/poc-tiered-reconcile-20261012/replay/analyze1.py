import json, collections, statistics as st
rows = [json.loads(l) for l in open('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/compact_calls.jsonl')]
errs = [r for r in rows if 'error' in r]; rows = [r for r in rows if 'error' not in r]
print('calls', len(rows), 'errors', len(errs))
acts = collections.Counter()
tot = collections.defaultdict(float)
print('%-9s %4s %5s %5s %5s | %5s %5s %6s | %7s %6s %6s' % ('job', 'obsI', 'work', 'cards', 'texts', 'chg', 'tgt', 'used%', 'in_tok', 'out', 'USD'))
for r in sorted(rows, key=lambda r: r['created_at']):
    wr = r['work_results']
    changed = {k for k, v in wr.items() if v != 'unchanged'}
    # map work_index -> alias id
    idx2alias = {w['work_index']: w['id'] for w in r['work']}
    alias_changed = {idx2alias.get(k) for k in changed}
    targeted = {o.get('update_target') for o in r['obs_out'] if o.get('update_target')}
    used = alias_changed | targeted
    for v in wr.values(): acts[v if isinstance(v, str) else json.dumps(v)[:30]] += 1
    nwork = len(r['work'])
    tot['work'] += nwork; tot['used'] += len(used); tot['micro'] += r['micro']; tot['out'] += r['out_tok'] or 0; tot['in'] += r['in_tok'] or 0
    print('%-9s %4d %5d %5d %5d | %5d %5d %5.1f%% | %7s %6s %6.3f' % (r['job_id'][:8], len(r['obs_in']), nwork, r['n_cards'], r['n_texts'], len(alias_changed), len(targeted & set(idx2alias.values())), 100*len(used)/max(1,nwork), r['in_tok'], r['out_tok'], r['micro']/1e6))
print('TOTAL work candidates', int(tot['work']), 'used', int(tot['used']), '%.1f%%' % (100*tot['used']/tot['work']), 'cost USD %.2f' % (tot['micro']/1e6), 'in', int(tot['in']), 'out', int(tot['out']))
print('work_result values', acts.most_common(8))
