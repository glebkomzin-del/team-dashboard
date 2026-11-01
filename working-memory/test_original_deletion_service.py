import json,tempfile,unittest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from memory import ValidationError,connect,register,claim,apply
from journal_projection import digest
from original_deletion_service import _deletion_inputs,stage_and_plan,purge
from projection_snapshot import build_snapshot
from test_original_deletion import fixture,DELETION_ID,PREPARED_AT

OWNER='20000000-0000-4000-8000-000000000001'
class Store:
 def __init__(self,entry,*,entries=None,receipt=None):self.entry=entry;self.input_entries=entries or [entry];self.receipt=receipt;self.saved=[];self.space_value={'id':'space','owner_id':OWNER,'revision':1,'archive_revision':0,'deletion_revision':0}
 def space(self):return self.space_value
 def entries(self,**kw):return [{**self.entry,'revision':1,'source_version':self.entry['source']['id'],'command_id':str(uuid4()),'actor_id':None,'request_hash':'a'*64}]
 def call(self,op,**fields):
  self.saved.append((op,fields))
  if op=='source_deletion_inputs':return self.input_entries
  if op=='source_deletion_stage':return {'state':'prepared'}
  if op=='source_deletion_candidates':
   if fields['after']:return []
   text=self.receipt if self.receipt is not None else self.entry['source']['transcript']
   return [{'scope':'question','record_key':str(uuid4()),'before_hash':'b'*64,
            'data':{'request_json':'{"question":"Keep","context":"'+text+'"}','response_json':'{"answer":"Keep answer"}'}}]
  if op=='source_deletion_plan_put':return {'saved':True}
  if op=='source_deletion_ledger':return [{'deletion_id':DELETION_ID,'source_id':self.entry['source']['source_id'],'state':'prepared','ledger_revision':1}]
  if op=='source_deletion_purge':return {'state':'purging','snapshot':fields['projection_snapshot']}
  raise AssertionError(op)
class Service:
 def __init__(self,store,db=None):self.store=store;self.db=db
 def authorize(self,identity,space):
  if identity!={'role':'owner','id':OWNER}:raise PermissionError
 @contextmanager
 def projection(self,identity):yield self.db,self.store.space()

