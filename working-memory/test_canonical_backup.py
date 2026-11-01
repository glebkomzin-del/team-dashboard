import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_canonical_archive import fixture,SPACE
from archive_index import digest
from canonical_backup import export,verify,checksum
from memory import ValidationError

class Store:
 space_id=SPACE
 def __init__(self):
  _,self.doc,self.note=fixture();self.released=False;self.fail_page=False
  job={'space_id':SPACE,'id':digest(self.doc['source_id']+':'+self.doc['body_hash']),'document_id':self.doc['id'],'source_id':self.doc['source_id'],'event_date':self.doc['event_date'],'state':'review'}
  req='{"prompt":"Exact Unicode ä 👋","model":"synthetic"}'
  call={'space_id':SPACE,'job_id':job['id'],'call_index':0,'request_json':req,'request_hash':digest(req),'response_json':None,'response_hash':None,'reserved_micro_usd':500000}
  self.records=[]
  for index,(kind,value) in enumerate([('job',job),('call',call),('config',{'space_id':SPACE,'enabled':False})]):
   raw=json.dumps(value,ensure_ascii=False);self.records.append({'sequence':index+50,'kind':kind,'record_json':raw,'record_hash':digest(raw)})
 def entries(self,**kw):return []
 def archive_rows(self,kind,**kw):return iter([self.doc] if kind=='documents' else [self.note])
 def call(self,op,**v):
  if op=='backup_begin':return {'id':v['snapshot_id'],'space_id':SPACE,'space_json':{'id':SPACE,'owner_id':'synthetic','state':'draft','deletion_revision':0},'revision':0,'archive_revision':2,'deletion_revision':0,'record_count':3}
  if op=='backup_page':return [] if self.fail_page else [copy.deepcopy(r) for r in self.records if r['sequence']>v['after']][:1]
  if op=='backup_release':self.released=True;return {'released':True}
  raise AssertionError(op)

class BackupTests(unittest.TestCase):
 def test_question_requests_calls_and_cost_receipts_are_verified(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=Store();request='{"question":"Was ist offen?"}';response='{"answer":"Belegt"}'
   question={'space_id':SPACE,'id':'20000000-0000-4000-8000-000000000001','actor_id':'30000000-0000-4000-8000-000000000001',
    'revision':0,'archive_revision':2,'request_json':request,'request_hash':digest(request),'response_json':response,'response_hash':digest(response)}
   call={'space_id':SPACE,'question_id':question['id'],'call_index':0,'request_json':request,'request_hash':digest(request),
    'reserved_micro_usd':5000,'actual_micro_usd':1234,'response_json':response,'response_hash':digest(response)}
   for kind,value in [('question',question),('question_call',call)]:
    raw=json.dumps(value);store.records.append({'sequence':len(store.records)+50,'kind':kind,'record_json':raw,'record_hash':digest(raw)})
   original=store.call
   def invoke(op,**values):
    result=original(op,**values)
    if op=='backup_begin':result['record_count']=len(store.records)
    return result
   store.call=invoke
   result=export(store,Path(tmp)/'snapshot')
   self.assertEqual(result['queue_records']['question'],1);self.assertEqual(result['queue_records']['question_call'],1)
 def test_bounded_multi_record_page_preserves_order_and_complete_restore(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=Store();original=store.call
   store.call=lambda op,**values:copy.deepcopy(store.records) if op=='backup_page' and values['after']==0 else original(op,**values)
   result=export(store,Path(tmp)/'snapshot')
   self.assertTrue(result['verified']);self.assertEqual(sum(result['queue_records'].values()),3)
 def test_exact_export_and_full_offline_reconstruction_before_release(self):
  with tempfile.TemporaryDirectory() as tmp,patch('processor.anthropic') as api:
   store=Store();folder=Path(tmp)/'snapshot';result=export(store,folder)
   self.assertTrue(store.released);self.assertTrue(result['verified']);self.assertEqual(result['queue_records'],{'job':1,'call':1,'config':1})
   self.assertEqual((result['documents'],result['notes']),(1,1));self.assertEqual(verify(folder),result);api.assert_not_called()
   self.assertIn('Exact Unicode ä 👋',(folder/'queue.jsonl').read_text())
   self.assertEqual((folder/'queue.jsonl').stat().st_mode & 0o777,0o600)
 def test_missing_page_cannot_release_snapshot_or_mark_it_verified(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=Store();store.fail_page=True;folder=Path(tmp)/'snapshot'
   with self.assertRaises(ValidationError):export(store,folder)
   self.assertFalse(store.released);self.assertFalse((folder/'restore-check.json').exists())
 def test_tampering_and_missing_records_fail_independent_restore_check(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)/'snapshot';export(Store(),folder)
   q=folder/'queue.jsonl';original=q.read_text();q.write_text(original.replace('Exact Unicode','Changed Unicode'))
   with self.assertRaises(ValidationError):verify(folder)
   # Even recomputing the outer file checksum cannot conceal an altered model request.
   m=folder/'manifest.json';manifest=json.loads(m.read_text());manifest['files']['queue.jsonl']={'bytes':q.stat().st_size,'sha256':checksum(q)};m.write_text(json.dumps(manifest))
   with self.assertRaises(ValidationError):verify(folder)

if __name__=='__main__':unittest.main()
