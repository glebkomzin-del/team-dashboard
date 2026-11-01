import gzip,io,json,unittest
from unittest.mock import patch
from urllib.error import HTTPError
from gateway_journal import GatewayJournal,JournalUnavailable,RevisionConflict,TransientGateway

class SearchRetryTests(unittest.TestCase):
 def test_compressed_export_is_lossless_and_requested(self):
  value={'body':'Änderung 🧾 '*1000,'ids':['a'*64]*32}
  response=io.BytesIO(gzip.compress(json.dumps(value,ensure_ascii=False).encode()))
  response.headers={'Content-Encoding':'gzip'}
  with patch('gateway_journal.urlopen',return_value=response) as send:
   self.assertEqual(self.store().call('backup_page',after=0),value)
   self.assertEqual(send.call_args.args[0].get_header('Accept-encoding'),'gzip')
 def test_corrupt_compression_never_becomes_success(self):
  response=io.BytesIO(b'not-gzip');response.headers={'Content-Encoding':'gzip'}
  with patch('gateway_journal.urlopen',return_value=response):
   with self.assertRaises(JournalUnavailable):self.store().call('backup_page',after=0)
 def test_compressed_error_preserves_safe_diagnostic(self):
  error=HTTPError('https://example',503,'failed',{'Content-Encoding':'gzip'},io.BytesIO(gzip.compress(b'{"code":"57014","message":"private detail"}')))
  with patch('gateway_journal.urlopen',side_effect=error):
   with self.assertRaises(TransientGateway) as caught:self.store().call('backup_begin')
   self.assertEqual(caught.exception.diagnostic['http_status'],503)
   self.assertEqual(caught.exception.diagnostic['sqlstate'],'57014')
   self.assertEqual(caught.exception.diagnostic['op'],'backup_begin')
   self.assertNotIn('private detail',str(caught.exception))
 def store(self):return GatewayJournal('https://example.supabase.co','public','a'*64,'96a2dc44-9b9e-4644-b236-c5c1956cd39d')
 def test_retry_keeps_identical_search_document_and_never_calls_model(self):
  requests=[]
  def send(req,**kw):
   requests.append(req.data)
   if len(requests)==1:raise TimeoutError('synthetic temporary timeout')
   return io.BytesIO(b'{"saved":1}')
  with patch('gateway_journal.urlopen',side_effect=send),patch('gateway_journal.time.sleep'):
   self.assertEqual(self.store().call('search_put',documents=[{'id':'same','text':'same'}]),{'saved':1})
  self.assertEqual(len(requests),2);self.assertEqual(requests[0],requests[1])
 def test_pinned_backup_read_retries_same_cursor_without_duplicate_rows(self):
  requests=[]
  def send(req,**kw):
   requests.append(json.loads(req.data))
   if len(requests)==1:raise TimeoutError('temporary read failure')
   return io.BytesIO(b'[{"sequence":33}]')
  with patch('gateway_journal.urlopen',side_effect=send),patch('gateway_journal.time.sleep'):
   self.assertEqual(self.store().call('backup_page',snapshot_id='fixed',after=32),[{'sequence':33}])
  self.assertEqual(requests[0],requests[1]);self.assertEqual(len(requests),2)
 def test_pipeline_reads_retry_and_report_redacted_attempt_count(self):
  for op in ('space','archive_document','processing_status','job_detail'):
   with patch('gateway_journal.urlopen',side_effect=TimeoutError('private endpoint detail')) as send,patch('gateway_journal.time.sleep'):
    with self.assertRaises(TransientGateway) as caught:self.store().call(op)
    self.assertEqual(send.call_count,3);self.assertEqual(caught.exception.diagnostic['attempts'],3)
    self.assertEqual(caught.exception.diagnostic['type'],'network');self.assertNotIn('private',str(caught.exception))
 def test_search_retry_is_bounded_and_other_mutations_are_single_shot(self):
  for op,expected in [('search_query',3),('reserve_call',1),('receive_call',1),('append',1),('publish_job',1)]:
   with patch('gateway_journal.urlopen',side_effect=TimeoutError()),patch('gateway_journal.time.sleep') as sleep:
    with self.assertRaises(JournalUnavailable):self.store().call(op)
    self.assertEqual(sleep.call_count,expected-1)
 def test_validation_and_revision_errors_are_not_retried(self):
  for status,expected in [(400,ValueError),(401,JournalUnavailable),(409,RevisionConflict)]:
   error=HTTPError('https://example',status,'failed',{},io.BytesIO(b'{}'))
   with patch('gateway_journal.urlopen',side_effect=error) as send,patch('gateway_journal.time.sleep'):
    with self.assertRaises(expected):self.store().call('search_put')
    self.assertEqual(send.call_count,1)
