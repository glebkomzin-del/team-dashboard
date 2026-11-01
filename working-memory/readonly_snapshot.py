"""Prepare a consistent SQLite snapshot for a genuinely read-only container mount."""
import hashlib,json,os,sqlite3
from pathlib import Path

def create(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Snapshot destination already exists')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    original=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    copy=sqlite3.connect(destination)
    try:
        original.backup(copy)
        # WAL headers otherwise cause readers to create sidecars on the read-only mount.
        if copy.execute('PRAGMA journal_mode=DELETE').fetchone()[0]!='delete':raise ValueError('Cannot detach WAL')
        if copy.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Snapshot integrity failed')
    finally:copy.close();original.close()
    destination.chmod(0o600)
    return {'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'bytes':destination.stat().st_size,'journal_mode':'delete','integrity':'ok'}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');a=p.parse_args();print(json.dumps(create(a.source,a.destination)))
