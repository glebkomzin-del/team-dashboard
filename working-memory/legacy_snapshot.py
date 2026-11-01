"""Retain the entire legacy snapshot and map only defensible source identities.

This imports into a new local database. It never changes Supabase and never
promotes an old AI suggestion to a new commitment.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from archive_index import connect as archive_connect

TABLES = ('meetings', 'todos', 'blockers', 'open_items', 'inbox_items')

def build(snapshot_path, archive_path, destination):
    destination = Path(destination)
    if destination.exists(): raise ValueError('Use a new migration database')
    payload = Path(snapshot_path).read_bytes(); snapshot = json.loads(payload)
    tables = snapshot['tables']
    if set(tables) != set(TABLES): raise ValueError('Incomplete table set')
    for name in TABLES:
        if len({r['id'] for r in tables[name]}) != len(tables[name]): raise ValueError('Duplicate legacy identity')
    for meeting in tables['meetings']:
        if hashlib.sha256((meeting['raw_transcript'] or '').encode()).hexdigest() != meeting['raw_sha256']:
            raise ValueError('Legacy changed during export; take a new snapshot')
    archive = archive_connect(archive_path, readonly=True)
    documents = [dict(row) for row in archive.execute('SELECT id,source_id,body_hash,body,event_date FROM documents')]
    archive.close()
    by_source = defaultdict(list); by_hash = defaultdict(list)
    for doc in documents:
        by_source[doc['source_id']].append(doc); by_hash[doc['body_hash']].append(doc)
    links = {}; conflicts = defaultdict(set)
    for item in tables['inbox_items']:
        mid = item['payload'].get('meeting_id')
        if mid: conflicts[mid].add(item['source'])
    for meeting in tables['meetings']:
        exact = by_hash[meeting['raw_sha256']]
        partial = [] if exact else [doc for doc in documents if meeting['raw_transcript'] and meeting['raw_transcript'] in doc['body']]
        matches = exact or partial
        links[meeting['id']] = {'status': 'exact_content' if len(exact)==1 else 'exact_partial' if len(partial)==1 else 'needs_review',
            'archive_ids': [doc['id'] for doc in matches],
            'offsets': [doc['body'].find(meeting['raw_transcript']) for doc in matches],
            'legacy_link_conflict': len(conflicts[meeting['id']]) > 1}
    temp = destination.with_suffix('.building.sqlite')
    if temp.exists(): raise ValueError('Previous incomplete snapshot exists; inspect it first')
    db = sqlite3.connect(temp);temp.chmod(0o600)
    db.executescript('''CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE legacy_records (entity_table TEXT NOT NULL,legacy_id TEXT NOT NULL,title TEXT NOT NULL,
          original_status TEXT NOT NULL,original_json TEXT NOT NULL,link_json TEXT NOT NULL,
          PRIMARY KEY(entity_table,legacy_id));''')
    counts = Counter()
    try:
        with db:
            for table in TABLES:
                for row in tables[table]:
                    if table=='meetings': link=links[row['id']]
                    elif table=='inbox_items':
                        matches=by_source['drive:'+row['source'].removeprefix('drive:')]
                        link={'status':'drive_identity' if len(matches)==1 else 'needs_review','archive_ids':[d['id'] for d in matches],
                              'legacy_link_conflict':bool(row['payload'].get('meeting_id') and len(conflicts[row['payload']['meeting_id']])>1)}
                    else: link=links.get(row.get('meeting_id'),{'status':'needs_review','archive_ids':[],'legacy_link_conflict':False})
                    counts[table+'/'+link['status']]+=1
                    title=row.get('title') or row.get('payload',{}).get('title') or 'Ohne Titel'
                    db.execute('INSERT INTO legacy_records VALUES (?,?,?,?,?,?)',(table,row['id'],title,row.get('status','retained'),json.dumps(row,ensure_ascii=False),json.dumps(link)))
            report={'snapshot_sha256':hashlib.sha256(payload).hexdigest(),'captured_at':snapshot['captured_at'],
                    'retained_counts':{k:len(tables[k]) for k in TABLES},'source_links':dict(counts),
                    'conflicting_meeting_links':sum(len(value)>1 for value in conflicts.values()),
                    'policy':'All legacy IDs and original records retained. No old AI claims imported as new work. No production mutation.'}
            db.execute('INSERT INTO metadata VALUES (?,?)',('manifest',json.dumps(report,ensure_ascii=False)))
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Integrity check failed')
        assert db.execute('SELECT count(*) FROM legacy_records').fetchone()[0]==sum(len(tables[k]) for k in TABLES)
    except Exception:
        db.close();raise
    db.close();temp.rename(destination)
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('snapshot');p.add_argument('--archive',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print(json.dumps(build(a.snapshot,a.archive,a.out),ensure_ascii=False))
