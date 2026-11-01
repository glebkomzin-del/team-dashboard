"""Immutable, scope-bound search snapshots; vectors are not factual evidence.

Documents contain source text, never generated historical classifications.
Only missing content hashes are embedded. SQL enforces complete snapshots.
"""
from datetime import date, timedelta
import hashlib
import json
import re
import math

from memory import context, overview, ValidationError
from archive_index import connect as archive_connect, bounds, LATEST

MODEL = 'text-embedding-3-small'
DIMENSIONS = 1536
# The production table is deliberately pinned to this exact cache profile.
# A model or dimension change must first migrate SQL, backup/restore and the
# gateway together; fail closed here instead of reusing body-only vectors.
EMBEDDING_CACHE_PROFILE = ('text-embedding-3-small', 1536, 'schema-v1')
VERSION = 'hybrid-v1'
SEARCH_METHOD = 'hybrid-rrf-hnsw200-v1'
EMBED_SCHEMA = {'type': 'embedding', 'dimensions': DIMENSIONS}
SEARCH_PUT_ITEMS = 8
SEARCH_PUT_BYTES = 750000

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def assert_embedding_cache_profile():
    if (MODEL,DIMENSIONS)!=EMBEDDING_CACHE_PROFILE[:2]:
        raise ValidationError('Embedding model change requires a coordinated cache migration')

def parts(text, size=1400, overlap=120):
    """Stable paragraph/speaker chunks; overlap only inside oversized blocks."""
    if not isinstance(size,int) or isinstance(size,bool) or size<1:raise ValueError('Invalid chunk size')
    if not isinstance(overlap,int) or isinstance(overlap,bool) or not 0<=overlap<size:raise ValueError('Invalid chunk overlap')
    boundaries={0,len(text)}
    boundaries.update(match.end() for match in re.finditer(r'\n[ \t]*\n+',text))
    boundaries.update(match.start() for match in re.finditer(r'(?m)^(?:\d{1,2}:\d{2}(?::\d{2})?\s+)?[^\n:]{1,80}:\s',text) if match.start())
    points=sorted(boundaries)
    blocks=[(left,right) for left,right in zip(points,points[1:]) if left<right]
    pending=None
    for left,right in blocks:
        if right-left>size:
            if pending and text[pending[0]:pending[1]].strip():yield pending[0],text[pending[0]:pending[1]]
            pending=None;start=left
            while start<right:
                end=min(start+size,right);body=text[start:end]
                if body.strip():yield start,body
                if end==right:break
                start=end-overlap
        elif pending is None:
            pending=(left,right)
        elif right-pending[0]<=size:
            pending=(pending[0],right)
        else:
            if text[pending[0]:pending[1]].strip():yield pending[0],text[pending[0]:pending[1]]
            pending=(left,right)
    if pending and text[pending[0]:pending[1]].strip():yield pending[0],text[pending[0]:pending[1]]

def archive_parts(text, size=1400):
    """Preserve existing archive index identities; passages already overlap.

    Rechunking the historical archive here duplicates thousands of vectors.
    Any future archive chunk profile needs an explicit bounded migration.
    """
    for start in range(0,len(text),size):
        body=text[start:start+size]
        if body.strip():yield start,body

