import json, pickle, sys, collections, re, math, operator, datetime as dt
exec(open(sys.argv[1] + '/recall2.py').read().split("rows = [json.loads")[0].replace("SP = sys.argv[1]", "SP = sys.argv[1]"))
rows = [json.loads(l) for l in open(SP + '/compact_calls.jsonl')]
rows = [r for r in rows if 'error' not in r and r['work'] and r['obs_in'] and r.get('meeting_date')]
t_ranks = []; l_info = []
for r in rows:
    day = dt.date.fromisoformat(r['meeting_date'])
    idx2 = {w['work_index']: w['id'] for w in r['work']}
    alias_idx = {w['id']: j for j, w in enumerate(r['work'])}
    W = r['work']; n = len(W)
    M = [(lambda v: norm(v) if v else None)(wvec(w)) for w in W]
    wt = [toks(' '.join([w.get('title') or '', w.get('claim') or '', w.get('matter') or ''])) for w in W]
    def ranks_for(o):
        q = qv.get(json.dumps([qkey(o)], ensure_ascii=False)) or qv.get(json.dumps([qkey(o)]))
        if isinstance(q, str): q = json.loads(q)
        e = [10**6]*n
        if q:
            qn = norm(q)
            for rk, (_, j) in enumerate(sorted((-(dot(qn, M[j])) if M[j] else 1, j) for j in range(n))): e[j] = rk
        qt = toks(qkey(o) + ' ' + (o.get('claim') or ''))
        lx = [10**6]*n
        for rk, (_, j) in enumerate(sorted((-(len(qt & wt[j]) / math.sqrt(len(qt) * len(wt[j]) or 1)), j) for j in range(n))): lx[j] = rk
        return e, lx
    obs_in = {o['source_index']: o for o in r['obs_in']}
    targeted_pairs = [(o['source_index'], o['update_target']) for o in r['obs_out'] if o.get('update_target') in alias_idx]
    tgt_ids = {a for _, a in targeted_pairs}
    for si, a in targeted_pairs:
        e, lx = ranks_for(obs_in[si]); j = alias_idx[a]
        t_ranks.append((e[j], lx[j], min(e[j], lx[j])))
    changed = {idx2.get(k) for k, v in r['work_results'].items() if v != 'unchanged'}
    for a in changed - tgt_ids:
        j = alias_idx[a]
        best_e = best_l = 10**6
        for o in r['obs_in']:
            e, lx = ranks_for(o); best_e = min(best_e, e[j]); best_l = min(best_l, lx[j])
        try: age = (day - dt.date.fromisoformat(W[j]['last_changed'][:10])).days
        except Exception: age = None
        l_info.append((r['work_results'][next(k for k, v in idx2.items() if v == a)], best_e, best_l, age, n))
print('TARGETED (alignment) pairs:', len(t_ranks))
for lim in (1, 2, 3, 5, 8, 10, 20):
    print('  rank<%d  emb %5.1f%%  lex %5.1f%%  either %5.1f%%' % (lim, *[100*sum(1 for t in t_ranks if t[i] < lim)/len(t_ranks) for i in range(3)]))
print('LIFECYCLE-only changed items:', len(l_info))
for x in l_info: print('  action', x[0] if isinstance(x[0], str) else json.dumps(x[0], ensure_ascii=False)[:60], '| best emb rank', x[1], '| best lex rank', x[2], '| age', x[3], '| of', x[4])
