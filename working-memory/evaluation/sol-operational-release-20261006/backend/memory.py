"""Isolated working-memory prototype. SQLite holds immutable evidence and an event log.

No production connections. Python 3.11+. Model proposals are untrusted input.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

VERSION = 'working-memory-v1'
KINDS = {'commitment', 'dependency', 'fact', 'decision', 'question', 'risk', 'idea', 'status'}

class ValidationError(ValueError): pass
class BusyError(RuntimeError): pass
class ReplayRequired(RuntimeError): pass

def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()

def connect(path):
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS source_versions (
      id TEXT PRIMARY KEY, source_id TEXT NOT NULL, content_hash TEXT NOT NULL,
      event_date TEXT NOT NULL, observed_at REAL NOT NULL, title TEXT NOT NULL,
      transcript TEXT NOT NULL, UNIQUE(source_id, content_hash));
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, source_version TEXT NOT NULL REFERENCES source_versions(id),
      pipeline TEXT NOT NULL, status TEXT NOT NULL, lease_token TEXT, lease_until REAL,
      attempts INTEGER NOT NULL DEFAULT 0, error TEXT, UNIQUE(source_version,pipeline));
    CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), created_at REAL NOT NULL,
      model TEXT NOT NULL, usage_json TEXT NOT NULL, elapsed_seconds REAL NOT NULL,
      outcome TEXT NOT NULL, proposal_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS matters (id TEXT PRIMARY KEY, title TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS observations (
      id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
      source_version TEXT NOT NULL REFERENCES source_versions(id),
      matter_id TEXT NOT NULL REFERENCES matters(id), event_date TEXT NOT NULL,
      kind TEXT NOT NULL, data_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS work_events (
      id TEXT PRIMARY KEY, work_id TEXT NOT NULL, observation_id TEXT NOT NULL REFERENCES observations(id),
      event_date TEXT NOT NULL, action TEXT NOT NULL, data_json TEXT NOT NULL);
    ''')
    from human_decisions import setup
    setup(db)
    from matter_links import setup as setup_links
    setup_links(db)
    return db

def register(db, *, source_id, event_date, title, transcript, pipeline=VERSION):
    if not source_id or not transcript.strip(): raise ValidationError('Missing source identity or transcript')
    from datetime import date
    date.fromisoformat(event_date)
    digest = fingerprint(transcript)
    sid = fingerprint(source_id + ':' + digest)
    jid = fingerprint(sid + ':' + pipeline)
    db.execute('BEGIN IMMEDIATE')
    try:
        existing = db.execute('SELECT event_date,title FROM source_versions WHERE id=?',(sid,)).fetchone()
        if existing and (existing['event_date'] != event_date or existing['title'] != title):
            raise ReplayRequired('Source metadata changed: explicit new version/replay required')
        db.execute('INSERT OR IGNORE INTO source_versions VALUES (?,?,?,?,?,?,?)',
                   (sid, source_id, digest, event_date, time.time(), title, transcript))
        completed=db.execute("SELECT id FROM jobs WHERE source_version=? AND status='applied' LIMIT 1",(sid,)).fetchone()
        if completed:
            # A code/model upgrade must not replay already imported content implicitly.
            # Explicit reprocessing builds a separate projection generation.
            jid=completed['id']
        else:
            db.execute("INSERT OR IGNORE INTO jobs(id,source_version,pipeline,status) VALUES (?,?,?,'queued')", (jid,sid,pipeline))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK'); raise
    return jid

def claim(db, job_id, *, now=None, seconds=300):
    now = time.time() if now is None else now
    token = str(uuid.uuid4())
    db.execute('BEGIN IMMEDIATE')
    try:
        job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not job: raise ValidationError('Unknown job')
        if job['status'] == 'applied':
            db.execute('COMMIT'); return None
        if job['status'] == 'leased' and job['lease_until'] > now: raise BusyError('Job leased')
        db.execute("UPDATE jobs SET status='leased',lease_token=?,lease_until=?,attempts=attempts+1,error=NULL WHERE id=?",(token, now+seconds, job_id))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK'); raise
    return token

def context(db, event_date):
    # Explicit as-of predicate. Historical replays cannot see later observations.
    rows = db.execute('''SELECT o.*,m.title AS matter_title FROM observations o
                         JOIN matters m ON m.id=o.matter_id WHERE event_date<=? ORDER BY event_date,o.id''',(event_date,)).fetchall()
    from matter_links import project_context
    return project_context(db,[{**dict(r), 'data': json.loads(r['data_json'])} for r in rows],event_date)

def known_work_ids(db, as_of='9999-12-31'):
    ids={r[0] for r in db.execute('SELECT DISTINCT work_id FROM work_events WHERE event_date<=?',(as_of,))}
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='human_decisions'").fetchone():
        for row in db.execute('SELECT work_id,data_json FROM human_decisions WHERE event_date<=?',(as_of,)):
            if json.loads(row['data_json'])['action'] in ('approve','correct_confirm') and row['work_id']:ids.add(row['work_id'])
    from planner import state as planning_state
    ids.update(planning_state(db,as_of)['tasks'])
    return ids

def validate(proposal, transcript, existing_work):
    if not isinstance(proposal, dict) or set(proposal) != {'observations','coverage_notes'}:
        raise ValidationError('Invalid proposal envelope')
    if not isinstance(proposal['observations'],list) or not isinstance(proposal['coverage_notes'],list):
        raise ValidationError('Invalid proposal arrays')
    result = []
    for original in proposal['observations']:
        if not isinstance(original,dict): raise ValidationError('Invalid observation')
        o = dict(original)
        if o.get('kind') not in KINDS or not all(isinstance(o.get(k),str) and o[k].strip() for k in ('title','claim','matter')):
            raise ValidationError('Missing or invalid observation fields')
        for key in ('owner','uncertainty','action_uncertainty','condition_text','matter_id','update_target'):
            if o.get(key) is not None and not isinstance(o[key],str): raise ValidationError('Invalid ' + key)
        if o.get('update') not in ('none','progress','done','reopened','owner_changed','date_changed','condition_met'):
            raise ValidationError('Invalid update')
        if not isinstance(o.get('required_review'),bool): raise ValidationError('Invalid review flag')
        if not isinstance(o.get('quotes'),list) or not o['quotes']:
            raise ValidationError('Every observation needs original evidence')
        spans = []
        for quote in o['quotes']:
            if not isinstance(quote,str) or not quote.strip() or quote not in transcript:
                raise ValidationError('Quote not found verbatim in source: ' + repr(quote)[:100])
            start = transcript.index(quote)
            spans.append({'start':start,'end':start+len(quote),'quote':quote})
        if 'source_spans' in o:
            selected=o['source_spans']
            if not isinstance(selected,list) or not selected or any(
                not isinstance(s,dict) or type(s.get('start')) is not int or type(s.get('end')) is not int
                or not 0<=s['start']<s['end']<=len(transcript)
                or transcript[s['start']:s['end']]!=s.get('quote') for s in selected):
                raise ValidationError('Invalid selected original span')
            if set(s['quote'] for s in selected)!=set(o['quotes']):raise ValidationError('Selected evidence coverage mismatch')
            spans=selected
        if o.get('due_text') is not None and (not isinstance(o['due_text'],str) or not any(o['due_text'] in q for q in o['quotes'])):
            raise ValidationError('Due expression lacks quoted evidence')
        if o.get('condition_text') and any(not any(part in q for q in o['quotes']) for part in o['condition_text'].splitlines() if part.strip()):
            raise ValidationError('Condition lacks quoted evidence')
        if o.get('work_state','open') not in ('not_applicable','open','waiting','done'):
            raise ValidationError('Invalid work state')
        if o.get('work_state')=='done' and (not o.get('state_quotes') or any(q not in o['quotes'] for q in o['state_quotes'])):
            raise ValidationError('Completed work needs original state evidence')
        if o.get('update')=='condition_met':
            if not o.get('update_target') or o.get('work_state')!='open' or o.get('condition_text'):
                raise ValidationError('Condition resolution needs an existing task, open state and no new condition')
            if not o.get('state_quotes') or any(q not in o['quotes'] for q in o['state_quotes']):
                raise ValidationError('Condition resolution needs original state evidence')
        if o.get('update') == 'owner_changed' and not o.get('owner'):
            raise ValidationError('Owner change requires an identified new owner')
        if o.get('update') == 'date_changed' and not o.get('due_text'):
            raise ValidationError('Date change requires a quoted new due expression')
        if o.get('update_target') and o['update_target'] not in existing_work:
            raise ValidationError('Unknown work target')
        if o.get('update','none') != 'none' and not o.get('update_target'):
            # Preserve a status report as knowledge; it cannot close an unidentified task.
            o['unapplied_update'] = o['update']
            o['update'] = 'none'
        if (o['kind'] == 'commitment' or o.get('update','none') != 'none') and re.fullmatch(r'(?:Speaker|Sprecher|Unknown Speaker|Unknown|Unbekannt)\s*\d*', o.get('owner') or '', re.I):
            o['unresolved_speaker_label'] = o['owner']
            o['prior_identity_action_uncertainty'] = o.get('action_uncertainty', o.get('uncertainty'))
            o['action_uncertainty'] = 'Die Person hinter der anonymen Sprecherbezeichnung ist in dieser Quelle nicht verlässlich identifiziert.'
            o['required_review'] = True
        o['spans'] = spans
        o['creates_work'] = (o['kind'] == 'commitment' and o.get('commitment_strength') in ('explicit','accepted_request')
            and bool(o.get('owner')) and not o.get('action_uncertainty',o.get('uncertainty')) and not o.get('update_target')
            and not o['required_review']
            and o.get('work_gate',{}).get('verdict','supported') in ('supported','already_done'))
        result.append(o)
    return result

def apply(db, job_id, token, proposal, *, model, usage=None, elapsed=0, now=None, run_id=None, human_guard='field-v1'):
    now = time.time() if now is None else now
    # Runs remain auditable even when proposal validation fails; actual retry spend is retained.
    if run_id is None:
        run_id=str(uuid.uuid4())
        db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
            (run_id,job_id,now,model,json.dumps(usage or {}),elapsed,'received',json.dumps(proposal,ensure_ascii=False)))
    else:
        row=db.execute('SELECT job_id FROM runs WHERE id=?',(run_id,)).fetchone()
        if not row or row[0]!=job_id:raise ValidationError('Invalid run reference')
        db.execute('UPDATE runs SET proposal_json=? WHERE id=?',(json.dumps(proposal,ensure_ascii=False),run_id))
    db.execute('BEGIN IMMEDIATE')
    try:
        job = db.execute('SELECT j.*,s.transcript,s.event_date,s.source_id FROM jobs j JOIN source_versions s ON s.id=j.source_version WHERE j.id=?',(job_id,)).fetchone()
        if not job or job['status'] != 'leased' or job['lease_token'] != token or job['lease_until'] <= now:
            raise BusyError('Lease expired or replaced')
        # Changed versions and out-of-order imports require an isolated rebuild before replacing projections.
        if db.execute('SELECT 1 FROM observations o JOIN source_versions s ON s.id=o.source_version WHERE s.source_id=? AND o.job_id<>? LIMIT 1',(job['source_id'],job_id)).fetchone():
            raise ReplayRequired('Changed source version: rebuild affected projection')
        if db.execute('SELECT 1 FROM observations WHERE event_date>? LIMIT 1',(job['event_date'],)).fetchone():
            raise ReplayRequired('Out-of-order source: replay chronologically')
        work = known_work_ids(db,job['event_date'])
        from corrections import correct_proposal
        corrected = correct_proposal(proposal, job['transcript'])
        from human_decisions import guard_updates
        corrected = guard_updates(db, corrected,mode=human_guard)
        items = validate(corrected, job['transcript'], work)
        known_matters = {r['id']:r['title'] for r in db.execute('SELECT id,title FROM matters')}
        new_matters = {}
        for index, o in enumerate(items):
            if o.get('update')=='condition_met':
                state=overview(db,job['event_date'])
                target=next((w for group in ('personal','waiting_dependencies','waiting') for w in state[group] if w['id']==o['update_target']),None)
                if not target or target['status'] not in ('open','waiting') or not target.get('condition_text'):
                    raise ValidationError('Condition resolution requires an active task with a recorded condition')
            mid = o.get('matter_id')
            if mid and mid not in known_matters:
                exact=[identifier for identifier,title in known_matters.items() if title==o['matter']]
                if len(exact)!=1:raise ValidationError('Unknown matter ID')
                mid=exact[0];o['matter_id']=mid
            if o.get('update_target'):
                target_row = db.execute('SELECT o.matter_id FROM work_events e JOIN observations o ON o.id=e.observation_id WHERE e.work_id=? ORDER BY e.rowid LIMIT 1',(o['update_target'],)).fetchone()
                if not target_row:
                    target_row=db.execute('SELECT matter_id FROM observations WHERE id=?',(o['update_target'],)).fetchone()
                if target_row:
                    target_matter = target_row[0]
                else:
                    from planner import state as planning_state
                    if o['update_target'] not in planning_state(db,job['event_date'])['tasks']:
                        raise ValidationError('Unknown work target')
                    target_matter=fingerprint('manual-planning:matter')
                    db.execute('INSERT OR IGNORE INTO matters VALUES (?,?)',(target_matter,'Eigene Planung'))
                from matter_links import aliases,resolve
                links=aliases(db,job['event_date'])
                if mid and resolve(mid,links) != resolve(target_matter,links): raise ValidationError('Work update belongs to a different matter')
                mid = target_matter
            if not mid:
                # Only coalesce exact matter labels inside this one meeting, never across projects implicitly.
                mid = new_matters.setdefault(o['matter'], fingerprint(job_id + ':matter:' + o['matter']))
                db.execute('INSERT OR IGNORE INTO matters VALUES (?,?)',(mid,o['matter']))
            oid = fingerprint(job_id + ':observation:' + str(index))
            data = json.dumps(o,ensure_ascii=False)
            db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?)',(oid,job_id,job['source_version'],mid,job['event_date'],o['kind'],data))
            action = 'created' if o['creates_work'] else o.get('update','none')
            # Ambiguous change proposals remain knowledge; they cannot mutate an existing task.
            if o.get('required_review') or o.get('action_uncertainty',o.get('uncertainty')): action = 'none'
            if o.get('work_gate',{}).get('verdict','supported') not in ('supported','already_done'):action='none'
            if action != 'none':
                wid = o.get('update_target') or oid
                db.execute('INSERT INTO work_events VALUES (?,?,?,?,?,?)',(fingerprint(oid+action),wid,oid,job['event_date'],action,data))
        from projection_order import record as record_order
        record_order(db,'source',job['source_version'])
        db.execute("UPDATE jobs SET status='applied',lease_token=NULL,lease_until=NULL WHERE id=?",(job_id,))
        db.execute("UPDATE runs SET outcome='applied' WHERE id=?",(run_id,))
        db.execute('COMMIT')
        return items
    except Exception:
        db.execute('ROLLBACK')
        db.execute("UPDATE runs SET outcome='rejected' WHERE id=?",(run_id,))
        raise

def record_failure(db, job_id, token, error):
    # Stale workers cannot release another worker's lease.
    db.execute("UPDATE jobs SET status='failed',error=?,lease_token=NULL,lease_until=NULL WHERE id=? AND lease_token=?",(str(error)[:500],job_id,token))

def overview(db, as_of='9999-12-31'):
    events = db.execute("""SELECT e.*,s.title AS source_title,s.source_id,s.content_hash,o.source_version
        FROM work_events e JOIN observations o ON o.id=e.observation_id
        JOIN source_versions s ON s.id=o.source_version WHERE e.event_date<=? ORDER BY e.event_date,e.rowid""",(as_of,)).fetchall()
    work = {}
    for row in events:
        item = json.loads(row['data_json']); action=row['action']
        prior = work.get(row['work_id'])
        evidence={'event_date':row['event_date'],'action':action,'source_title':row['source_title'],
                  'source_id':row['source_id'],'source_version':row['source_version'],'content_hash':row['content_hash'],
                  'claim':item['claim'],'quotes':item['quotes'],'owner':item.get('owner'),'due_text':item.get('due_text')}
        if prior is None:
            current={**item,'id':row['work_id'],'title':item['title'],'history':[],
                     'status':item.get('work_state') if item.get('work_state') in ('waiting','done') else 'open',
                     'due_reference_date':row['event_date'] if item.get('due_text') else None}
        else:
            current={**prior, 'claim':item['claim'],'quotes':item['quotes']}
            # Status reports are not patches to every nullable field in the schema.
            if action=='owner_changed':current['owner']=item['owner']
            if action=='date_changed':
                current['due_text']=item['due_text'];current['due_reference_date']=row['event_date']
            if action=='done':current['status']='done'
            elif action=='reopened':current['status']='waiting' if item.get('work_state')=='waiting' else 'open'
            elif action=='progress' and current['status']!='done' and item.get('work_state') in ('open','waiting'):
                current['status']=item['work_state']
            elif action=='condition_met' and current['status']!='done':
                evidence['resolved_condition_text']=current.get('condition_text')
                current['condition_text']=None
                current['status']='open'
            for field in ('work_gate','human_corrections','uncertainty','action_uncertainty','resolution_basis'):
                current.pop(field,None)
                if field in item:current[field]=item[field]
        for field in ('assignment_score','change_score','confidence_reason','subject','search_keywords'):
            if field in item:current[field]=item[field]
        current['last_changed']=row['event_date']
        current['history']=[*current['history'],evidence]
        work[row['work_id']]=current
    knowledge = context(db,as_of)
    def personal(item):
        name=re.sub(r'[^a-z]+',' ',(item.get('owner') or '').lower()).strip()
        return name in ('gleb','gleb komzin','komzin gleb')
    state = {'as_of':as_of,'personal':[x for x in work.values() if personal(x) and x['status']=='open'],
        'waiting_dependencies':[x for x in work.values() if personal(x) and x['status']=='waiting'],
        'waiting':[x for x in work.values() if not personal(x) and x['status']!='done'],
        'knowledge':knowledge,'completed':[x for x in work.values() if x['status']=='done']}
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='human_decisions'").fetchone():
        from human_decisions import project
        state = project(db,state,as_of)
    topics={row['id']:row for row in knowledge}
    for group in ('personal','waiting_dependencies','waiting','completed','cancelled'):
        for item in state.get(group,[]):
            topic=topics.get(item['id'])
            if topic:
                item['matter_id']=topic['matter_id'];item['matter']=topic['matter_title']
    return state