def documents(db, meeting, archive_path=''):
    cutoff = (date.fromisoformat(meeting['meeting_date'][:10])-timedelta(days=1)).isoformat()
    result = {}
    def add(kind, target, source, version, day, observed, text, metadata):
        if not isinstance(text, str) or not text.strip(): return
        split=archive_parts if kind in ('passage','summary') else parts
        for start, body in split(text):
            row = {'kind': kind, 'target_id': target, 'source_id': source, 'source_version': version,
                   'event_date': day, 'observed_at': observed, 'text': body,
                   'metadata': {**metadata, 'part_start': start}, 'content_hash': digest(body),
                   'embedding_model': MODEL}
            row['id'] = digest(VERSION+':'+encode(row))
            result[row['id']] = row
    from human_decisions import project_knowledge
    # Rejected interpretations remain in the human audit projection, but are
    # not active retrieval candidates until explicitly confirmed/corrected.
    history = project_knowledge(db, context(db, cutoff), cutoff, active_only=True)
    for row in history:
        data = row['data']
        source = db.execute('SELECT * FROM source_versions WHERE id=?', (row['source_version'],)).fetchone()
        add('knowledge', row['id'], source['source_id'] if source else '', row['source_version'], row['event_date'],
            __import__('datetime').datetime.fromtimestamp(source['observed_at'],__import__('datetime').timezone.utc).isoformat() if source else None, ('Vom Nutzer korrigierte Fassung (Originalbelege bleiben unverändert):\n' if data.get('correction_history') else '')+'\n'.join(str(data.get(k) or '') for k in ('matter', 'title', 'claim', 'owner', 'condition_text', 'subject', 'search_keywords')),
            {'matter_id': row['matter_id'], 'matter': row['matter_title'], 'quotes': data.get('quotes', []), **({'human_correction': data['correction_history'], 'original_interpretation': data['original_interpretation']} if data.get('correction_history') else {})})
    from planner import state as planning_state
    planning=planning_state(db,cutoff)
    for memory in planning['memories'].values():
        if memory['deleted']:continue
        add('knowledge',memory['id'],'human:'+memory['provenance']['actor_id'],memory['provenance']['command_id'],
            memory['last_changed'],None,'Nutzernotiz (vom angemeldeten Eigentümer ausdrücklich gespeichert):\n'+memory['title']+'\n'+memory['claim'],
            {'matter_id':'explicit-user-memory','matter':'Nutzernotizen','title':memory['title'],
             'quotes':[memory['claim']],'user_memory':True,'provenance':memory['provenance']})
    from planner import overlay as planning_overlay
    state = planning_overlay(db, overview(db, meeting['meeting_date'][:10]), meeting['meeting_date'][:10])
    for group in ('personal', 'waiting', 'waiting_dependencies', 'completed'):
        for item in state[group]:
            first = (item.get('history') or [{}])[0]
            text = '\n'.join(str(item.get(k) or '') for k in
                            ('matter', 'title', 'claim', 'owner', 'due_text', 'condition_text', 'subject'))
            text += '\n'+' '.join(item.get('search_keywords', []))
            add('work', item['id'], first.get('source_id', ''), first.get('source_version', ''),
                item['last_changed'], None, text, {'matter_id': item.get('matter_id'), 'matter': item.get('matter'),
                'status': item['status'], 'owner': item.get('owner'),
                **({'origin':'manual'} if item.get('origin')=='manual' else {})})
    # Interpretation feedback is reusable evidence about a prior correction.
    # Later manual status updates describe reality and must not train interpretation.
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='human_decisions'").fetchone():
        for decision in db.execute('SELECT * FROM human_decisions WHERE event_date<=? ORDER BY command_id',(cutoff,)):
            value=json.loads(decision['data_json'])
            if value.get('action') not in ('approve','reject','correct','confirm_knowledge','correct_confirm'):continue
            if value.get('feedback_kind')=='real_world_change':continue
            if value.get('action')=='correct' and value.get('feedback_kind')!='interpretation':continue
            original=db.execute('SELECT * FROM observations WHERE id=?',(decision['observation_id'],)).fetchone()
            if original is None:continue
            before=json.loads(original['data_json'])
            text=encode({'original_interpretation':{k:before.get(k) for k in ('title','claim','kind','owner','due_text','update','quotes')},
                         'user_action':value['action'],'user_patch':value.get('patch',{}),'reason':value['reason']})
            add('feedback',decision['command_id'],'human:'+decision['actor_id'],decision['command_id'],decision['event_date'],None,text,
                {'observation_id':decision['observation_id'],'matter_id':original['matter_id'],'feedback_kind':'interpretation'})
    if archive_path:
        archive = archive_connect(archive_path, readonly=True)
        try:
            _, known_at = bounds(cutoff, meeting.get('observed_at'))
            rows = archive.execute('SELECT d.id,d.source_id,d.body_hash,d.event_date,d.observed_at,d.title,p.start,p.end,p.text FROM passages p JOIN documents d ON d.id=p.document_id WHERE '+LATEST,
                                   (cutoff, known_at, known_at)).fetchall()
            for row in rows:
                add('passage', row['id'], row['source_id'], row['body_hash'], row['event_date'], row['observed_at'],
                    row['text'], {'start': row['start'], 'end': row['end'], 'title': row['title']})
            # Imported notes are navigation aids, never independent evidence.
            if archive.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='archived_notes'").fetchone():
                active_available=bool(archive.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='active_source_notes'").fetchone())
                active=archive.execute('SELECT * FROM active_source_notes').fetchall() if active_available else []
                active_documents={row['document_id'] for row in active}
                archived=archive.execute('SELECT * FROM archived_notes ORDER BY registered_revision DESC').fetchall()
                for row in [*active,*(r for r in archived if r['origin']!='source_summary' or r['document_id'] not in active_documents)]:
                    note = dict(row)
                    parent = archive.execute('SELECT id,source_id,body_hash,event_date,observed_at FROM documents WHERE id=?', (note.get('document_id'),)).fetchone()
                    if not parent or parent['event_date'] > cutoff or parent['observed_at'] > known_at: continue
                    payload = json.loads(note.get('note_json') or '{}')
                    record = payload.get('legacy_record', payload)
                    data = record.get('payload', record)
                    texts = [data.get('ai_summary', ''), data.get('executive_summary', '')]
                    texts += [t.get('summary','') for t in data.get('topics',[]) if isinstance(t,dict)]
                    for index, text in enumerate(texts):
                        add('summary', note['id'], parent['source_id'], parent['body_hash'], parent['event_date'],
                            parent['observed_at'], text, {'document_id': parent['id'], 'summary_part': index})
        finally: archive.close()
    return sorted(result.values(), key=lambda row: row['id'])

def vectors(response, count):
    if response.get('stop_reason') != 'end_turn':
        raise ValidationError('Embedding provider did not complete; search unavailable')
    values = response.get('embeddings')
    if not isinstance(values, list) or len(values) != count:
        raise ValidationError('Embedding coverage mismatch')
    for vector in values:
        if not isinstance(vector, list) or len(vector) != DIMENSIONS or any(type(x) not in (int,float) or not math.isfinite(x) for x in vector):
            raise ValidationError('Invalid embedding vector')
        if sum(x*x for x in vector) == 0: raise ValidationError('Empty embedding vector')
    return values

class SearchIndex:
    def __init__(self, store, api):
        assert_embedding_cache_profile()
        self.store, self.api = store, api
        self.snapshot_id = None
        self.document_count = 0
        self.query_cache = {}

    def prepare(self, db, meeting, archive_path=''):
        rows = documents(db, meeting, archive_path)
        ids = [r['id'] for r in rows]
        self.persist(rows)
        self.snapshot_id = digest(','.join(ids))
        receipt = self.store.call('search_snapshot', search_snapshot_id=self.snapshot_id, document_ids=ids)
        if receipt.get('count') != len(ids): raise ValidationError('Search snapshot coverage mismatch')
        self.document_count = len(rows)
        return {'snapshot_id': self.snapshot_id, 'documents': len(rows), 'method': SEARCH_METHOD, 'embedding_model': MODEL}

    def persist(self, rows):
        by_id={r['id']:r for r in rows};ids=sorted(by_id);missing_ids=[]
        for start in range(0,len(ids),1024):
            batch=ids[start:start+1024]
            missing=self.store.call('search_missing',document_ids=batch)
            if not isinstance(missing,list) or set(missing)-set(batch):raise ValidationError('Invalid search coverage receipt')
            missing_ids.extend(missing)
        todo=[by_id[i] for i in sorted(set(missing_ids))]
        for start in range(0,len(todo),32):
            batch=todo[start:start+32]
            cached=self.store.call('search_cached',content_hashes=list(dict.fromkeys(r['content_hash'] for r in batch)))
            fresh=list({r['content_hash']:r for r in batch if r['content_hash'] not in cached}.values())
            if fresh:
                response=self.api(encode([r['text'] for r in fresh]),MODEL,max_tokens=1,schema=EMBED_SCHEMA)
                cached.update({r['content_hash']:v for r,v in zip(fresh,vectors(response,len(fresh)))})
            embedded=[cached[r['content_hash']] for r in batch]
            vectors({'stop_reason':'end_turn','embeddings':embedded},len(batch))
            values=[{**r,'embedding':v} for r,v in zip(batch,embedded)]
            # Keep HNSW writes bounded, but avoid one gateway round-trip per
            # vector when a cold archive is materialized for its first query.
            # The reviewed RPC accepts at most 32; eight leaves ample timeout
            # headroom while cutting the dominant network overhead.
            chunks=[];chunk=[]
            for value in values:
                candidate=chunk+[value]
                if chunk and (len(candidate)>SEARCH_PUT_ITEMS or len(encode(candidate).encode())>SEARCH_PUT_BYTES):
                    chunks.append(chunk);chunk=[value]
                else:chunk=candidate
                if len(encode(chunk).encode())>SEARCH_PUT_BYTES:
                    raise ValidationError('Search document exceeds the bounded gateway payload')
            if chunk:chunks.append(chunk)
            for chunk in chunks:
                receipt=self.store.call('search_put',documents=chunk)
                if receipt.get('saved')!=len(chunk):raise ValidationError('Search persistence incomplete')

    def search(self, text, kinds, limit=20):
        if self.snapshot_id is None: raise ValidationError('Search index has not been prepared')
        if not self.document_count: return []
        if not isinstance(text,str) or not text.strip(): raise ValidationError('Empty search query')
        if len(text.encode()) > 7500: raise ValidationError('Search query exceeds reviewed size')
        if text not in self.query_cache:
            self.query_cache[text] = vectors(self.api(encode([text]), MODEL, max_tokens=1, schema=EMBED_SCHEMA),1)[0]
        return self.store.call('search_query', search_snapshot_id=self.snapshot_id, query_text=text,
                               query_embedding=self.query_cache[text], kinds=kinds, match_count=limit)

def queries(raw, originals):
    result = []
    for item in raw.get('search_queries',[]):
        ids = item.get('evidence_ids',[])
        if not ids or any(i not in originals for i in ids) or not item.get('text','').strip():
            raise ValidationError('Search topic lacks current original evidence')
        result.append(item['text'])
    for item in raw['observations']:
        keywords = item.get('search_keywords',[])
        if len(keywords)>8 or any(not isinstance(k,str) or not k.strip() for k in keywords):
            raise ValidationError('Invalid search keywords')
        result.append(' '.join([item['title'], item.get('subject',''), *keywords]))
    return list(dict.fromkeys(result))


def current_source_documents(meeting, raw):
    rows=[]
    source=meeting['source_id'];version=digest(meeting['raw_transcript'])
    texts=[('passage',meeting['raw_transcript'])]
    texts += [('summary',p['text']) for p in raw['meeting_summary']]
    for ordinal,(kind,text) in enumerate(texts):
        for start,body in parts(text):
            row={'kind':kind,'target_id':digest(source+':'+version),'source_id':source,'source_version':version,
                 'event_date':meeting['meeting_date'][:10],'observed_at':meeting.get('observed_at'),
                 'text':body,'content_hash':digest(body),'embedding_model':MODEL,
                 'metadata':{'title':meeting['title'],'ordinal':ordinal,'start':start,'end':start+len(body)}}
            row['id']=digest(VERSION+':'+encode(row));rows.append(row)
    return rows
