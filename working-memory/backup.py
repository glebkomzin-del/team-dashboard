"""Consistent SQLite online backup and independent integrity/row-count verification."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

def backup(source,target):
    source=Path(source);target=Path(target)
    if target.exists():raise ValueError('Backup target already exists')
    target.parent.mkdir(parents=True,exist_ok=True)
    original=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
    copy=sqlite3.connect(target)
    try:original.backup(copy)
    finally:copy.close();original.close()
    target.chmod(0o600)
    restored=sqlite3.connect(target.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        check=restored.execute('PRAGMA integrity_check').fetchone()[0]
        if check!='ok':raise RuntimeError('Backup integrity check failed')
        counts={table:restored.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('source_versions','jobs','observations','work_events','runs')}
    finally:restored.close()
    manifest={'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'integrity_check':check,'counts':counts}
    target.with_suffix(target.suffix+'.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');a=p.parse_args();print(json.dumps(backup(a.source,a.target)))
