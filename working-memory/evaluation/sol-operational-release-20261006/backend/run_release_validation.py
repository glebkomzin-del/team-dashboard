"""Bounded replay of one existing source against its original pinned context.

Uses real models and shared search cache, but never publishes work or enqueues
jobs. All evaluations share a durable $8 ledger (plus $2 reserved separately for chat); unknown calls never resend.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
from canonical_archive import verify_document
from evaluation_budget import EvaluationCalls
from future_summary import INSTRUCTION
from gateway_journal import GatewayJournal
from hybrid_pipeline import process,version
from hybrid_schema import extraction_schema
from journal_projection import rebuild
from journal_service import JournalService
from memory import connect
from openai_provider import request,count_input_tokens
from review_api import open_readonly

def main(job_id):
    if not re.fullmatch('[0-9a-f]{64}',job_id):raise ValueError('Invalid source job')
    model='gpt-5.6-terra'
    root=Path('/app/.local/release-validation-20260919');root.mkdir(parents=True,exist_ok=True,mode=0o700)
    keys=Path('/app/.local/model-keys.json')
    if not os.environ.get('OPENAI_API_KEY') and keys.exists():
        os.environ['OPENAI_API_KEY']=json.loads(keys.read_text())['OPENAI_API_KEY']
    store=GatewayJournal(os.environ['SUPABASE_URL'],os.environ['SUPABASE_PUBLISHABLE_KEY'],os.environ['MEMORY_JOURNAL_TOKEN'],os.environ['MEMORY_SPACE_ID'])
    service=JournalService(store,os.environ['MEMORY_CACHE_DIR'])
    job=store.call('job_detail',job_id=job_id)['job']
    if job['state']!='applied' or not isinstance(job.get('expected_revision'),int):raise ValueError('Use a completed pinned source only')
    document=verify_document(store.call('archive_document',document_id=job['document_id']))
    meeting={'id':job_id,'source_id':document['source_id'],'title':document['title'],
      'meeting_date':document['event_date'],'observed_at':document['observed_at'],'raw_transcript':document['body']}
    pinned=root/f"context-{job['expected_revision']}.sqlite"
    if not pinned.exists():rebuild(store,pinned,through=job['expected_revision'])
    identity={'role':'owner','id':store.space()['owner_id']}
    archive_path=root/'archive.sqlite'
    if not archive_path.exists():
        with service.archive_projection(identity) as (archive,_):
            target=sqlite3.connect(archive_path)
            try:archive.backup(target)
            finally:target.close()
    pipeline=version(model,compact=True)
    run=root/(job_id[:12]+'-'+pipeline.split(':')[-1]);run.mkdir(exist_ok=True,mode=0o700)
    db=connect(run/'result.sqlite');base=open_readonly(pinned)
    try:base.backup(db)
    finally:base.close()
    calls=EvaluationCalls(root/'budget.sqlite',store,request,extraction_schema(),
      {'source':job_id,'revision':job['expected_revision'],'pipeline':pipeline},ceiling=8_000_000,token_counter=count_input_tokens)
    before=calls.total()
    try:
        result=process(db,meeting,model,api=calls,pipeline=pipeline,archive_db=str(archive_path),extra_instruction=INSTRUCTION,compact=True)
        receipt={'source_job':job_id,'context_revision':job['expected_revision'],'pipeline':pipeline,
          'transcript_characters':len(document['body']),'incremental_usd':(calls.total()-before)/1_000_000,
          'consumed_request_costs_usd':{model:cost/1_000_000 for model,cost in calls.used_costs().items()},
          'shared_evaluation_usd':calls.total()/1_000_000,'result':result,'published':False}
        (run/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    finally:db.close();calls.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('job_id');args=parser.parse_args();main(args.job_id)
