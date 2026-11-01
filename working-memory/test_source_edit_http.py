from unittest.mock import patch
from journal_service import JournalService
import test_job_recovery_http as recovery_fixture
import test_source_edit as edit_fixture
from test_source_edit import EditStore,OWNER,REVIEW
import server

class SourceEditHTTPTests(recovery_fixture.RecoveryHTTPTests):
 def setUp(self):
  super().setUp();self.store=EditStore();self.service=JournalService(self.store,self.tmp.name);server.JOURNAL=self.service
 def test_source_editor_http_is_owner_only_staging_and_readonly_aware(self):
  path='/source-edits/jobs/'+self.store.job['id']
  request={'job_id':self.store.job['id'],'review_id':REVIEW,'expected_revision':0,'expected_updated_at':self.store.job['updated_at'],
   'reason':'Originalstelle manuell geprüft','observations':[edit_fixture.SourceEditTests.observation(None)],'identity_links':[],'topic_links':[]}
  with patch('processor.anthropic') as api:
   code,detail=self.request(path);self.assertEqual(code,200);self.assertTrue(detail['can_edit']);self.assertNotIn('lease_token',detail)
   for identity in (None,{'role':'service'},{**OWNER,'id':'other'}):
    with patch.object(server,'authenticate',return_value=identity):
     self.assertEqual(self.request(path)[0],401 if identity is None else 403)
     self.assertEqual(self.request('/source-edits',request)[0],401 if identity is None else 403)
   with patch.object(server,'READ_ONLY',True):self.assertEqual(self.request('/source-edits',request)[0],405)
   self.assertEqual(self.request('/source-edits',{**request,'expected_revision':4})[0],409)
   self.assertEqual(self.request('/source-edits',{**request,'actor_id':'forged'})[0],400)
   self.assertEqual(self.request('/source-edits',request)[0],200);self.assertEqual(self.store.revision,0);api.assert_not_called()
