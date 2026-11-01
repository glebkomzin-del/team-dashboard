from datetime import datetime,timezone,timedelta
import json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import Mock,patch
from scheduled_backup import RESTORE_BARRIER,copy_outbox,configured_outboxes,host_cache_path,persist_current_restore_barrier,prune,receipt_manifest,return_restore_barrier_to_service
from server import backup_status

class BackupOperationTests(unittest.TestCase):
 def test_outbox_copy_keeps_settled_file_and_rejects_changed_identity(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source';source.mkdir();target=Path(tmp)/'target';p=source/'reply.json';p.write_text('{"answer":"full response"}')
   copy_outbox(source,target);p.unlink();copy_outbox(source,target)
   self.assertEqual((target/'reply.json').read_text(),'{"answer":"full response"}')
   p.write_text('{"answer":"changed"}')
   with self.assertRaises(RuntimeError):copy_outbox(source,target)
 def test_retention_keeps_recent_and_weekly_verified_archives(self):
  with tempfile.TemporaryDirectory() as tmp,patch('scheduled_backup.BACKUPS',Path(tmp)):
   now=datetime.now(timezone.utc)
   for age in range(90):
    stamp=now-timedelta(days=age);p=Path(tmp)/('dashboard-'+stamp.strftime('%Y%m%dT%H%M%SZ')+'.tar.gz');p.write_bytes(b'fixture');os.utime(p,(stamp.timestamp(),stamp.timestamp()))
   incomplete=Path(tmp)/'unfinished.partial';incomplete.write_bytes(b'partial')
   prune(now);files=list(Path(tmp).glob('*.tar.gz'))
   self.assertGreaterEqual(len(files),14);self.assertLess(len(files),25);self.assertTrue(incomplete.exists())
   self.assertTrue(any(now-datetime.fromtimestamp(p.stat().st_mtime,timezone.utc)>timedelta(days=40) for p in files))
 def test_public_status_hides_private_paths_and_detects_missing_or_stale_backup(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'status.json';self.assertEqual(backup_status(p),{'state':'not_configured'})
   p.write_text(json.dumps({'state':'ok','archive':'private-path','sha256':'private','last_success_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}))
   value=backup_status(p);self.assertTrue(value['stale']);self.assertNotIn('archive',value);self.assertNotIn('sha256',value)
   p.write_text('broken');self.assertEqual(backup_status(p),{'state':'unavailable'})
 def test_restore_barrier_uses_the_private_host_cache_mount(self):
  with tempfile.TemporaryDirectory() as tmp,patch('scheduled_backup.ROOT',Path(tmp)):
   self.assertEqual(host_cache_path(RESTORE_BARRIER),Path(tmp)/'.local/cache/restore-barrier/deletions.json')
   with self.assertRaises(RuntimeError):host_cache_path('/tmp/deletions.json')
 def test_backup_uses_distinct_worker_and_question_receipt_paths(self):
  with tempfile.TemporaryDirectory() as tmp,patch('scheduled_backup.ROOT',Path(tmp)):
   paths=configured_outboxes({'MEMORY_CACHE_DIR':'/app/.local/projections','MEMORY_QA_OUTBOX':'.local/question-outbox'})
   self.assertEqual(paths,{'response-outbox':Path(tmp)/'.local/cache/projections/response-outbox',
                           'question-outbox':Path(tmp)/'.local/cache/question-outbox'})
 def test_receipt_manifest_declares_empty_question_outbox(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);(folder/'response-outbox').mkdir();(folder/'question-outbox').mkdir();(folder/'response-outbox'/'x.json').write_text('{}')
   receipt_manifest(folder);value=json.loads((folder/'receipt-manifest.json').read_text())
   self.assertEqual(value['outboxes']['question-outbox'],[]);self.assertEqual(value['outboxes']['response-outbox'][0]['name'],'x.json')
 def test_backup_attests_the_barrier_with_the_current_owner(self):
  store=Mock();store.space.return_value={'owner_id':'owner'}
  with patch('scheduled_backup.persist_restore_barrier',return_value={'restore_ledger_persisted':True}) as persist,patch('scheduled_backup.return_restore_barrier_to_service'):
   self.assertTrue(persist_current_restore_barrier(store)['restore_ledger_persisted'])
  self.assertEqual(persist.call_args.args[1],{'role':'owner','id':'owner'})
  self.assertEqual(persist.call_args.args[2],host_cache_path(RESTORE_BARRIER))
 def test_root_backup_returns_barrier_directory_lock_and_file_to_service_user(self):
  with tempfile.TemporaryDirectory() as tmp,patch('scheduled_backup.ROOT',Path(tmp)):
   target=host_cache_path(RESTORE_BARRIER);target.parent.mkdir(parents=True)
   target.write_text('{}');lock=target.with_name('.'+target.name+'.lock');lock.write_text('')
   store=Mock();store.space.return_value={'owner_id':'owner'}
   with patch('scheduled_backup.persist_restore_barrier',return_value={'restore_ledger_persisted':True}),patch('scheduled_backup.os.chown') as chown:
    return_restore_barrier_to_service(target)
   self.assertEqual(chown.call_args_list,[
    ((target,10001,10001),),((lock,10001,10001),),((target.parent,10001,10001),)])
   self.assertEqual(target.stat().st_mode&0o777,0o600)
   self.assertEqual(lock.stat().st_mode&0o777,0o600)
   self.assertEqual(target.parent.stat().st_mode&0o777,0o700)

if __name__=='__main__':unittest.main()
