"""Explicit operator recovery of the single reviewed failed source, no model calls.

Prepare verifies the source, revision, accepted proposal and all search records.
Publish requires an already audited pipeline transition; canonical RPCs enforce
lease, revision and source identity. Never synthesize paid-call receipts.
"""
import json, os, sqlite3, sys
from pathlib import Path
from datetime import date,timedelta
from uuid import uuid4
from run_hybrid_validation import setup,ROOT,JOB
from canonical_archive import verify_document
from canonical_worker import pipeline_version
from journal_projection import prepare_source,rebuild,apply_saved,digest
from memory import connect
from review_api import open_readonly
from hybrid_index import SearchIndex,documents,current_source_documents
from durable_calls import atomic_private,encode,sha
from future_summary import from_response
from processor import units

OUT=ROOT/'reviewed-recovery'
def no_paid_calls(*a,**k):raise RuntimeError('Recovery may not call a paid provider')

def prepare(folder):
 store=setup();folder=Path(folder);result=json.loads((folder/'result.json').read_text())
 if result['status']!='applied':raise ValueError('Unvalidated result')
 space=store.space()
 if space['revision']!=110:raise ValueError('Reviewed context changed')
 detail=store.call('job_detail',job_id=JOB);job=detail['job']
 if job['state']!='review' or job['reason']!='validation_failed':raise ValueError('Unexpected recovery state')
 document=verify_document(store.call('archive_document',document_id=job['document_id']))
 if document['title']!='VS Code + Python + PBI' or document['event_date']!='2026-09-08':raise ValueError('Wrong source')
 model='gpt-5.6-terra';OUT.mkdir(exist_ok=True,mode=0o700)
 source={'id':JOB,'source_id':document['source_id'],'content_hash':document['body_hash'],'event_date':document['event_date'],'observed_at':document['observed_at'],'title':document['title'],'transcript':document['body']}
 saved=sqlite3.connect(folder/'result.sqlite')
 row=saved.execute("SELECT proposal_json FROM runs WHERE outcome='applied' AND job_id=?",(result['job'],)).fetchone();saved.close()
 if not row:raise ValueError('Missing accepted proposal')
 proposal=json.loads(row[0]);primary=json.loads((folder/'primary.json').read_text())
 summary=from_response(primary,units(source['transcript']),source['title'])
 rebuild(store,OUT/'base.sqlite',through=110);base=open_readonly(OUT/'base.sqlite')
 try:
  payload=prepare_source(base,source,proposal,pipeline=pipeline_version(model),model=model,
   provenance={'mode':'reviewed_hybrid_recovery','document_id':document['id'],'job_id':JOB,'context_revision':110,'validation_directory':folder.name,'validation_result_sha256':sha((folder/'result.json').read_text()),'validation_proposal_sha256':sha(row[0])},
   usage={'paid_validation_ledger':'hybrid-validation-20260908/budget.sqlite','recovery_paid_calls':0,'historical_paid_calls_preserved':len(detail['calls'])})
  note_json=encode(summary);note_hash=sha(note_json)
  payload['archive_note']={'document_id':document['id'],'origin':'source_summary','origin_id':JOB,'note_json':note_json,'note_hash':note_hash,'id':sha(':'.join([document['id'],'source_summary',JOB,note_hash]))}
  scratch=connect(OUT/'accepted.sqlite')
  try:
   base.backup(scratch);apply_saved(scratch,source,payload)
   meeting={'id':JOB,'source_id':source['source_id'],'meeting_date':source['event_date'],'observed_at':source['observed_at'],'title':source['title'],'raw_transcript':source['transcript']}
   following={**meeting,'meeting_date':(date.fromisoformat(source['event_date'])+timedelta(days=1)).isoformat()}
   raw=json.loads(''.join(c.get('text','') for c in primary['content'] if c.get('type')=='text'))
   SearchIndex(store,no_paid_calls).persist(documents(scratch,following,str(ROOT/'archive.sqlite'))+current_source_documents(meeting,raw))
  finally:scratch.close()
 finally:base.close()
 atomic_private(OUT/'payload.json',payload);atomic_private(OUT/'source.json',source)
 receipt={'pipeline':payload['pipeline'],'source_hash':source['content_hash'],'payload_hash':digest(payload),'result_hash':payload['result_sha256'],'context_revision':110,'job_id':JOB,'previous_call_count':len(detail['calls']),'command_id':str(uuid4())}
 atomic_private(OUT/'receipt.json',receipt);print(encode(receipt),flush=True)

def publish():
 store=setup();receipt=json.loads((OUT/'receipt.json').read_text());payload=json.loads((OUT/'payload.json').read_text())
 if digest(payload)!=receipt['payload_hash']:raise ValueError('Prepared artifact changed')
 if store.space()['revision']!=receipt['context_revision']:raise ValueError('Context changed')
 lease=str(uuid4());job=store.call('claim_job',pipeline=receipt['pipeline'],lease_token=lease)
 if job.get('id')!=JOB or job.get('state')!='running' or job.get('lease_token')!=lease:raise ValueError('Unexpected claim')
 store.call('prepare_job',job_id=JOB,lease_token=lease,payload=payload)
 result=store.call('publish_job',job_id=JOB,lease_token=lease)
 if result.get('state')!='applied':raise ValueError('Publication not applied: '+encode(result))
 atomic_private(OUT/'publication.json',result);print(encode(result),flush=True)

if __name__=='__main__':
 if sys.argv[1]=='prepare':prepare(sys.argv[2])
 elif sys.argv[1]=='publish':publish()
 else:raise ValueError('Unknown explicit operation')
