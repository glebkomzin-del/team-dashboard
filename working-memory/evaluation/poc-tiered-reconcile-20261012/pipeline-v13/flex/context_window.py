"""Bounded, explicit retrieval plus a complete catalogue of existing work identities."""
from collections import Counter
from datetime import date, timedelta
import json
import re
from memory import context, overview, ValidationError
from archive_index import connect as archive_connect, bounds, LATEST

STOP = set('aber alle alles also andere auch auf aus bei bin bis bitte das dass dein dem den der des die diese dieser dieses doch dort du durch ein eine einem einen einer eines er es etwas für ganz geht gibt habe haben hat hier ich ihr ihre im in ist ja kann kein keine können machen mal man mehr mich mit muss nach nicht noch nun nur oder schon sein seine sich sie sind so soll um und uns unser vom von vor war was weil wenn werden wie wieder wir wird wo zu zum zur über'.split())
RETRIEVAL_BUDGET_CHARS = 450_000
RETRIEVAL_HARD_LIMIT_CHARS = 460_000

def compact_work(state):
    work = state['personal'] + state['waiting'] + state['waiting_dependencies'] + state['completed']
    # Every work identity is included, including completed work that could be reopened.
    # Full event history stays in the database; current values keep their original provenance.
    fields = ('id','title','claim','matter','owner','status','due_text','due_reference_date','condition_text','last_changed','uncertainty','action_uncertainty')
    return [{key: item.get(key) for key in fields} for item in work]

def retrieval(db, meeting, archive_path='', limit=40, prior_days_only=False):
    cutoff = (date.fromisoformat(meeting['meeting_date'][:10])-timedelta(days=1)).isoformat() if prior_days_only else meeting['meeting_date'][:10]
    history = context(db, cutoff)
    state = overview(db, cutoff)
    matters = list({r['matter_id']: {'id': r['matter_id'], 'title': r['matter_title']} for r in history}.values())
    compact = compact_work(state)
    words = re.findall(r'\w{4,}', meeting['raw_transcript'].casefold(), re.UNICODE)
    counts = Counter(word for word in words if word not in STOP and not word.isdecimal())
    title_terms = [word for word in re.findall(r'\w{4,}', meeting['title'].casefold()) if word not in STOP]
    terms = list(dict.fromkeys(title_terms + [w for w, _ in counts.most_common(24)]))[:32]
    selected = []
    for observation in history:
        text = (observation['data']['claim'] + ' ' + observation['matter_title']).casefold()
        score = sum(1 for term in terms if term in text)
        if score: selected.append((score, observation))
    selected.sort(key=lambda row: (-row[0], row[1]['id']))
    facts = [{'id': row['id'], 'matter_id': row['matter_id'], 'date': row['event_date'], **row['data']} for _, row in selected[:60]]
    passages = []; total = 0
    cutoff = (date.fromisoformat(meeting['meeting_date'][:10]) - timedelta(days=1)).isoformat()
    if archive_path and terms:
        archive = archive_connect(archive_path, readonly=True)
        try:
            expression = ' OR '.join('"' + term + '"' for term in terms)
            _, known_at = bounds(cutoff, meeting.get('observed_at'))
            args = (expression, cutoff, known_at, known_at)
            where = 'passage_search MATCH ? AND ' + LATEST
            total = archive.execute('SELECT count(*) FROM passage_search JOIN passages p ON p.id=passage_search.rowid JOIN documents d ON d.id=p.document_id WHERE '+where,args).fetchone()[0]
            rows = archive.execute('''SELECT d.id,d.source_id,d.title,d.event_date,d.body_hash,p.start,p.end,p.text,bm25(passage_search,1.0,3.0) score
              FROM passage_search JOIN passages p ON p.id=passage_search.rowid JOIN documents d ON d.id=p.document_id WHERE '''+where+' ORDER BY score,d.event_date DESC,p.start LIMIT ?',(*args,limit)).fetchall()
            passages = [dict(row) for row in rows]
        finally: archive.close()
    prior = {'matters': matters, 'work': compact, 'observations': facts, 'prior_original_passages': passages,
             'retrieval': {'method': 'lexical_retrieval_v1', 'all_work_identities': len(compact), 'all_matters': len(matters),
               'history_observations_total': len(history), 'history_observations_selected': len(facts),
               'archive_matching_passages': total, 'archive_selected_passages': len(passages),
               'archive_event_cutoff': cutoff, 'terms': terms,
               'limitation': 'Ranked historical excerpts are context, not exhaustive historical coverage; same-day archive originals excluded. Current meeting is included in full.'}}
    if prior_days_only:
        current=overview(db,meeting['meeting_date'][:10])
        same_day=[item for key in ('personal','waiting','waiting_dependencies','completed') for item in current[key]
                  if item.get('history') and item['history'][0]['event_date']==meeting['meeting_date'][:10]]
        prior['unordered_same_day_work']=[{key:item.get(key) for key in ('id','title','claim','owner','matter')} for item in same_day]
        prior['retrieval']['same_day_order']='Unknown; same-day identities only, no assumed previous state or causal history.'
        prior['retrieval']['same_day_identity_count']=len(same_day)
    # Reserve the complete work catalogue; reduce only whole historical records.
    prior['observations']=[];prior['prior_original_passages']=[]
    base_size=len(json.dumps(prior,ensure_ascii=False))
    # v9 permits a 600k-character prompt. Keep every existing work identity and
    # reserve at least 140k for instructions plus the complete current source.
    if base_size>RETRIEVAL_BUDGET_CHARS:
        raise ValidationError('Existing work catalogue exceeds reviewed budget; explicit partition/replay required')
    remaining=RETRIEVAL_BUDGET_CHARS-base_size
    for records,key in [(facts,'observations'),(passages,'prior_original_passages')]:
        budget=min(60000,remaining//2) if key=='observations' else min(90000,remaining)
        used=0
        for record in records:
            size=len(json.dumps(record,ensure_ascii=False))+2
            if used+size>budget:continue
            prior[key].append(record);used+=size
        remaining-=used
    prior['retrieval']['history_observations_selected']=len(prior['observations'])
    prior['retrieval']['archive_selected_passages']=len(prior['prior_original_passages'])
    if len(json.dumps(prior, ensure_ascii=False)) > RETRIEVAL_HARD_LIMIT_CHARS:
        raise ValidationError('Existing work catalogue exceeds reviewed budget; explicit partition/replay required')
    return prior
