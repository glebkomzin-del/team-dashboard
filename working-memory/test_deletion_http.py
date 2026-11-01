from http.server import ThreadingHTTPServer
import json,threading,unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from deletion_jobs import DeletionJobs
import server

OWNER={'id':'00000000-0000-4000-8000-000000000001','role':'owner'}
DELETION='20000000-0000-4000-8000-000000000001'
SOURCE='drive:fixture'


class DeletionHTTPTests(unittest.TestCase):
 def setUp(self):
  self.service=Mock();self.service.store.call.return_value=[]
  self.service.store.space.return_value={'id':'space','owner_id':OWNER['id']}
  self.settings=patch.multiple(server,JOURNAL=self.service,READ_ONLY=False,ORIGINAL_DELETION_ENABLED=True,
                               DELETION_JOBS=DeletionJobs())
  self.settings.start();self.auth=patch.object(server,'authenticate',return_value=OWNER);self.auth.start()
  self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.http.shutdown();self.http.server_close();self.thread.join(2);self.auth.stop();self.settings.stop()
 def request(self,path,data=None):
  request=Request(f'http://127.0.0.1:{self.http.server_port}'+path,data=None if data is None else json.dumps(data).encode(),
                  headers={} if data is None else {'Content-Type':'application/json'})
  try:
   with urlopen(request,timeout=3) as response:return response.status,json.load(response)
  except HTTPError as error:
   with error:return error.code,json.load(error)
 def test_owner_route_is_feature_gated_and_pollable(self):
  payload={'deletion_id':DELETION,'source_id':SOURCE}
  with patch('deletion_workflow.execute',return_value={**payload,'state':'verified','retained':['tasks','knowledge','adopted_evidence_quotes']}) as execute:
   status,result=self.request('/source-deletions',payload)
   if status==202:
    for _ in range(100):
     status,result=self.request('/source-deletions',payload)
     if status!=202:break
     threading.Event().wait(.01)
   self.assertEqual(status,200);self.assertEqual(result['state'],'verified');execute.assert_called_once()
  with patch.object(server,'ORIGINAL_DELETION_ENABLED',False):self.assertEqual(self.request('/source-deletions',payload)[0],404)
 def test_service_identity_and_read_only_mode_cannot_delete(self):
  payload={'deletion_id':DELETION,'source_id':SOURCE}
  with patch.object(server,'authenticate',return_value={'id':'service','role':'service'}):self.assertEqual(self.request('/source-deletions',payload)[0],403)
  with patch.object(server,'READ_ONLY',True):self.assertEqual(self.request('/source-deletions',payload)[0],405)
 def test_status_returns_only_public_ledger_fields(self):
  row={'deletion_id':DELETION,'source_id':SOURCE,'state':'purging','ledger_revision':4,'secret':'not returned'}
  self.service.store.call.return_value=[row]
  status,result=self.request('/source-deletions?source_id=drive%3Afixture')
  self.assertEqual(status,200);self.assertEqual(result['deletion'],{'deletion_id':DELETION,'source_id':SOURCE,'state':'purging','requested_at':None,'completed_at':None})
 def test_status_hides_verified_epoch_after_actual_reimport(self):
  self.service.store.call.return_value=[{'deletion_id':DELETION,'source_id':SOURCE,'state':'verified','ledger_revision':4,'superseded_by_reimport':True}]
  self.assertEqual(self.request('/source-deletions?source_id=drive%3Afixture'),(200,{'deletion':None}))


if __name__=='__main__':unittest.main()
