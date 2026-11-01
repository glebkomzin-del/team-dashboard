"""Read-only API for real projection data; no worker or model calls.

Uses the existing private Bearer boundary. Browser access is mediated by a local
Vite development proxy, never by placing a service credential in frontend code.
"""
from datetime import date
import json
from pathlib import Path
import sqlite3
from memory import overview

def open_readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db

def review(db, as_of=None):
    dates = [r[0] for r in db.execute("SELECT DISTINCT s.event_date FROM source_versions s JOIN jobs j ON j.source_version=s.id WHERE j.status='applied' ORDER BY s.event_date")]
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='human_decisions'").fetchone():
        dates = sorted(set(dates) | {r[0] for r in db.execute('SELECT DISTINCT event_date FROM human_decisions')})
    from planner import events as planning_events, overlay
    dates = sorted(set(dates) | {e["event_date"] for e in planning_events(db)})
    selected = as_of or (dates[-1] if dates else date.today().isoformat())
    date.fromisoformat(selected)
    state = overview(db, selected)
    sources = [dict(r) for r in db.execute("SELECT DISTINCT s.id,s.source_id,s.content_hash,s.event_date,s.title FROM source_versions s JOIN jobs j ON j.source_version=s.id WHERE s.event_date<=? AND j.status='applied' ORDER BY s.event_date,s.observed_at", (selected,))]
    jobs = [dict(r) for r in db.execute("SELECT j.id,j.status,j.attempts,j.error,s.title,s.event_date FROM jobs j JOIN source_versions s ON s.id=j.source_version WHERE s.event_date<=? ORDER BY s.event_date", (selected,))]
    changes = [dict(r) for r in db.execute("SELECT e.id,e.work_id,e.event_date,e.action,o.matter_id,m.title AS matter_title,e.data_json FROM work_events e JOIN observations o ON o.id=e.observation_id JOIN matters m ON m.id=o.matter_id WHERE e.event_date=? ORDER BY e.rowid", (selected,))]
    for change in changes:
        change['data'] = json.loads(change.pop('data_json'))
    for decision in state.get('human_decisions',[]):
        if decision['event_date']!=selected:continue
        origin=db.execute('SELECT o.data_json,o.matter_id,m.title FROM observations o JOIN matters m ON m.id=o.matter_id WHERE o.id=?',
                          (decision['observation_id'],)).fetchone()
        data=json.loads(origin['data_json'])
        data.update(claim=decision['reason'],human_decision=decision)
        if decision['patch'].get('title'):data['title']=decision['patch']['title']
        changes.append({'id':decision['command_id'],'work_id':decision['work_id'],'event_date':selected,
                        'action':decision['action'],'matter_id':origin['matter_id'],'matter_title':origin['title'],'data':data})
    state = overlay(db, state, selected)
    return {'mode': 'isolated-preview', 'dates': dates, 'sources': sources, 'jobs': jobs, 'changes': changes, **state}
