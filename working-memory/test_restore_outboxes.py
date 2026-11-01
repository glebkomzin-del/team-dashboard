import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from restore_outboxes import restore_receipts


class Store:
 space_id='space'
 def __init__(self):self.calls=[]
 def call(self,op,**fields):self.calls.append((op,fields));return {'saved':True}


class RestoreOutboxTests(unittest.TestCase):
 def package(self,root,model=None,question=None):
  archive=root/'archive';archive.mkdir();outboxes={'response-outbox':model or [],'question-outbox':question or []};files={}
  for directory,rows in outboxes.items():
   if rows:
    path=archive/directory;path.mkdir()
    for name,body in rows:
     target=path/name;target.write_bytes(body);files[str(target.relative_to(archive))]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
  declared={name:[{'name':item[0],'bytes':len(item[1]),'sha256':hashlib.sha256(item[1]).hexdigest()} for item in rows] for name,rows in outboxes.items()}
  receipt=archive/'receipt-manifest.json';receipt.write_text(json.dumps({'format':'working-memory-receipts-v1','outboxes':declared}))
  files['receipt-manifest.json']={'bytes':receipt.stat().st_size,'sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()}
  (archive/'bundle-manifest.json').write_text(json.dumps({'format':'dashboard-full-backup-v1','files':files}));return archive
 def test_copies_and_persists_actual_hash_job_and_question_receipts(self):
  with tempfile.TemporaryDirectory() as tmp,patch('restore_outboxes.os.chown'):
   root=Path(tmp);job='a'*64;qid='20000000-0000-4000-8000-000000000001';digest='44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
   model=json.dumps({'space_id':'space','job_id':job,'lease_token':'lease','call_index':0,'response_json':'{}','actual_micro_usd':1,'response_hash':digest}).encode()
   question=json.dumps({'space_id':'space','question_id':qid,'actor_id':'owner','call_index':0,'response_json':'{}','actual_micro_usd':1,'response_hash':digest}).encode()
   archive=self.package(root,[(job+'-0.json',model)],[('question-'+qid+'-0.json',question)]);targets={'response-outbox':root/'live-model','question-outbox':root/'live-question'};store=Store()
   result=restore_receipts(store,archive,targets)
   self.assertEqual(result['persisted'],{'response-outbox':1,'question-outbox':1});self.assertEqual([value[0] for value in store.calls],['receive_call','question_receive'])
 def test_empty_manifest_allows_tar_without_empty_directories(self):
  with tempfile.TemporaryDirectory() as tmp,patch('restore_outboxes.os.chown'):
   root=Path(tmp);archive=self.package(root);targets={'response-outbox':root/'model','question-outbox':root/'question'}
   self.assertEqual(restore_receipts(Store(),archive,targets)['persisted'],{'response-outbox':0,'question-outbox':0})
 def test_wrong_scope_is_rejected_before_live_receipt_copy(self):
  with tempfile.TemporaryDirectory() as tmp,patch('restore_outboxes.os.chown'):
   root=Path(tmp);job='a'*64;body=json.dumps({'space_id':'other','job_id':job,'lease_token':'lease','call_index':0,'response_json':'{}','actual_micro_usd':1,'response_hash':'44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'}).encode()
   archive=self.package(root,[(job+'-0.json',body)]);target=root/'model';targets={'response-outbox':target,'question-outbox':root/'question'}
   with self.assertRaises(RuntimeError):restore_receipts(Store(),archive,targets)
   self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
