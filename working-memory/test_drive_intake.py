import copy,json,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from drive_intake import document_from_original,persist_original,FOLDERS
from memory import ValidationError
from journal_store import RevisionConflict,JournalUnavailable

class DriveIntakeTests(unittest.TestCase):
 def original(self):
  return {'source_id':'drive:fictional','event_date':'2026-09-08','title':'Test',
   'intake_status':'read_verified_not_imported','transcript':'00:01 Gleb: Ein Test mit Ä und 😀.\r\n',
   'drive_metadata':{'id':'fictional','name':'2026-09-08 Test.docx','mime_type':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','version':'2','modified_time':'2026-09-08T12:00:00Z','parents':[sorted(FOLDERS)[0]],'md5_checksum':'abc'}}
 def test_lossless_unicode_and_known_envelope(self):
  raw=self.original();row=document_from_original(raw,observed_at='2026-09-07T13:00:00Z')
  self.assertEqual(row['body'],raw['transcript']);self.assertEqual(json.loads(row['metadata_json'])['body_characters'],len(raw['transcript']))
  raw['transcript']='Transcript delivered by Tactiq.io - get it for your Google Meet today!\r\nTitel 😀\r\nTranskript:\r\n'+raw['transcript']
  row=document_from_original(raw);self.assertEqual(row['body'],self.original()['transcript'])
  self.assertEqual(row['export'],raw['transcript'])
 def test_wrong_scope_date_version_and_encoding_rejected(self):
  for change in ('folder','date','version','encoding','unverified','empty'):
   raw=self.original()
   if change=='folder':raw['drive_metadata']['parents']=['unrelated']
   elif change=='date':raw['event_date']='2026-08-01'
   elif change=='version':raw['drive_metadata']['version']=None
   elif change=='encoding':raw['transcript']='bad\ud800'
   elif change=='unverified':raw['intake_status']='guessed'
   else:raw['transcript']=' '
   with self.subTest(change=change),self.assertRaises(ValidationError):document_from_original(raw)
 def test_retry_reuses_first_observation_and_repairs_archive_enqueue_gap(self):
  raw=self.original();saved=document_from_original(raw,observed_at='2026-09-07T13:00:00Z')
  store=Mock();store.call.side_effect=[saved,{'state':'archive_only'}]
  result=persist_original(store,raw,pipeline='test')
  self.assertEqual(result['state'],'archive_only');store.archive_put.assert_called_once_with(saved)
  self.assertEqual(store.call.call_args.args,('enqueue',))
 def test_concurrent_identical_archive_write_is_reconciled_without_overwrite(self):
  raw=self.original();saved=document_from_original(raw,observed_at='2026-09-07T13:00:00Z')
  store=Mock();store.call.side_effect=[None,saved,{'state':'queued','id':'job'}]
  store.archive_put.side_effect=[RevisionConflict('race'),{'id':saved['id'],'repeated':True}]
  self.assertEqual(persist_original(store,raw,pipeline='test')['state'],'queued')
  self.assertEqual(store.archive_put.call_args.args,(saved,))
 def test_archive_failure_never_queues(self):
  store=Mock();store.call.return_value=None;store.archive_put.side_effect=JournalUnavailable('offline')
  with self.assertRaises(JournalUnavailable):persist_original(store,self.original(),pipeline='test')
  store.call.assert_called_once()

if __name__=='__main__':unittest.main()
