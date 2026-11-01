import sys, json, pickle
workdocs = {}   # body -> vector (kind work)
queries = {}    # prompt -> vector
nq = 0
for line in sys.stdin:
    head = line[:40]
    if '"search_document"' in head:
        r = json.loads(line); d = json.loads(r['record_json'])
        if d['kind'] == 'work' and d.get('embedding') and d.get('body'):
            workdocs.setdefault(d['body'], d['embedding'])
    elif '"kind": "call"' in head:
        r = json.loads(line); c = json.loads(r['record_json'])
        resp = c['response_json']; resp = json.loads(resp) if isinstance(resp, str) else resp
        if isinstance(resp, dict) and resp.get('embeddings'):
            req = c['request_json']; req = json.loads(req) if isinstance(req, str) else req
            p = req.get('prompt')
            vecs = resp['embeddings']
            if isinstance(p, str): queries[p] = vecs[0]
            elif isinstance(p, list):
                for t, v in zip(p, vecs): queries[t] = v
            nq += 1
pickle.dump({'workdocs': workdocs, 'queries': queries}, open(sys.argv[1], 'wb'))
print('workdocs', len(workdocs), 'queries', len(queries), 'embedding calls', nq)
