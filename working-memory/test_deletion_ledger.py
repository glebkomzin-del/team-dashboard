import json,tempfile,threading,unittest
from pathlib import Path
from deletion_ledger import write,read
from memory import ValidationError

class DeletionLedgerTest(unittest.TestCase):
 def test_current_external_watermark_is_durable_and_tamper_evident(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'restore-ledger.json'
   value=write(path,space_id='space',minimum_deletion_revision=4,deletions=[{'deletion_id':'d','source_id':'s'}],observed_at='2026-09-19T12:00:00Z')
   self.assertEqual(read(path,space_id='space')['minimum_deletion_revision'],4)
   changed=json.loads(path.read_text());changed['minimum_deletion_revision']=3;path.write_text(json.dumps(changed))
   with self.assertRaisesRegex(ValidationError,'Invalid external'):read(path,space_id='space')
 def test_missing_ledger_fails_closed(self):
  with self.assertRaisesRegex(ValidationError,'required'):read('/not/here',space_id='space')
 def test_watermark_cannot_roll_back_or_drop_a_deletion_identity(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'restore-ledger.json';deletions=[{'deletion_id':'d','source_id':'s','state':'prepared'}]
   write(path,space_id='space',minimum_deletion_revision=4,deletions=deletions,observed_at='now')
   with self.assertRaisesRegex(ValidationError,'must not decrease'):
    write(path,space_id='space',minimum_deletion_revision=3,deletions=deletions,observed_at='later')
   with self.assertRaisesRegex(ValidationError,'must not disappear'):
    write(path,space_id='space',minimum_deletion_revision=4,deletions=[],observed_at='later')
   self.assertEqual(read(path,space_id='space')['minimum_deletion_revision'],4)
 def test_same_revision_allows_only_forward_deletion_state(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'restore-ledger.json'
   write(path,space_id='space',minimum_deletion_revision=4,deletions=[{'deletion_id':'d','source_id':'s','state':'prepared'}],observed_at='now')
   write(path,space_id='space',minimum_deletion_revision=4,deletions=[{'deletion_id':'d','source_id':'s','state':'verified'}],observed_at='later')
   with self.assertRaisesRegex(ValidationError,'state must not regress'):
    write(path,space_id='space',minimum_deletion_revision=4,deletions=[{'deletion_id':'d','source_id':'s','state':'purging'}],observed_at='later')
   self.assertEqual(read(path,space_id='space')['deletions'][0]['state'],'verified')
 def test_corrupt_current_ledger_fails_closed_but_stale_temp_does_not_block(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'restore-ledger.json';path.write_text('{broken')
   with self.assertRaisesRegex(ValidationError,'required'):write(path,space_id='space',minimum_deletion_revision=1,deletions=[],observed_at='now')
   path.unlink();(Path(folder)/'.restore-ledger.json.tmp').write_text('interrupted')
   write(path,space_id='space',minimum_deletion_revision=1,deletions=[],observed_at='now')
   self.assertEqual(read(path,space_id='space')['minimum_deletion_revision'],1)
 def test_concurrent_writer_cannot_leave_a_lower_watermark(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'restore-ledger.json';write(path,space_id='space',minimum_deletion_revision=4,deletions=[],observed_at='start')
   barrier=threading.Barrier(2);errors=[]
   def writer(revision):
    try:barrier.wait();write(path,space_id='space',minimum_deletion_revision=revision,deletions=[],observed_at=str(revision))
    except ValidationError as error:errors.append(str(error))
   high=threading.Thread(target=writer,args=(5,));low=threading.Thread(target=writer,args=(3,));high.start();low.start();high.join();low.join()
   self.assertEqual(read(path,space_id='space')['minimum_deletion_revision'],5)
   self.assertTrue(all('watermark' in error for error in errors))
if __name__=='__main__':unittest.main()
