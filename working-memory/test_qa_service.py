from contextlib import contextmanager
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

import archive_index
from memory import apply,claim,connect,register,ValidationError
from planner import record
from qa_service import CompletionUnknown,QuestionService
from question_calls import QuestionCalls,drain_all_question_outbox
from durable_calls import OutcomeUnknown
from test_memory import TEXT,observation,proposal

OWNER={'id':'00000000-0000-4000-8000-000000000001','role':'owner'}
SPACE={'id':'10000000-0000-4000-8000-000000000001','owner_id':OWNER['id'],'revision':1,'archive_revision':0,'deletion_revision':0}
QUESTION='20000000-0000-4000-8000-000000000001'

class Store:
    space_id=SPACE['id']
    def __init__(self):self.questions={};self.calls={};self.documents={};self.snapshots={};self.sent=0
    def space(self):return dict(SPACE)
    def call(self,op,**v):
        if op=='question_begin':
            h=hashlib.sha256(v['request_json'].encode()).hexdigest();old=self.questions.get(v['question_id'])
            if old:
                if old['request_hash']!=h:raise RuntimeError('conflict')
                return {**old,'next_call_index':sum(key[0]==v['question_id'] for key in self.calls)}
            row={**v,'request_hash':h,'response_json':None};self.questions[v['question_id']]=row;return {**row,'next_call_index':0}
        if op=='question_reserve':
            key=(v['question_id'],v['call_index']);h=hashlib.sha256(v['request_json'].encode()).hexdigest()
            for row in self.calls.values():
                if row['question_id']==v['question_id'] and row['request_hash']==h:return {**row,'send':False}
            if key in self.calls:return {**self.calls[key],'send':False}
            row={**v,'request_hash':h,'response_json':None};self.calls[key]=row;return {**row,'send':True}
        if op=='question_receive':
            row=self.calls[(v['question_id'],v['call_index'])];row.update(response_json=v['response_json'],
                response_hash=hashlib.sha256(v['response_json'].encode()).hexdigest(),actual_micro_usd=v['actual_micro_usd'])
            return {'saved':True}
        if op=='question_complete':
            self.questions[v['question_id']].update(response_json=v['response_json'],response_hash=hashlib.sha256(v['response_json'].encode()).hexdigest())
            return {'saved':True}
        if op=='search_missing':return [i for i in v['document_ids'] if i not in self.documents]
        if op=='search_cached':return {}
        if op=='search_put':
            for row in v['documents']:self.documents[row['id']]=row
            return {'saved':len(v['documents'])}
        if op=='search_snapshot':self.snapshots[v['search_snapshot_id']]=v['document_ids'];return {'count':len(v['document_ids'])}
        if op=='search_query':return [self.documents[i] for i in self.snapshots[v['search_snapshot_id']]][:v['match_count']]
        raise AssertionError(op)

class Journal:
    def __init__(self,store,db,archive):self.store,self.db,self.archive=store,db,archive
    def authorize(self,identity,space):
        if identity!=OWNER:raise PermissionError
    @contextmanager
    def question_projections(self,identity,*,revision,archive_revision):
        self.authorize(identity,SPACE)
        self.assert_equal((revision,archive_revision),(SPACE['revision'],SPACE['archive_revision']))
        yield self.db,self.archive,dict(SPACE)
    def assert_equal(self,a,b):
        if a!=b:raise AssertionError((a,b))

class QuestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.db=connect(root/'memory.sqlite');self.archive=archive_index.connect(root/'archive.sqlite')
        record(self.db,command_id='30000000-0000-4000-8000-000000000001',actor_id=OWNER['id'],command={
            'action':'create_task','target_id':'40000000-0000-4000-8000-000000000001','reason':'Eigene Aufgabe',
            'event_date':'2026-09-19','patch':{'title':'Budgetbericht abschließen','owner':'Gleb Komzin','note':'Zahlen bis Freitag prüfen'}})
        self.db.commit();self.store=Store();self.sent=[]
    def tearDown(self):self.db.close();self.archive.close();self.tmp.cleanup()
    def api(self,prompt,model,max_tokens=0,schema=None):
        self.sent.append(model)
        if model=='text-embedding-3-small':
            inputs=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in inputs],
              'usage_final':True,'usage':{'input_tokens':len(inputs),'output_tokens':0}}
        return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({
          'answer':'Die manuelle Aufgabe ist offen [E001].','citation_ids':['E001'],'insufficient_evidence':False})}],
          'usage_final':True,'usage':{'input_tokens':100,'output_tokens':20,'input_tokens_details':{}}}
    def service(self):return QuestionService(Journal(self.store,self.db,self.archive),self.api,budget_micro_usd=10**9,outbox=Path(self.tmp.name)/'outbox')
    def test_manual_task_is_answered_with_server_built_navigation_and_replay(self):
        request={'request_id':QUESTION,'question':'Welche Aufgabe zum Budgetbericht ist offen?','messages':[]}
        result=self.service().answer(OWNER,request)
        self.assertEqual(result['citations'][0]['kind'],'task')
        self.assertEqual(result['citations'][0]['target'],{'page':'todos','params':{
          'task':'40000000-0000-4000-8000-000000000001','as_of':'2026-09-19'}})
        repeated=self.service().answer(OWNER,request)
        self.assertTrue(repeated['repeated']);self.assertEqual(self.sent,['text-embedding-3-small','text-embedding-3-small','gpt-5.6-terra'])
        self.assertEqual(self.store.questions[QUESTION]['deletion_revision'],0)
        self.assertEqual(self.db.execute('select count(*) from planning_events').fetchone()[0],1)

    def test_all_and_count_task_questions_use_complete_projection_without_provider(self):
        result=self.service().answer(OWNER,{'request_id':QUESTION,'question':'Wie viele offene Aufgaben gibt es?'})
        self.assertIn('1 Aufgabe',result['answer'])
        self.assertEqual(result['coverage']['mode'],'structured_tasks')
        self.assertEqual(result['coverage']['matched_tasks'],1)
        self.assertEqual(result['coverage']['task_total'],1)
        self.assertEqual(result['citations'][0]['kind'],'task_set')
        self.assertEqual(self.sent,[])

    def test_structured_task_route_rejects_filters_and_conflicting_scopes(self):
        questions=('Wie viele offene Aufgaben für den Budgetbericht gibt es?',
          'Wie viele offene Aufgaben von Anna gibt es?',
          'Wie viele Aufgaben gab es gestern?',
          'Wie viele offene und erledigte Aufgaben gibt es?')
        for index,question in enumerate(questions,1):
            with self.subTest(question=question):
                identifier=f'20000000-0000-4000-8000-{index:012d}'
                result=self.service().answer(OWNER,{'request_id':identifier,'question':question})
                self.assertEqual(result['coverage']['mode'],'retrieval')

    def test_personal_filter_is_applied_after_status_scope(self):
        result=self.service().answer(OWNER,{'request_id':QUESTION,'question':'Wie viele meiner erledigten Aufgaben gibt es?'})
        self.assertIn('0 Aufgaben',result['answer'])
        self.assertEqual(result['coverage']['mode'],'structured_tasks')
        self.assertEqual(result['coverage']['matched_tasks'],0)
        self.assertEqual(self.sent,[])

    def test_default_scope_uses_latest_archive_or_work_event_without_user_date(self):
        self.db.execute('DELETE FROM planning_events');self.db.commit()
        body='Späteres dokumentiertes Ereignis.';document='c'*64
        self.archive.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',(document,'drive:later','2026-09-18',
          '2026-09-18T10:00:00+00:00','Spätere Quelle',hashlib.sha256(body.encode()).hexdigest(),'d'*64,body,body,'{}'))
        self.archive.commit()
        result=self.service().answer(OWNER,{'request_id':QUESTION,'question':'Wie viele offene Aufgaben gibt es?'})
        self.assertEqual(result['as_of'],'2026-09-18')
        self.assertEqual(result['coverage']['latest_available_as_of'],'2026-09-18')
        self.assertTrue(result['coverage']['is_latest'])
        self.assertEqual(result['coverage']['working_sources'],0)
        self.assertEqual(result['coverage']['archived_sources'],1)
        self.assertEqual(result['coverage']['archived_only_sources'],1)

    def test_retrieval_discloses_scope_freshness_and_compacted_history(self):
        messages=[{'role':'user' if index%2==0 else 'assistant','content':f'Beitrag {index}'} for index in range(8)]
        result=self.service().answer(OWNER,{'request_id':QUESTION,'question':'Was ist offen?',
          'messages':messages,'context_omitted':3})
        coverage=result['coverage']
        self.assertEqual(coverage['mode'],'retrieval')
        self.assertEqual(coverage['context_messages'],8)
        self.assertEqual(coverage['context_omitted'],3)
        self.assertTrue(coverage['is_latest'])
        self.assertIn('documents_considered',coverage['retrieval'])

    def test_retrieval_keeps_relevant_tasks_and_archive_passages_ahead_of_irrelevant_task_mass(self):
        class Index:
            def __init__(self,*_):self.snapshot_id=None;self.document_count=0
            def persist(self,_):pass
            def search(self,*_):return [
                {'kind':'work','target_id':'task-hit'},
                {'kind':'passage','target_id':'archive-filialen','text':'Jan wandte am 18.09. gegen die Filterregel ein.',
                 'event_date':'2026-09-18','metadata':{'start':0,'title':'Filialen'}}]
        irrelevant=[('personal',{'id':f'task-irrelevant-{index}','title':'Anderes Thema','claim':'x'*12000,
            'owner':'Gleb','status':'open','last_changed':'2026-09-19'}) for index in range(40)]
        relevant=[('personal',{'id':'task-hit','title':'Aktive Filialen','claim':'Aktive Filialen prüfen',
            'owner':'Gleb','status':'open','last_changed':'2026-09-19'}),
            ('personal',{'id':'task-score','title':'Budget für Filialen','claim':'Budget und Filialen abstimmen',
             'owner':'Gleb','status':'open','last_changed':'2026-09-19'})]
        snapshot={'as_of':'2026-09-19','sources':[]}
        with patch('qa_service.SearchIndex',Index),patch('qa_service.search_documents',return_value=[]):
            evidence,coverage=self.service()._evidence(self.db,self.archive,snapshot,'aktive Filialen',None,irrelevant+relevant)
        self.assertEqual([row['label'] for row in evidence.rows if row['kind']=='task'],['Aktive Filialen','Budget für Filialen'])
        self.assertIn('archive_source',[row['kind'] for row in evidence.rows])
        self.assertEqual(coverage['task_candidates_omitted'],0)
        self.assertFalse(coverage['evidence_bytes_truncated'])
    def test_model_cannot_create_a_source_link(self):
        generated=[]
        def bad(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                inputs=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in inputs],
                  'usage_final':True,'usage':{'input_tokens':len(inputs),'output_tokens':0}}
            generated.append(True)
            return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({
              'answer':'Belegt [E001], angeblich auch [E999].','citation_ids':['E001'],'insufficient_evidence':False})}],
              'usage_final':True,'usage':{'input_tokens':1,'output_tokens':1,'input_tokens_details':{}}}
        service=QuestionService(Journal(self.store,self.db,self.archive),bad,budget_micro_usd=10**9,outbox=Path(self.tmp.name)/'outbox')
        request={'request_id':QUESTION,'question':'Was ist offen?'}
        with self.assertRaises(ValidationError):service.answer(OWNER,request)
        with self.assertRaises(ValidationError):service.answer(OWNER,request)
        self.assertEqual(len(generated),2)
    def test_uncertain_terminal_receipt_replays_provider_calls_without_resend(self):
        original=self.store.call;fail={'once':True};generated=[]
        def uncertain(op,**values):
            if op=='question_complete' and fail['once']:
                fail['once']=False
                return {'saved':False}
            return original(op,**values)
        self.store.call=uncertain
        def bad(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                values=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in values],
                  'usage_final':True,'usage':{'input_tokens':len(values),'output_tokens':0}}
            generated.append(True)
            return {'stop_reason':'end_turn','content':[{'type':'text','text':'{}'}],
              'usage_final':True,'usage':{'input_tokens':1,'output_tokens':1,'input_tokens_details':{}}}
        service=QuestionService(Journal(self.store,self.db,self.archive),bad,budget_micro_usd=10**9,outbox=Path(self.tmp.name)/'outbox')
        request={'request_id':QUESTION,'question':'Was ist offen?'}
        with self.assertRaises(CompletionUnknown):service.answer(OWNER,request)
        with self.assertRaises(ValidationError):service.answer(OWNER,request)
        self.assertEqual(len(generated),2)
    def test_non_json_answer_is_terminal_and_not_resent(self):
        generated=[]
        def invalid(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                values=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in values],
                  'usage_final':True,'usage':{'input_tokens':len(values),'output_tokens':0}}
            generated.append(True)
            return {'stop_reason':'end_turn','content':[{'type':'text','text':'not-json'}],
              'usage_final':True,'usage':{'input_tokens':1,'output_tokens':1,'input_tokens_details':{}}}
        service=QuestionService(Journal(self.store,self.db,self.archive),invalid,budget_micro_usd=10**9,outbox=Path(self.tmp.name)/'outbox')
        request={'request_id':QUESTION,'question':'Was ist offen?'}
        with self.assertRaises(ValidationError):service.answer(OWNER,request)
        with self.assertRaises(ValidationError):service.answer(OWNER,request)
        self.assertEqual(len(generated),2)
    def test_working_and_archive_citations_use_canonical_open_targets(self):
        job=register(self.db,source_id='drive:meeting',event_date='2026-09-18',title='Statusmeeting',transcript=TEXT)
        apply(self.db,job,claim(self.db,job),proposal(observation()),model='fixture');self.db.commit()
        body='Im historischen Original wurde die Budgetfreigabe ausdrücklich besprochen.';document='a'*64
        self.archive.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',(document,'drive:archive','2026-09-17','2026-09-18T10:00:00+00:00','Budgethistorie',hashlib.sha256(body.encode()).hexdigest(),'b'*64,body,body,'{}'))
        cursor=self.archive.execute('INSERT INTO passages(document_id,ordinal,start,end,text,title) VALUES (?,?,?,?,?,?)',(document,0,0,len(body),body,'Budgethistorie'))
        self.archive.execute('INSERT INTO passage_search(rowid,text,title) VALUES (?,?,?)',(cursor.lastrowid,body,'Budgethistorie'));self.archive.commit()
        def choose(kind):
            def provider(prompt,model,max_tokens=0,schema=None):
                if model=='text-embedding-3-small':
                    inputs=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in inputs],
                      'usage_final':True,'usage':{'input_tokens':len(inputs),'output_tokens':0}}
                rows=json.loads(prompt.split('\nEVIDENZ:\n',1)[1]);identifier=next(row['id'] for row in rows if row['kind']==kind)
                return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({'answer':f'Belegt [{identifier}].','citation_ids':[identifier],'insufficient_evidence':False})}],
                  'usage_final':True,'usage':{'input_tokens':100,'output_tokens':20,'input_tokens_details':{}}}
            return provider
        working=QuestionService(Journal(self.store,self.db,self.archive),choose('working_source'),budget_micro_usd=10**9,outbox=Path(self.tmp.name)/'outbox')
        result=working.answer(OWNER,{'request_id':'50000000-0000-4000-8000-000000000001','question':'Was wurde im Statusmeeting zugesagt?'})
        self.assertEqual(result['citations'][0]['target']['page'],'wissen');self.assertIn('source',result['citations'][0]['target']['params'])
        archived=QuestionService(Journal(self.store,self.db,self.archive),choose('archive_source'),budget_micro_usd=10**9,outbox=Path(self.tmp.name)/'outbox')
        result=archived.answer(OWNER,{'request_id':'60000000-0000-4000-8000-000000000001','question':'Was steht historisch zur Budgetfreigabe?'})
        self.assertEqual(result['citations'][0]['target'],{'page':'archiv','params':{
          'meeting':document,'meeting_view':'original','as_of':'2026-09-19'}})
    def test_service_identity_is_rejected_before_provider(self):
        with self.assertRaises(PermissionError):self.service().answer({'role':'service','id':'n8n'},{'request_id':QUESTION,'question':'Was ist offen?'})
        self.assertEqual(self.sent,[])
    def test_request_shape_date_and_completed_hash_fail_closed(self):
        service=self.service()
        for request in ({'request_id':QUESTION},{'request_id':7,'question':'Was ist offen?'},
          {'request_id':QUESTION,'question':'Was ist offen?','as_of':'20260919'}):
            with self.subTest(request=request),self.assertRaises((ValidationError,ValueError)):service.answer(OWNER,request)
        request={'request_id':QUESTION,'question':'Was ist offen?'}
        service.answer(OWNER,request);self.store.questions[QUESTION]['response_hash']='0'*64
        with self.assertRaises(ValidationError):service.answer(OWNER,request)
    def test_user_history_supplies_followup_retrieval_context(self):
        seen=[]
        def provider(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                values=json.loads(prompt);seen.extend(values)
                return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in values],
                  'usage_final':True,'usage':{'input_tokens':len(values),'output_tokens':0}}
            return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({
              'answer':'Die Aufgabe ist belegt [E001].','citation_ids':['E001'],'insufficient_evidence':False})}],
              'usage_final':True,'usage':{'input_tokens':1,'output_tokens':1,'input_tokens_details':{}}}
        service=QuestionService(Journal(self.store,self.db,self.archive),provider,budget_micro_usd=10**9,outbox=Path(self.tmp.name)/'outbox')
        service.answer(OWNER,{'request_id':QUESTION,'question':'Und wer ist dafür zuständig?','messages':[
          {'role':'user','content':'Wie steht es um den Budgetbericht?'},{'role':'assistant','content':'Unbelegte Zukunftsbehauptung'}]})
        self.assertTrue(any('Budgetbericht' in value and 'zuständig' in value for value in seen))
        self.assertFalse(any('Zukunftsbehauptung' in value for value in seen))
    def test_provider_result_is_not_resent_after_uncertain_receipt(self):
        original=self.store.call;failed={'once':False};sent=[]
        def uncertain(op,**values):
            if op=='question_receive' and not failed['once']:
                failed['once']=True
                return {'saved':False}
            return original(op,**values)
        self.store.call=uncertain
        def provider(*args,**kwargs):
            sent.append(True)
            return {'stop_reason':'end_turn','content':[{'type':'text','text':'{}'}],
              'usage_final':True,'usage':{'input_tokens':1,'output_tokens':1,'input_tokens_details':{}}}
        calls=QuestionCalls(self.store,question_id=QUESTION,actor_id=OWNER['id'],api=provider,
          outbox=Path(self.tmp.name)/'outbox',budget_micro_usd=10**9)
        with self.assertRaises(OutcomeUnknown):calls('Frage','gpt-5.6-terra',max_tokens=10,schema={'type':'object'})
        self.assertEqual(len(sent),1)
        self.assertEqual(drain_all_question_outbox(self.store,Path(self.tmp.name)/'outbox'),1)
        replay=QuestionCalls(self.store,question_id=QUESTION,actor_id=OWNER['id'],api=provider,
          outbox=Path(self.tmp.name)/'outbox',budget_micro_usd=10**9)
        self.assertEqual(replay('Frage','gpt-5.6-terra',max_tokens=10,schema={'type':'object'})['stop_reason'],'end_turn')
        self.assertEqual(len(sent),1)

    def test_unlimited_budget_is_forwarded_as_null_without_changing_accounting(self):
        def provider(*_args,**_kwargs):
            return {'stop_reason':'end_turn','content':[{'type':'text','text':'{}'}],
              'usage_final':True,'usage':{'input_tokens':2,'output_tokens':1,'input_tokens_details':{}}}
        calls=QuestionCalls(self.store,question_id=QUESTION,actor_id=OWNER['id'],api=provider,
          outbox=Path(self.tmp.name)/'outbox',budget_micro_usd=None)
        calls('Frage','gpt-5.6-terra',max_tokens=10,schema={'type':'object'})
        row=self.store.calls[(QUESTION,0)]
        self.assertIsNone(row['budget_micro_usd']);self.assertGreater(row['reserved_micro_usd'],0)

if __name__=='__main__':unittest.main()
