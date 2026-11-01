import json, pickle, sys, collections, re, math, operator, datetime as dt
SP = sys.argv[1]
V = pickle.load(open(SP + '/vectors.pkl', 'rb')); qv = V['queries']
wd = {b: (json.loads(v) if isinstance(v, str) else v) for b, v in V['workdocs'].items()}
by_title = collections.defaultdict(list)
for body, vec in wd.items():
    for ln in body.split('\n')[:3]: by_title[ln.strip()].append((body, vec))
def norm(v):
    n = math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/n for x in v]
def dot(a, b): return sum(map(operator.mul, a, b))
def wvec(w):
    c = by_title.get((w.get('title') or '').strip(), [])
    if not c: return None
    claim = (w.get('claim') or '').strip()
    for body, vec in c:
        if claim and claim[:60] in body: return vec
    return c[0][1]
def qkey(o): return ' '.join([o.get('title') or '', o.get('subject') or '', *(o.get('search_keywords') or [])])
def toks(t): return {x[:6] for x in re.findall(r'\w{4,}', (t or '').casefold())}
rows = [json.loads(l) for l in open(SP + '/compact_calls.jsonl')]
rows = [r for r in rows if 'error' not in r and r['work'] and r['obs_in'] and r.get('meeting_date')]
recs = []   # per call: list of dict(per candidate: used, age, status, emb_rank, lex_rank)
for r in rows:
    day = dt.date.fromisoformat(r['meeting_date'])
    idx2 = {w['work_index']: w['id'] for w in r['work']}
    changed = {idx2.get(k) for k, v in r['work_results'].items() if v != 'unchanged'}
    targeted = {o.get('update_target') for o in r['obs_out'] if o.get('update_target')}
    used = changed | targeted
    W = r['work']
    M = []
    for w in W:
        v = wvec(w); M.append(norm(v) if v else None)
    Q = []
    for o in r['obs_in']:
        q = qv.get(json.dumps([qkey(o)], ensure_ascii=False)) or qv.get(json.dumps([qkey(o)]))
        if isinstance(q, str): q = json.loads(q)
        Q.append((norm(q) if q else None, toks(qkey(o) + ' ' + (o.get('claim') or ''))))
    n = len(W)
    emb_rank = [10**6]*n; lex_rank = [10**6]*n
    for q, qt in Q:
        if q is not None:
            sc = [(-(dot(q, M[j])) if M[j] else 1, j) for j in range(n)]
            for rk, (_, j) in enumerate(sorted(sc)): emb_rank[j] = min(emb_rank[j], rk)
        ls = []
        for j, w in enumerate(W):
            wt = toks(' '.join([w.get('title') or '', w.get('claim') or '', w.get('matter') or '']))
            ls.append((-(len(qt & wt) / math.sqrt(len(qt) * len(wt) or 1)), j))
        for rk, (_, j) in enumerate(sorted(ls)): lex_rank[j] = min(lex_rank[j], rk)
    for j, w in enumerate(W):
        try: age = (day - dt.date.fromisoformat(w['last_changed'][:10])).days
        except Exception: age = 9999
        recs.append({'call': r['job_id'][:8], 'used': w['id'] in used, 'age': age, 'status': w.get('status'),
                     'er': emb_rank[j], 'lr': lex_rank[j], 'n': n})
tot = len(recs); U = sum(1 for x in recs if x['used'])
print('candidates', tot, 'used', U)
print('filter: keep if age<=A OR emb_rank<k OR lex_rank<k   (rank = best rank over observations)')
print('   A   k |  recall   kept%   missed used')
for A in (0, 7, 14, 21, 30, 45):
    for k in (0, 3, 5, 8, 12):
        keep = [x for x in recs if x['age'] <= A or x['er'] < k or x['lr'] < k]
        got = sum(1 for x in keep if x['used'])
        if A == 0 and k == 0: continue
        print('%4d %3d | %5.1f%% %7.1f%% %6d' % (A, k, 100*got/U, 100*len(keep)/tot, U - got))
# what do the misses look like at A=30,k=5
print('\nmissed used items at A=30,k=5:')
for x in recs:
    if x['used'] and not (x['age'] <= 30 or x['er'] < 5 or x['lr'] < 5):
        print('  call', x['call'], 'age', x['age'], 'status', x['status'], 'emb_rank', x['er'], 'lex_rank', x['lr'], 'of', x['n'])
