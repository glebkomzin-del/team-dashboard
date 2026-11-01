from http.server import ThreadingHTTPServer
import json,tempfile,threading,unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from journal_service import JournalService
from test_job_recovery import RecoveryStore,OWNER,COMMAND
import server

class RecoveryHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=RecoveryStore();self.service=JournalService(self.store,self.tmp.name)
  self.settings=patch.multiple(server,JOURNAL=self.service,DB='/missing-legacy-db',READ_ONLY=False);self.settings.start()
  self.auth=patch.object(server,'authenticate',return_value=OWNER);self.auth.start()
  self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.http.shutdown();self.http.server_close();self.thread.join(timeout=2);self.auth.stop();self.settings.stop();self.tmp.cleanup()
 def request(self,path,data=None):
  req=Request(f'http://127.0.0.1:{self.http.server_port}'+path,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json'})
  try:
   with urlopen(req,timeout=3) as r:return r.status,json.load(r)
  except HTTPError as e:
   with e:return e.code,json.load(e)
 def test_owner_get_and_post_keep_service_and_other_accounts_out(self):
  path='/operations/jobs/'+self.store.job['id']+'?command_id='+COMMAND
  with patch('processor.anthropic') as api:
   status,detail=self.request(path);self.assertEqual(status,200);self.assertTrue(detail['can_retry']);self.assertNotIn('lease_token',detail)
   req={k:detail[k] for k in ('job_id','command_id','expected_revision','expected_updated_at')};req.update(action='retry',reason='Reviewed transport error',preview_hash=None)
   for identity in (None,{'role':'service'},{**OWNER,'id':'other'}):
    with patch.object(server,'authenticate',return_value=identity):
     self.assertEqual(self.request(path)[0],401 if identity is None else 403)
     self.assertEqual(self.request('/operations/decisions',req)[0],401 if identity is None else 403)
   self.assertEqual(self.request('/operations/decisions',{**req,'expected_revision':4})[0],409)
   self.assertEqual(self.request('/operations/decisions',{**req,'actor_id':'forged'})[0],400)
   self.assertEqual(self.request('/operations/decisions',req)[0],200)
   self.assertEqual(len(self.store.resolved),1);api.assert_not_called()

if __name__=='__main__':unittest.main()
