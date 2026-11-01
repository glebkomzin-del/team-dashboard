"""Read paid baseline requests; build compact diagnostic without an API call.

Uses the union of each old batch's candidates (a conservative superset). This
measures prompt size; it cannot establish semantic quality of the new request.
"""
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compact_reconcile import Catalog, INSTRUCTION, response_schema
from retrieval_context import pack_catalog
from hybrid_index import encode
from hybrid_pipeline import CONFIDENCE, compact_candidates
from call_budget import reserve_micro_usd
import reconcile


def measure(folder):
    folder = Path(folder)
    reference = json.loads((folder/'baseline-cost.json').read_text())['gpt-5.6-terra']
    ids = {s['response_id']: s['stage'] for s in reference['stages']}
    db = sqlite3.connect('file:'+str(folder/'ledger.sqlite')+'?mode=ro', uri=True)
    stages = {}
    for request, response in db.execute('SELECT request,response FROM calls WHERE response IS NOT NULL'):
        response = json.loads(response)
        if response.get('id') in ids:
            stages[ids[response['id']]] = (json.loads(request), response)
    db.close()
    work = {}; hits = {}; observations = {}; query_hits = {}
    for name, (request, _) in stages.items():
        prompt = request['prompt']
        if name.startswith('align-'):
            packed = json.loads(prompt.split('\nKandidaten:\n')[1].split('\nMeeting: ')[0])
            catalog = packed['candidates']
            for w in catalog['work']:
                work[w['id']] = w
            batch = json.loads(prompt.split('\nVorläufige Beobachtungen:\n')[1].split('\nKandidaten:\n')[0])
            batch_hits = {}
            for h in catalog['search_hits']:
                h = {**h, 'text': packed['historical_texts'][h['text_ref']],
                     'metadata': {'matter_id': h.get('matter_id')}}
                del h['text_ref']
                hits[h['id']] = h; batch_hits[h['id']] = h
            for item in batch:
                observations[item['source_index']] = item
                query = ' '.join([item['title'], item.get('subject', ''), *item.get('search_keywords', [])])
                query_hits[query] = batch_hits
        if name.startswith('lifecycle-'):
            rows = json.loads(prompt.split('\nAlle noch zu prüfenden Arbeits-IDs:\n')[1]
                              .split('\nVollständiges aktuelles Original:\n')[0])
            # Lifecycle aliases are not stored identities; recover against full
            # descriptions. For diagnostic-only unseen rows use stable local IDs.
            for w in rows:
                matches = [v for v in work.values() if all(v.get(k) == w.get(k)
                           for k in ('title','claim','owner','last_changed','condition_text'))]
                if matches:
                    continue
                w = {**w, 'id': name+':'+w['id']}
                work[w['id']] = w
    first = stages['align-0'][0]['prompt']
    rules = first.split('\nZusätzliche v10-Regeln:')[0]
    base = '\nMeeting: '+first.split('\nMeeting: ', 1)[1]
    catalog = Catalog(list(work.values()), hits, query_hits)
    obs = [observations[i] for i in sorted(observations)]
    prompt = (rules+'\n'+CONFIDENCE+'\n'+INSTRUCTION+'\n'+reconcile.PROMPT+
              '\nVorläufige Beobachtungen:\n'+encode(obs)+'\nKandidaten:\n'+encode(pack_catalog(catalog.render(set())))+base)
    schema = response_schema(catalog, sorted(observations))
    before = sum(len(r['prompt']) for name, (r, _) in stages.items()
                 if name.startswith(('align-', 'lifecycle-')))
    result = {'baseline_reconciliation_calls': 10, 'baseline_reconciliation_characters': before,
              'compact_first_call_characters': len(prompt), 'character_reduction_fraction': 1-len(prompt)/before,
              'work_candidates': len(work), 'search_candidates': len(hits), 'observations': len(obs),
              'maximum_reservation_usd': reserve_micro_usd(prompt, 'gpt-5.6-terra', 16000, schema)/1e6,
              'quality_validated': False, 'note': 'Size only; expansions and retries are not included.'}
    (folder/'compact-diagnostic-request.json').write_text(encode({'prompt': prompt, 'schema': schema}))
    (folder/'compact-measurement.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    print(json.dumps(measure(sys.argv[1]), indent=2))
