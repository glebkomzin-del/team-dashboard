import hashlib,io,json,tarfile,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from deletion_ledger import read,write
from offserver_backup import persist_restore_barrier_copy,verify_bundle
from server import backup_status

class OffserverBackupTests(unittest.TestCase):
 def archive(self,path,*,body=b'original',hash_body=b'original',name='source.txt'):
  manifest={'format':'dashboard-full-backup-v1','files':{name:{'bytes':len(body),'sha256':hashlib.sha256(hash_body).hexdigest()}}}
  with tarfile.open(path,'w:gz') as tar:
   for label,data in [(name,body),('bundle-manifest.json',json.dumps(manifest).encode())]:
    info=tarfile.TarInfo(label);info.size=len(data);tar.addfile(info,io.BytesIO(data))
 def test_offserver_copy_verifies_every_member_instead_of_trusting_transfer(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'backup.tar.gz';self.archive(p)
   self.assertEqual(verify_bundle(p),{'files_verified':1})
   self.archive(p,body=b'changed!',hash_body=b'original')
   with self.assertRaisesRegex(ValueError,'checksum'):verify_bundle(p)
 def test_path_escape_never_becomes_a_verified_bundle(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'backup.tar.gz';self.archive(p,name='../source.txt')
   with self.assertRaisesRegex(ValueError,'path'):verify_bundle(p)
 def test_recent_check_cannot_hide_an_old_copied_backup(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'status.json';now=datetime.now(timezone.utc)
   p.write_text(json.dumps({'state':'ok','last_success_at':now.isoformat(),'last_backup_at':(now-timedelta(days=3)).isoformat(),'archive':'private','target':'owner_mac'}))
   value=backup_status(p)
   self.assertTrue(value['stale']);self.assertNotIn('archive',value);self.assertNotIn('target',value)
 def test_current_restore_barrier_is_copied_outside_rotating_archives_without_rollback(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'remote.json';target=Path(tmp)/'mac'/'deletions.json'
   write(source,space_id='space',minimum_deletion_revision=4,deletions=[{'deletion_id':'d','source_id':'s'}],observed_at='now')
   receipt=persist_restore_barrier_copy(source,target)
   self.assertEqual(receipt['minimum_deletion_revision'],4);self.assertEqual(receipt['ledger_observed_at'],'now')
   old=Path(tmp)/'remote-old.json';write(old,space_id='space',minimum_deletion_revision=3,deletions=[{'deletion_id':'d','source_id':'s'}],observed_at='old')
   source.write_bytes(old.read_bytes())
   with self.assertRaises(Exception):persist_restore_barrier_copy(source,target)
   self.assertEqual(read(target,space_id='space')['minimum_deletion_revision'],4)

if __name__=='__main__':unittest.main()
