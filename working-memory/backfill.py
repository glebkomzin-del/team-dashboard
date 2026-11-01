"""Frozen chronological archive generation. No Supabase writes or publication.

Plan registers every source before any model call. Execution is opt-in, bounded,
resumable and stops at the first failed meeting so later context is not incomplete.
"""
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import archive_index
import processor
from call_budget import CallBudget
from memory import connect, register


def prepare(archive_path, output_path, model):
    archive = archive_index.connect(archive_path, readonly=True)
    try:
        as_of, known_at = archive_index.bounds()
        rows = archive.execute('SELECT d.* FROM documents d WHERE ' + archive_index.LATEST
                               + ' ORDER BY d.event_date,d.source_id,d.id',
                               (as_of, known_at, known_at)).fetchall()
        meetings = []
        for row in rows:
            if hashlib.sha256(row['body'].encode()).hexdigest() != row['body_hash']:
                raise ValueError('Archive body hash mismatch')
            meetings.append({'id': row['id'], 'source_id': row['source_id'],
                             'meeting_date': row['event_date'], 'observed_at': row['observed_at'],
                             'title': row['title'], 'raw_transcript': row['body'],
                             'body_hash': row['body_hash']})
    finally:
        archive.close()
    pipeline = processor.pipeline_version(model)
    inventory = [{key: m[key] for key in ('id', 'source_id', 'meeting_date', 'body_hash')} for m in meetings]
    frozen = {'pipeline': pipeline, 'model': model, 'inventory': inventory}
    fingerprint = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    db = connect(output)
    output.chmod(0o600)
    db.execute('CREATE TABLE IF NOT EXISTS generation (id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL, manifest_json TEXT NOT NULL)')
    receipt=None
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='replay_receipt' AND type='table'").fetchone():
        receipt=json.loads(db.execute('SELECT receipt_json FROM replay_receipt WHERE id=1').fetchone()[0])
        frozen['replay_seed']=receipt
        fingerprint=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()
    previous = db.execute('SELECT fingerprint FROM generation WHERE id=1').fetchone()
    if previous and previous[0] != fingerprint:
        db.close()
        raise ValueError('Archive or pipeline changed; create a new isolated generation')
    if not previous:
        if db.execute('SELECT count(*) FROM jobs').fetchone()[0]:
            source_set={(m['source_id'],m['body_hash']) for m in meetings}
            seeded={(row[0],row[1]) for row in db.execute('SELECT source_id,content_hash FROM source_versions')}
            rules_hash=hashlib.sha256((processor.ROOT/'memory.py').read_bytes()+(processor.ROOT/'temporal_guard.py').read_bytes()).hexdigest()
            if not receipt or receipt.get('method')!='saved_observations_with_identity_and_temporal_guards' or receipt.get('rules_sha256')!=rules_hash or not seeded.issubset(source_set) or db.execute("SELECT 1 FROM jobs WHERE status!='applied' LIMIT 1").fetchone():
                db.close()
                raise ValueError('Refuse to adopt an unrelated or unverified replay database')
        db.execute('INSERT INTO generation VALUES (1,?,?)', (fingerprint, json.dumps(frozen)))
    for meeting in meetings:
        meeting['job_id'] = register(db, source_id=meeting['source_id'], event_date=meeting['meeting_date'],
                                     title=meeting['title'], transcript=meeting['raw_transcript'], pipeline=pipeline)
    summary = {'generation': fingerprint, 'pipeline': pipeline, 'sources': len(meetings),
               'characters': sum(len(m['raw_transcript']) for m in meetings),
               'first_date': meetings[0]['meeting_date'] if meetings else None,
               'last_date': meetings[-1]['meeting_date'] if meetings else None,
               'jobs': dict(db.execute('SELECT status,count(*) FROM jobs GROUP BY status').fetchall()),
               'published': False}
    return db, meetings, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', required=True)
    parser.add_argument('--db', required=True)
    parser.add_argument('--model', default='claude-opus-5')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--max-meetings', type=int, default=0)
    parser.add_argument('--budget-usd', type=float, default=0)
    args = parser.parse_args()
    if args.execute and (args.max_meetings < 1 or args.budget_usd <= 0):
        parser.error('Execution needs explicit positive --max-meetings and --budget-usd')
    if processor.PROMPT_VERSION != 'v9':
        parser.error('Set MEMORY_PROMPT_VERSION=v9 explicitly for this generation')
    os.environ['MEMORY_ARCHIVE_DB'] = str(Path(args.archive).resolve())
    db, meetings, summary = prepare(args.archive, args.db, args.model)
    print(json.dumps(summary), flush=True)
    budget = None
    original_api = processor.anthropic
    try:
        if not args.execute:
            return
        budget = CallBudget(args.db, args.budget_usd)
        schema = json.loads((processor.ROOT / 'evaluation/schema-v9.json').read_text())
        processor.anthropic = budget.wrap(original_api, schema)
        processed = 0
        for meeting in meetings:
            state = db.execute('SELECT status FROM jobs WHERE id=?', (meeting['job_id'],)).fetchone()[0]
            if state == 'applied':
                continue
            if processed == args.max_meetings:
                break
            result = processor.process(db, meeting, args.model)
            processed += 1
            print(json.dumps({'source_id': meeting['source_id'], 'date': meeting['meeting_date'],
                              **result, 'budget_accounted_usd': round(budget.total(), 6)}), flush=True)
    finally:
        processor.anthropic = original_api
        if budget:
            budget.close()
        db.close()


if __name__ == '__main__':
    main()
