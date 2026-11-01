import json,tempfile,unittest
from pathlib import Path
from canonical_backup import export
from canonical_restore import generate,prepared_rows
from test_canonical_backup import Store
from archive_index import digest
from memory import ValidationError
from deletion_ledger import write as write_deletion_ledger

OWNER='20000000-0000-4000-8000-000000000001'
STAMP='2026-09-07T00:00:00+00:00'
class CompleteStore(Store):
 def __init__(self):
  super().__init__();job=json.loads(self.records[0]['record_json'])
  job.update(pipeline='fixture-v9',state='running',reason=None,expected_revision=0,lease_token='30000000-0000-4000-8000-000000000001',lease_until='2026-09-08T00:00:00+00:00',attempts=1,command_id='40000000-0000-4000-8000-000000000001',prepared_payload=None,applied_revision=None,created_at=STAMP,updated_at=STAMP)
  call=json.loads(self.records[1]['record_json']);call.update(response_json=None,response_hash=None,actual_micro_usd=None,received_at=None,created_at=STAMP)
  call['request_json']=json.dumps({'model':'synthetic','prompt':"'; DROP TABLE wm_spaces; --\n\\! touch /tmp/should-never-exist ä 👋"},ensure_ascii=False);call['request_hash']=digest(call['request_json'])
  response='{"answer":"Exact prior paid response 👋"}'
  previous={**call,'call_index':1,'response_json':response,'response_hash':digest(response),'actual_micro_usd':12345,'received_at':STAMP}
  config={'space_id':self.space_id,'enabled':True,'automatic_from':'2026-06-01','pipeline':'fixture-v9','budget_micro_usd':10000000}
  decision=dict(space_id=self.space_id,command_id='50000000-0000-4000-8000-000000000001',job_id=job['id'],actor_id=OWNER,action='retry',reason='Manually accepted earlier retry',request={'fixture':True},previous_job={**job,'state':'review'},result={'state':'queued'},recorded_at=STAMP)
  self.records=[]
  for i,(kind,value) in enumerate([('config',config),('job',job),('call',call),('call',previous),('job_decision',decision)]):
   raw=json.dumps(value,ensure_ascii=False);self.records.append({'sequence':i+1,'kind':kind,'record_json':raw,'record_hash':digest(raw)})
 def call(self,op,**kw):
  result=super().call(op,**kw)
  if op=='backup_begin':result.update(space_json={'id':self.space_id,'owner_id':OWNER,'state':'active','label':'Restore fixture','revision':0,'archive_revision':2,'deletion_revision':0,'created_at':STAMP},deletion_revision=0,record_count=len(self.records))
  return result

class RestoreTests(unittest.TestCase):
 def ledger(self,tmp,space_id,minimum=0):
  path=Path(tmp)/'restore-ledger.json';write_deletion_ledger(path,space_id=space_id,
   minimum_deletion_revision=minimum,deletions=[],observed_at=STAMP);return path
 def test_question_cost_ledger_is_included_in_paused_restore(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=CompleteStore();request='{"question":"fixture"}';response='{"answer":"fixture"}'
   q={'space_id':store.space_id,'id':'60000000-0000-4000-8000-000000000001','actor_id':OWNER,'revision':0,'archive_revision':2,
      'request_json':request,'request_hash':digest(request),'response_json':response,'response_hash':digest(response),'created_at':STAMP,'completed_at':STAMP}
   qc={'space_id':store.space_id,'question_id':q['id'],'call_index':0,'request_json':request,'request_hash':digest(request),
       'reserved_micro_usd':5000,'actual_micro_usd':1200,'response_json':response,'response_hash':digest(response),'created_at':STAMP,'received_at':STAMP}
   for kind,value in [('question',q),('question_call',qc)]:
    raw=json.dumps(value);store.records.append({'sequence':len(store.records)+1,'kind':kind,'record_json':raw,'record_hash':digest(raw)})
   folder=Path(tmp)/'snapshot';export(store,folder);ledger=self.ledger(tmp,store.space_id);rows,_=prepared_rows(folder,ledger)
   self.assertEqual(rows['wm_questions'],[q]);self.assertEqual(rows['wm_question_calls'],[qc])
   path=Path(tmp)/'restore.sql';generate(folder,path,restore_ledger=ledger,verification_only=True)
   sql=path.read_text();self.assertIn("'wm_questions'",sql);self.assertIn("'wm_question_calls'",sql)
 def test_exact_paid_receipts_and_decisions_survive_but_automation_is_paused(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=CompleteStore();folder=Path(tmp)/'snapshot';export(store,folder);ledger=self.ledger(tmp,store.space_id);rows,_=prepared_rows(folder,ledger)
   self.assertEqual(rows['wm_spaces'][0]['state'],'draft');self.assertFalse(rows['wm_processing_config'][0]['enabled'])
   self.assertEqual(len(rows['wm_model_calls']),2);self.assertIsNone(rows['wm_model_calls'][0]['response_json'])
   self.assertEqual(rows['wm_model_calls'][1]['actual_micro_usd'],12345);self.assertEqual(len(rows['wm_job_decisions']),1)
   path=Path(tmp)/'restore.sql';receipt=generate(folder,path,restore_ledger=ledger,verification_only=True);sql=path.read_text()
   self.assertNotIn('DROP TABLE wm_spaces',sql);self.assertNotIn('\\! touch',sql);self.assertTrue(sql.endswith('ROLLBACK;\n'))
   self.assertFalse(receipt['overwrite']);self.assertEqual(receipt['database_connections'],0)
 def test_existing_output_is_not_overwritten(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=CompleteStore();folder=Path(tmp)/'snapshot';export(store,folder);ledger=self.ledger(tmp,store.space_id);path=Path(tmp)/'restore.sql';path.write_text('Keep previous approved recovery')
   with self.assertRaises(FileExistsError):generate(folder,path,restore_ledger=ledger)
   self.assertEqual(path.read_text(),'Keep previous approved recovery')
 def test_backup_before_external_deletion_watermark_is_refused(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=CompleteStore();folder=Path(tmp)/'snapshot';export(store,folder);ledger=self.ledger(tmp,store.space_id,minimum=1)
   with self.assertRaisesRegex(ValidationError,'predates'):prepared_rows(folder,ledger)

if __name__=='__main__':unittest.main()