class OriginalDeletionServiceTest(unittest.TestCase):
 def test_invalid_deletion_input_is_a_validation_error(self):
  with self.assertRaises(ValidationError):_deletion_inputs([None])
 def test_archive_only_snapshot_has_a_deletion_ledger_without_a_package(self):
  db=connect(':memory:')
  try:
   snapshot=build_snapshot(db,through_revision=0,deletions=[{'deletion_id':DELETION_ID,'source_id':'drive:archive-only'}],logical_basis=[],redaction_packages=[])
   self.assertEqual(snapshot['deletions'][0]['source_id'],'drive:archive-only');self.assertEqual(snapshot['logical_basis'],[])
  finally:db.close()
 def test_archive_only_input_stages_without_inventing_accepted_source(self):
  entry=fixture();original='Archive-only original with a deletion canary.'
  archive={'kind':'archive_only','source':{'id':'archive-doc','source_id':entry['source']['source_id'],
    'content_hash':'c'*64,'event_date':'2026-09-19','title':'Archive only','observed_at':'2026-09-19T10:00:00Z','transcript':original}}
  store=Store(entry,entries=[archive],receipt=original)
  result=stage_and_plan(Service(store),{'role':'owner','id':OWNER},source_id=entry['source']['source_id'],deletion_id=DELETION_ID,prepared_at=PREPARED_AT)
  self.assertEqual(result['packages'],[]);self.assertEqual(result['planned_records'],1)
  stage=next(fields for op,fields in store.saved if op=='source_deletion_stage')
  self.assertEqual(stage['packages'],[])
  plan=next(fields for op,fields in store.saved if op=='source_deletion_plan_put')
  self.assertNotIn(original,str(plan['replacement']))
 def test_stage_scans_every_candidate_and_keeps_independent_chat(self):
  entry=fixture();store=Store(entry);result=stage_and_plan(Service(store),{'role':'owner','id':OWNER},source_id=entry['source']['source_id'],deletion_id=DELETION_ID,prepared_at=PREPARED_AT)
  self.assertEqual(result['planned_records'],1)
  plan=next(fields for op,fields in store.saved if op=='source_deletion_plan_put')
  self.assertNotIn(entry['source']['transcript'],str(plan['replacement']))
  self.assertIn('Keep answer',str(plan['replacement']))
 def test_stage_sanitizes_every_live_source_version_in_one_receipt(self):
  first=fixture('First private version carries enough unique detail for the deletion canary. Nina übernimmt den Export bis Freitag. First private ending.')
  second=fixture('Second private version carries other unique detail for the deletion canary. Nina übernimmt den Export bis Freitag. Second private ending.')
  receipt=json.dumps({'request_json':json.dumps({'context':first['source']['transcript']+' '+second['source']['transcript']}),
                      'response_json':json.dumps({'answer':'Independent answer remains.'})})
  store=Store(first,entries=[first,second],receipt=receipt)
  result=stage_and_plan(Service(store),{'role':'owner','id':OWNER},source_id=first['source']['source_id'],deletion_id=DELETION_ID,prepared_at=PREPARED_AT)
  self.assertEqual(result['planned_records'],1)
  plan=next(fields for op,fields in store.saved if op=='source_deletion_plan_put')
  self.assertNotIn(first['source']['transcript'],str(plan['replacement']))
  self.assertNotIn(second['source']['transcript'],str(plan['replacement']))
  self.assertIn('Independent answer remains.',str(plan['replacement']))
 def test_purge_builds_compiler_capable_redacted_checkpoint(self):
  entry=fixture();store=Store(entry);db=connect(':memory:')
  try:
   source=entry['source'];job=register(db,source_id=source['source_id'],event_date=source['event_date'],title=source['title'],transcript=source['transcript'],pipeline=entry['payload']['pipeline'])
   token=claim(db,job);items=apply(db,job,token,entry['payload']['proposal'],model='fixture')
   entry['payload']['result_sha256']=digest(items)
   staged=stage_and_plan(Service(store),{'role':'owner','id':OWNER},source_id=source['source_id'],deletion_id=DELETION_ID,prepared_at=PREPARED_AT)
   result=purge(Service(store,db),{'role':'owner','id':OWNER},deletion_id=DELETION_ID,command_id=str(uuid4()),packages=staged['packages'])
   basis=result['snapshot']['logical_basis'];self.assertEqual(basis[0]['kind'],'redacted_source');self.assertNotIn(source['transcript'],str(result['snapshot']))
  finally:db.close()
 def test_purge_uses_latest_epoch_after_explicit_reimport(self):
  entry=fixture();store=Store(entry);newest=str(uuid4())
  original_call=store.call
  def call(op,**fields):
   if op=='source_deletion_ledger':return [
    {'deletion_id':str(uuid4()),'source_id':entry['source']['source_id'],'state':'verified','ledger_revision':2},
    {'deletion_id':newest,'source_id':entry['source']['source_id'],'state':'prepared','ledger_revision':4}]
   return original_call(op,**fields)
  store.call=call;db=connect(':memory:')
  try:
   source=entry['source'];job=register(db,source_id=source['source_id'],event_date=source['event_date'],title=source['title'],transcript=source['transcript'],pipeline=entry['payload']['pipeline'])
   token=claim(db,job);entry['payload']['result_sha256']=digest(apply(db,job,token,entry['payload']['proposal'],model='fixture'))
   package=stage_and_plan(Service(Store(entry)),{'role':'owner','id':OWNER},source_id=source['source_id'],deletion_id=newest,prepared_at=PREPARED_AT)['packages']
   result=purge(Service(store,db),{'role':'owner','id':OWNER},deletion_id=newest,command_id=str(uuid4()),packages=package)
   self.assertEqual(result['snapshot']['deletions'],[{'deletion_id':newest,'source_id':source['source_id']}])
  finally:db.close()
if __name__=='__main__':unittest.main()
