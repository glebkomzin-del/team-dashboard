from http.server import ThreadingHTTPServer
import json,threading,unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

import server
from question_jobs import QuestionJobs

OWNER={'id':'00000000-0000-4000-8000-000000000001','role':'owner'}
QUESTION='20000000-0000-4000-8000-000000000001'

class QuestionHTTPTests(unittest.TestCase):
    def test_question_budget_accepts_explicit_unlimited_or_positive_integer(self):
        self.assertIsNone(server.question_budget('unlimited'));self.assertEqual(server.question_budget('2500000'),2500000)
        for value in ('','0','-1','none'):
            with self.subTest(value=value),self.assertRaises(ValueError):server.question_budget(value)
    def setUp(self):
        self.service=Mock();self.service.answer.return_value={'request_id':QUESTION,'answer':'Belegt [E001].','as_of':'2026-09-19',
          'revision':1,'archive_revision':2,'repeated':False,'citations':[]}
        self.conversations=Mock();self.conversations.create.return_value={'conversation':{'conversation_id':QUESTION,'title':'Neues Gespräch'},'repeated':False}
        self.conversations.list.return_value={'conversations':[]};self.conversations.get.return_value={'conversation':{'conversation_id':QUESTION},'messages':[]}
        self.settings=patch.multiple(server,QA_ENABLED=True,QUESTION_SERVICE=self.service,CONVERSATIONS=self.conversations,QUESTION_JOBS=QuestionJobs(),READ_ONLY=True,JOURNAL=Mock())
        self.settings.start();self.auth=patch.object(server,'authenticate',return_value=OWNER);self.auth.start()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(timeout=2);self.auth.stop();self.settings.stop()
    def post(self,value,path='/questions'):
        request=Request(f'http://127.0.0.1:{self.http.server_port}{path}',data=json.dumps(value).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=3) as result:return result.status,json.load(result)
        except HTTPError as error:
            with error:return error.code,json.load(error)
    def get(self,path):
        request=Request(f'http://127.0.0.1:{self.http.server_port}{path}')
        try:
            with urlopen(request,timeout=3) as result:return result.status,json.load(result)
        except HTTPError as error:
            with error:return error.code,json.load(error)
    def completed(self,value):
        first=self.post(value)
        if first[0]!=202:return first
        self.assertEqual(first,(202,{'state':'processing','request_id':value['request_id']}))
        for _ in range(100):
            result=self.post(value)
            if result[0]!=202:return result
            threading.Event().wait(.01)
        self.fail('Question did not complete')
    def test_long_question_returns_pollable_processing_state(self):
        with patch.object(server.QUESTION_JOBS,'submit',return_value={'state':'processing','request_id':QUESTION}) as submit:
            status,result=self.post({'request_id':QUESTION,'question':'Was ist offen?'})
        self.assertEqual((status,result),(202,{'state':'processing','request_id':QUESTION}))
        self.assertEqual(submit.call_args.kwargs,{'wait_seconds':20})
    def test_enabled_question_is_owner_only_even_in_read_only_mode(self):
        payload={'request_id':QUESTION,'question':'Was ist offen?'}
        self.assertEqual(self.completed(payload)[0],200)
        with patch.object(server,'authenticate',return_value={'role':'service','id':'n8n'}):self.assertEqual(self.post(payload)[0],403)
        with patch.object(server,'authenticate',return_value=None):self.assertEqual(self.post(payload)[0],401)
        self.service.answer.assert_called_once_with(OWNER,payload)
    def test_feature_is_off_by_default_boundary(self):
        with patch.object(server,'QA_ENABLED',False):
            status,result=self.post({'request_id':QUESTION,'question':'Was ist offen?'})
        self.assertEqual(status,405);self.assertEqual(result['code'],'questions_disabled');self.service.answer.assert_not_called()
    def test_invalid_and_unknown_provider_results_are_explicit(self):
        from durable_calls import OutcomeUnknown
        self.service.answer.side_effect=ValueError('bad')
        self.assertEqual(self.completed({'request_id':QUESTION,'question':'x'})[1]['code'],'invalid_question')
        self.service.answer.side_effect=OutcomeUnknown('unknown')
        status,result=self.completed({'request_id':QUESTION,'question':'x'})
        self.assertEqual(status,503);self.assertEqual(result,{'error':'Provider outcome unknown; the same request will not be sent again','code':'provider_outcome_unknown','retryable':False})

    def test_unverified_answer_has_a_distinct_error_code(self):
        from qa_service import AnswerUnverified
        self.service.answer.side_effect=AnswerUnverified('not grounded')
        status,result=self.completed({'request_id':QUESTION,'question':'Welche Entscheidungen sind aktuell festgehalten?'})
        self.assertEqual(status,422)
        self.assertEqual(result,{'error':'Answer could not be sufficiently grounded','code':'answer_unverified','retryable':False})

    def test_conversation_contract_is_owner_scoped_and_question_remains_compatible(self):
        self.assertEqual(self.post({'conversation_id':QUESTION},'/conversations')[0],201)
        self.assertEqual(self.get('/conversations'),(200,{'conversations':[]}))
        self.assertEqual(self.get('/conversations/'+QUESTION)[0],200)
        payload={'request_id':QUESTION,'question':'Was ist offen?','conversation_id':QUESTION}
        self.assertEqual(self.completed(payload)[0],200)
        self.service.answer.assert_called_once_with(OWNER,payload)
        with patch.object(server,'authenticate',return_value={'role':'service','id':'n8n'}):
            self.assertEqual(self.get('/conversations')[0],403)

    def test_memory_action_and_coverage_contract_passes_through_http(self):
        action='30000000-0000-4000-8000-000000000001';memory='40000000-0000-4000-8000-000000000001'
        self.service.answer.return_value={
          'request_id':QUESTION,'answer':'Gespeichert: Exportregel.','as_of':'2026-09-20',
          'revision':2,'archive_revision':1,'repeated':False,'citations':[],
          'memory_actions':[{'action_id':action,'status':'applied','kind':'create_memory','target_id':memory,
            'receipt':{'command_id':action,'revision':2,'repeated':False}}],
          'coverage':{'mode':'memory_write','as_of':'2026-09-20','latest_available_as_of':'2026-09-20',
            'is_latest':True,'working_sources':1,'archived_sources':1,'archived_only_sources':0,
            'pending_jobs':0,'task_total':1,'matched_tasks':None,'context_messages':0,
            'context_omitted':0,'output_truncated':False,'retrieval':None}}
        status,result=self.completed({'request_id':QUESTION,'question':'Merke dir: Der Export wird freitags geprüft.'})
        self.assertEqual(status,200)
        self.assertEqual(result['coverage']['mode'],'memory_write')
        self.assertEqual(result['memory_actions'][0]['action_id'],action)
        self.assertEqual(result['memory_actions'][0]['receipt']['command_id'],action)

if __name__=='__main__':unittest.main()
