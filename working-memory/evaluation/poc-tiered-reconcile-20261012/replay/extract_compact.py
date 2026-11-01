import sys, json, collections, re
dec = json.JSONDecoder()
out = open(sys.argv[1], 'w')
n = 0; ex = None
def alias_to_idx(a):
    return a
for line in sys.stdin:
    if '"kind": "call"' not in line[:60]: continue
    r = json.loads(line)
    c = json.loads(r['record_json'])
    req = c['request_json']; req = json.loads(req) if isinstance(req, str) else req
    p = req.get('prompt', '') or ''
    if 'Bereits geöffnete Original-IDs' not in p: continue
    try:
        i = p.index('\nKandidaten:\n') + 13
        packed, _ = dec.raw_decode(p, i)
        oi = p.index('\nVorläufige Beobachtungen:\n') + len('\nVorläufige Beobachtungen:\n')
        obs, _ = dec.raw_decode(p, oi)
        resp = c['response_json']; resp = json.loads(resp) if isinstance(resp, str) else resp
        text = resp['content'][0]['text']
        o = json.loads(text)
    except Exception as e:
        out.write(json.dumps({'job_id': c['job_id'], 'call_index': c['call_index'], 'error': str(e)[:120]}) + '\n'); continue
    t = packed['tables']['work']; f = t['fields']; texts = packed['texts']
    work = []
    for row in t['rows']:
        d = {}
        for k, cell in zip(f, row):
            if k in t['text_fields'] and isinstance(cell, int) and not isinstance(cell, bool): d[k] = texts[cell]
            else: d[k] = cell
        work.append(d)
    nav = packed['metadata'].get('archive_navigation', {})
    nav_rows = 0
    try:
        nav_rows = sum(len(tt['rows']) for tt in nav.get('tables', {}).values())
    except Exception: pass
    wr = o.get('work_results') or {}
    if isinstance(wr, list): wr = {str(i): x for i, x in enumerate(wr)}
    if ex is None and wr:
        k0 = next(iter(wr)); ex = wr[k0]
    u = resp.get('usage', {})
    mdate = re.search(r'\nDatum: (\d{4}-\d{2}-\d{2})', p)
    rec = {'meeting_date': mdate.group(1) if mdate else None, 'job_id': c['job_id'], 'call_index': c['call_index'], 'created_at': c['created_at'],
           'prompt_chars': len(p), 'in_tok': u.get('input_tokens'), 'out_tok': u.get('output_tokens'),
           'reason_tok': (u.get('output_tokens_details') or {}).get('reasoning_tokens'),
           'micro': c['actual_micro_usd'], 'n_cards': nav_rows, 'n_texts': len(texts),
           'work': work, 'obs_in': obs, 'obs_out': o.get('observations', []), 'work_results': wr,
           'open_ids': o.get('open_ids'), 'stop': resp.get('stop_reason')}
    out.write(json.dumps(rec, ensure_ascii=False) + '\n'); n += 1
print('compact calls', n); print('example work_result', json.dumps(ex, ensure_ascii=False)[:400])
