"""Controlled single-source v10 evaluation. Never publishes a journal result."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from gateway_journal import GatewayJournal
from journal_service import JournalService
from journal_projection import rebuild
from canonical_archive import verify_document
from memory import connect
from review_api import open_readonly
from hybrid_pipeline import process,version
from hybrid_schema import extraction_schema
from evaluation_budget import EvaluationCalls
from openai_provider import request
from future_summary import INSTRUCTION

ROOT=Path('/app/.local/hybrid-validation-20260908')
JOB='83681f9dc511bb9888969e88f17c6d25dc21c1b3e22a7c32aa934ce3f4c1aeaf'
def setup():
 store=GatewayJournal(os.environ['SUPABASE_URL'],os.environ['SUPABASE_PUBLISHABLE_KEY'],os.environ['MEMORY_JOURNAL_TOKEN'],os.environ['MEMORY_SPACE_ID'])
 ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
 keyfile=Path('/app/.local/model-keys.json')
 if not os.environ.get('OPENAI_API_KEY') and keyfile.exists():os.environ['OPENAI_API_KEY']=json.loads(keyfile.read_text())['OPENAI_API_KEY']
 return store

def main(model,compact=False,ceiling=10000000):
 if model not in ('gpt-5.6-terra','gpt-5.6-luna'):raise ValueError('Unreviewed model')
 store=setup();service=JournalService(store,os.environ.get('MEMORY_CACHE_DIR','.local/projections'))
 detail=store.call('job_detail',job_id=JOB)
 document=verify_document(store.call('archive_document',document_id=detail['job']['document_id']))
 if document['title']!='VS Code + Python + PBI' or document['event_date']!='2026-09-08':raise ValueError('Unapproved full test source')
 meeting={'id':JOB,'source_id':document['source_id'],'title':document['title'],'meeting_date':document['event_date'],
          'observed_at':document['observed_at'],'raw_transcript':document['body']}
 pinned=ROOT/'pinned.sqlite';archive_path=ROOT/'archive.sqlite'
 if not pinned.exists():rebuild(store,pinned,through=110)
 identity={'role':'owner','id':store.space()['owner_id']}
 if not archive_path.exists():
  with service.archive_projection(identity) as (archive,_):
   copy=sqlite3.connect(archive_path)
   try:archive.backup(copy)
   finally:copy.close()
 run=ROOT/(model+'-'+version(model,compact=compact).split(':')[-1]);run.mkdir(exist_ok=True,mode=0o700)
 db=connect(run/'result.sqlite');base=open_readonly(pinned)
 try:base.backup(db)
 finally:base.close()
 from openai_provider import count_input_tokens
 calls=EvaluationCalls(ROOT/'budget.sqlite',store,request,extraction_schema(),{'source':JOB,'revision':110,'pipeline':version(model,compact=compact)},ceiling=ceiling,token_counter=count_input_tokens if compact else None)
 try:
  result=process(db,meeting,model,api=calls,archive_db=str(archive_path),extra_instruction=INSTRUCTION,compact=compact)
  (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
  (run/'primary.json').write_text(json.dumps(calls.primary_responses[-1],ensure_ascii=False))
  print(json.dumps(result,ensure_ascii=False),flush=True)
 finally:db.close();calls.close()

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('model',choices=['gpt-5.6-terra','gpt-5.6-luna']);parser.add_argument('--compact',action='store_true')
 parser.add_argument('--ceiling-micro-usd',type=int,default=10000000)
 args=parser.parse_args();main(args.model,args.compact,args.ceiling_micro_usd)
