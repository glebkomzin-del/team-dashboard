from contextlib import contextmanager
from copy import deepcopy
import sqlite3,tempfile,unittest
from unittest.mock import Mock,patch
from memory import connect,overview,ValidationError
from generation_service import stage,inspect,decide,make_plan
from generation_review import compile_generation
from journal_service import JournalService
from journal_store import RevisionConflict
from test_generation_review import entry,TEXT,OWNER,CMD

SPACE='10000000-0000-4000-8000-000000000001';REVIEW='30000000-0000-4000-8000-000000000001'
IDENTITY={'role':'owner','id':OWNER}
class GenerationServiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=connect(':memory:');self.e=entry(self.db,'drive:test')
  self.store=Mock();self.store.space.return_value={'id':SPACE,'owner_id':OWNER,'revision':0};self.store.entries.return_value=[];self.store.call.return_value=None
  self.service=JournalService(self.store,self.tmp.name)
  self.archive=sqlite3.connect(':memory:');self.archive.execute('create table documents(id,source_id,body_hash,event_date,title,body)')
  s=self.e['source'];self.archive.execute('insert into documents values(?,?,?,?,?,?)',('archive-fixture',s['source_id'],s['content_hash'],s['event_date'],s['title'],s['transcript']))
  @contextmanager
  def archive(identity):yield self.archive,self.store.space.return_value
  self.service.archive_projection=archive
  self.request={'review_id':REVIEW,'expected_revision':0,'label':'Neue Originalfassung prüfen','changes':[{'source_id':'drive:test','action':'add','entry':self.e,'reason':'Original vollständig geprüft'}],'identity_links':[],'topic_links':[],'reason':'Vorhandene Daten kontrolliert übernehmen','job_id':None}
 def tearDown(self):self.archive.close();self.db.close();self.tmp.cleanup()
 def row(self):
  payload=compile_generation([],[self.e],source_reviews={'drive:test':'Original vollständig geprüft'},identity_links=[],reason=self.request['reason'])
  return {'id':REVIEW,'space_id':SPACE,'label':'Review','expected_revision':0,'payload':payload,'review_sha256':payload['review_sha256'],'state':'pending'}
 def decision(self,row):return {'review_id':REVIEW,'command_id':CMD,'expected_revision':0,'review_sha256':row['review_sha256'],'action':'accept','reason':'Änderungen geprüft'}
 def test_only_staging_allows_service_identity_and_it_never_calls_model(self):
  with patch('processor.anthropic') as api:
   stage(self.service,{'role':'service'},self.request);api.assert_not_called()
  call=self.store.call.call_args;self.assertEqual(call.args,('generation_stage',));self.assertEqual(call.kwargs['expected_revision'],0)
  with self.assertRaises(PermissionError):decide(self.service,{'role':'service'},self.decision(self.row()))
 def test_unarchived_self_consistent_source_is_rejected(self):
  self.archive.execute('delete from documents')
  with self.assertRaisesRegex(ValidationError,'archived'):stage(self.service,IDENTITY,self.request)
  self.assertTrue(all(c.args!=('generation_stage',) for c in self.store.call.call_args_list))
 def test_owner_is_bound_and_stale_accept_does_not_write(self):
  row=self.row();self.store.call.return_value=row
  with self.assertRaises(PermissionError):decide(self.service,{'role':'owner','id':'other'},self.decision(row))
  self.store.space.return_value['revision']=1
  with self.assertRaises(RevisionConflict):decide(self.service,IDENTITY,self.decision(row))
  self.assertTrue(all(c.args!=('generation_decide',) for c in self.store.call.call_args_list))
 def test_lost_acceptance_acknowledgement_reaches_sql_identity_check(self):
  row=self.row();row['state']='accepted';self.store.call.return_value=row;self.store.space.return_value['revision']=1
  decide(self.service,IDENTITY,self.decision(row))
  self.assertEqual(self.store.call.call_args.args,('generation_decide',));self.assertEqual(self.store.call.call_args.kwargs['actor_id'],OWNER)
 def test_generation_decision_note_is_optional(self):
  row=self.row();self.store.call.return_value=row
  decide(self.service,IDENTITY,{**self.decision(row),'reason':''})
  self.assertEqual(self.store.call.call_args.kwargs['reason'],'')
 def test_lost_stage_acknowledgement_recompiles_original_boundary(self):
  row=self.row();self.store.call.return_value=row;self.store.space.return_value['revision']=1
  stage(self.service,IDENTITY,self.request)
  self.store.entries.assert_called_with(through=0)
  self.assertEqual(self.store.call.call_args.kwargs['expected_revision'],0)
 def test_inspect_exposes_review_changes_without_raw_plan_or_transcript(self):
  row=self.row();self.store.call.return_value=row
  result=inspect(self.service,IDENTITY,REVIEW)
  self.assertEqual(result['sources'][0]['after']['title'],'drive:test');self.assertEqual(result['sources'][0]['after']['archive_id'],'archive-fixture')
  self.assertFalse(result['stale']);self.assertIn('observation_diff',result);self.assertNotIn('entries',result);self.assertNotIn('new_sources',result)
 def test_stale_inspection_still_verifies_original_boundary_and_detects_tampering(self):
  row=self.row();self.store.call.return_value=row;self.store.space.return_value['revision']=1
  self.assertTrue(inspect(self.service,IDENTITY,REVIEW)['stale']);self.store.entries.assert_called_with(through=0)
  row['payload']['diff'][0]['after']['title']='Manipulated title'
  with self.assertRaises(ValidationError):inspect(self.service,IDENTITY,REVIEW)
 def test_explicit_identity_link_rebinds_followup_and_personal_decision(self):
  wid=overview(self.db)['personal'][0]['id'];later=entry(self.db,'drive:later',day='2026-07-16')
  later['payload']['proposal']['observations'][0].update(kind='status',update='progress',update_target=wid)
  h={'kind':'human','command_id':CMD,'actor_id':OWNER,'payload':{'target_id':wid,'action':'reject','patch':{},'event_date':'2026-09-06','reason':'Rejected'}}
  new=deepcopy(self.e);new['payload']['proposal']['coverage_notes']=['Updated note']
  plan,reasons=make_plan([self.e,later,h],[{'source_id':'drive:test','action':'replace','entry':new,'reason':'Geprüft'}],[{'old_id':wid,'new_id':'new-id','reason':'Dieselbe geprüfte Aufgabe'}],[])
  self.assertEqual(plan[1]['payload']['proposal']['observations'][0]['update_target'],'new-id');self.assertEqual(plan[2]['payload']['target_id'],'new-id');self.assertIn('drive:later',reasons)

 def test_same_day_order_is_staged_audited_and_exposed_by_title(self):
  second=entry(self.db,'drive:second');base=[self.e,second]
  self.store.entries.return_value=base;self.store.space.return_value['revision']=2
  audit={'before':['drive:test','drive:second'],'after':['drive:second','drive:test'],'reason':'Second meeting is explicitly earlier in its original'}
  request={**self.request,'expected_revision':2,'changes':[],'source_order_review':audit}
  with patch('processor.anthropic') as api:
   stage(self.service,IDENTITY,request);api.assert_not_called()
  payload=self.store.call.call_args.kwargs['payload']
  self.assertEqual(payload['source_order_review'],audit)
  self.store.call.return_value={'id':REVIEW,'space_id':SPACE,'expected_revision':2,'payload':payload,'review_sha256':payload['review_sha256'],'state':'pending'}
  shown=inspect(self.service,IDENTITY,REVIEW)
  self.assertEqual(shown['source_order_changes'][0],{'source_id':'drive:test','title':'drive:test','event_date':'2026-07-15','before_position':1,'after_position':2})
  self.assertEqual(shown['source_order_reason'],audit['reason'])
  stage(self.service,IDENTITY,request)
  self.assertEqual(self.store.call.call_args.kwargs['payload'],payload)

 def test_source_order_cannot_omit_or_repeat_retained_sources(self):
  second=entry(self.db,'drive:second')
  for order in ([],['drive:test'],['drive:test','drive:test'],['drive:test',{}]):
   with self.subTest(order=order),self.assertRaises(ValidationError):
    make_plan([self.e,second],[],[],[],{'before':['drive:test','drive:second'],'after':order,'reason':'Invalid'})

if __name__=='__main__':unittest.main()
