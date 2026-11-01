import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from canonical_backup import export,verify,checksum
from canonical_restore import prepared_rows,generate
from test_canonical_restore import CompleteStore,STAMP,OWNER
from test_generation_review import entry,CMD
from generation_review import compile_generation
from memory import connect,ValidationError
from archive_index import digest
from deletion_ledger import write as write_deletion_ledger

class GenerationStore(CompleteStore):
 def __init__(self,state):
  super().__init__();db=connect(':memory:');self.source=entry(db,'drive:generation-backup');db.close()
  payload=compile_generation([],[self.source],source_reviews={'drive:generation-backup':'Vollständiges Original manuell geprüft'},identity_links=[],reason='Geprüfte Ergänzung')
  self.review=dict(space_id=self.space_id,id='60000000-0000-4000-8000-000000000001',expected_revision=0,label='Original ergänzen',payload=payload,review_sha256=payload['review_sha256'],job_id=None,job_updated_at=None,state=state,created_at=STAMP,
   decision_command_id=None,decision_actor_id=None,decision_reason=None,decision_hash=None,decision_result=None,decided_at=None)
  self.journal=[]
  if state!='pending':
   result={'revision':int(state=='accepted'),'state':state,'review_id':self.review['id'],'command_id':CMD,'repeated':False}
   self.review.update(decision_command_id=CMD,decision_actor_id=OWNER,decision_reason='Original und Auswirkungen geprüft',decision_hash='a'*64,decision_result=result,decided_at=STAMP)
  if state=='accepted':
   self.journal=[dict(revision=1,command_id=CMD,actor_id=OWNER,kind='generation',source_version=None,payload=payload,request_hash='b'*64,recorded_at=STAMP)]
  self.repack()
 def repack(self):
  self.records=[r for r in self.records if r['kind']!='generation_review'];raw=json.dumps(self.review,ensure_ascii=False)
  self.records.append(dict(sequence=len(self.records)+1,kind='generation_review',record_json=raw,record_hash=digest(raw)))
 def entries(self,through=None,**kw):return deepcopy(self.journal[:through])
 def call(self,op,**kw):
  result=super().call(op,**kw)
  if op=='backup_begin':result['revision']=len(self.journal);result['space_json']['revision']=len(self.journal)
  return result

class GenerationBackupTests(unittest.TestCase):
 def test_pending_rejected_and_accepted_reviews_survive_full_export_and_paused_restore(self):
  for state in ['pending','rejected','accepted']:
   with self.subTest(state=state),tempfile.TemporaryDirectory() as tmp:
    store=GenerationStore(state);folder=Path(tmp)/'snapshot';proof=export(store,folder)
    ledger=Path(tmp)/'restore-ledger.json';write_deletion_ledger(ledger,space_id=store.space_id,minimum_deletion_revision=0,deletions=[],observed_at=STAMP)
    rows,_=prepared_rows(folder,ledger)
    self.assertEqual(proof['queue_records']['generation_review'],1)
    self.assertEqual(rows['wm_generation_reviews'],[store.review]);self.assertEqual(proof['observations'],int(state=='accepted'))
    self.assertEqual(len(rows['wm_source_versions']),int(state=='accepted'))
    path=Path(tmp)/'restore.sql';generate(folder,path,restore_ledger=ledger,verification_only=True)
    self.assertIn('public.wm_generation_reviews',path.read_text());self.assertEqual(verify(folder),proof)
 def test_corrupt_inner_generation_is_rejected_even_with_outer_checksums_updated(self):
  store=GenerationStore('pending');store.review['payload']['diff'][0]['after']['title']='Forged task';store.repack()
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(ValidationError):export(store,Path(tmp)/'snapshot')
   self.assertFalse(store.released)
 def test_acceptance_receipt_must_reference_exact_journal_actor_and_command(self):
  store=GenerationStore('accepted');store.review['decision_actor_id']='70000000-0000-4000-8000-000000000001';store.repack()
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaisesRegex(ValidationError,'immutable journal'):export(store,Path(tmp)/'snapshot')
   self.assertFalse(store.released)

if __name__=='__main__':unittest.main()
