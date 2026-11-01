"""Explicit, dated topic links; never infer identity from a repeated label.

Links are part of a saved source batch. Original topic IDs and task identities
remain immutable. Historical views only resolve links established by that date.
"""
import json
from memory import ValidationError


def setup(db):
    db.execute('''CREATE TABLE IF NOT EXISTS matter_links (
      source_version TEXT NOT NULL REFERENCES source_versions(id),
      event_date TEXT NOT NULL, from_id TEXT NOT NULL REFERENCES matters(id),
      to_id TEXT NOT NULL REFERENCES matters(id), data_json TEXT NOT NULL,
      PRIMARY KEY(source_version,from_id))''')


def aliases(db, as_of):
    result={}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='matter_links'").fetchone():return result
    for row in db.execute('SELECT from_id,to_id FROM matter_links WHERE event_date<=? ORDER BY rowid',(as_of,)):
        result[row['from_id']]=row['to_id']
    return result


def resolve(identity, links):
    seen=set()
    while identity in links:
        if identity in seen:raise ValidationError('Cyclic matter links')
        seen.add(identity);identity=links[identity]
    return identity


def validate(db, source, links):
    if not isinstance(links,list) or not links:
        raise ValidationError('Explicit matter links required')
    known={r[0] for r in db.execute('SELECT DISTINCT matter_id FROM observations WHERE event_date<=?',(source['event_date'],))}
    current=aliases(db,source['event_date']);seen=set()
    for link in links:
        if not isinstance(link,dict) or set(link)!={'from_id','to_id','reason','quotes'}:
            raise ValidationError('Invalid matter link')
        start,end=link['from_id'],link['to_id']
        if not isinstance(start,str) or not isinstance(end,str) or start not in known or end not in known or start==end:
            raise ValidationError('Matter link requires two distinct existing identities')
        if start in seen or start in current:
            raise ValidationError('Matter identity already linked; explicit revision required')
        if not isinstance(link['reason'],str) or not link['reason'].strip():
            raise ValidationError('Matter link requires a reviewed reason')
        quotes=link['quotes']
        if not isinstance(quotes,list) or not quotes or any(not isinstance(q,str) or not q.strip() or q not in source['transcript'] for q in quotes):
            raise ValidationError('Matter link requires exact evidence from the linking source')
        seen.add(start);current[start]=end
        resolve(start,current)
    return links


def record(db, source, links):
    checked=validate(db,source,links)
    for link in checked:
        db.execute('INSERT INTO matter_links VALUES (?,?,?,?,?)',(source['id'],source['event_date'],link['from_id'],link['to_id'],json.dumps(link,ensure_ascii=False)))
    return checked


def project_context(db, rows, as_of):
    links=aliases(db,as_of)
    titles={r['id']:r['title'] for r in db.execute('SELECT id,title FROM matters')}
    result=[]
    for row in rows:
        original=row['matter_id'];identity=resolve(original,links)
        result.append({**row,'original_matter_id':original,'matter_id':identity,'matter_title':titles[identity],
                       'data':{**row['data'],'matter_id':identity,'matter':titles[identity]}})
    return result
