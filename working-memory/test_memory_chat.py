import json,unittest
from uuid import uuid4

from human_decisions import record
from memory_chat import ConversationService,ConversationNotFound
from memory_chat_query import PLAN_SCHEMA,plan as plan_query,prepare_action
from qa_service import ANSWER_SCHEMA,AnswerUnverified,CompletionUnknown,QuestionService,_decoded
from memory import ValidationError
from review_api import review
from hybrid_index import documents as search_documents
from test_qa_service import OWNER,QUESTION,Journal,Store


def planned(**changes):
    value={'intent':'answer','scope':'targeted','search_queries':['Budgetbericht'],'people':[],'topics':[],
      'task_status':'all','date_from':'','date_to':'','explicit_write':False,'write_operation':'none',
      'write_target':'','write_title':'','write_owner':'','write_due_date':'','write_claim':'','write_status':'none'}
    value.update(changes);return value


class ActionJournal(Journal):
    def __init__(self,*args):
        super().__init__(*args);self.commands={};self.decisions=0;self.store.command=self.commands.get

    def decide(self,identity,request):
        self.decisions+=1
        self.authorize(identity,self.store.space())
        command={k:request[k] for k in ('action','target_id','reason','patch')}|{'event_date':'2026-09-20'}
        record(self.db,command_id=request['command_id'],actor_id=identity['id'],command=command);self.db.commit()
        receipt={'revision':request['expected_revision']+1,'repeated':False}
        self.commands[request['command_id']]={**receipt,'kind':'human','actor_id':identity['id'],'payload':command}
        return receipt


class MemoryChatQueryTests(unittest.TestCase):
    def setUp(self):
        from test_qa_service import QuestionServiceTests
        self.fixture=QuestionServiceTests();self.fixture.setUp()

    def tearDown(self):self.fixture.tearDown()

    def provider(self,plan_value,answer='Belegt [E001].'):
        def call(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                values=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in values],
                  'usage_final':True,'usage':{'input_tokens':len(values),'output_tokens':0}}
            if schema==PLAN_SCHEMA:
                value=plan_value
            else:value={'answer':answer,'citation_ids':['E001'],'insufficient_evidence':False}
            return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(value)}],
              'usage_final':True,'usage':{'input_tokens':10,'output_tokens':5,'input_tokens_details':{}}}
        return call

    def service(self,plan_value,journal=None):
        return QuestionService(journal or Journal(self.fixture.store,self.fixture.db,self.fixture.archive),
          self.provider(plan_value),budget_micro_usd=10**9,outbox=self.fixture.tmp.name+'/outbox')

    def test_natural_person_task_question_filters_complete_projection(self):
        record(self.fixture.db,command_id=str(uuid4()),actor_id=OWNER['id'],command={'action':'create_task',
          'target_id':str(uuid4()),'reason':'Sebastians Aufgabe','event_date':'2026-09-19',
          'patch':{'title':'Lieferantenrisiko prüfen','owner':'Sebastian Krüger'}});self.fixture.db.commit()
        result=self.service(planned(intent='tasks',people=['Sebastian'],task_status='all',search_queries=[])).answer(
          OWNER,{'request_id':QUESTION,'question':'Welche Aufgaben hat Sebastian?'})
        self.assertEqual(result['coverage']['mode'],'planned_tasks')
        self.assertEqual(result['coverage']['matched_tasks'],1)
        self.assertIn('Lieferantenrisiko',result['answer']);self.assertNotIn('Budgetbericht',result['answer'])

    def test_global_risk_question_uses_multiple_rounds_without_claiming_completeness(self):
        value=planned(scope='global',search_queries=['offene Risiken Projekte','Abhängigkeiten und Blocker'])
        result=self.service(value).answer(OWNER,{'request_id':QUESTION,
          'question':'Welche offenen Risiken haben wir projektübergreifend?'})
        retrieval=result['coverage']['retrieval']
        self.assertEqual(retrieval['scope'],'global');self.assertEqual(retrieval['search_rounds'],2)
        self.assertTrue(retrieval['overview']['incremental_content_hash_cache'])
        self.assertIn('source_snapshot_id',retrieval['overview'])

    def test_unqualified_inventory_question_is_prompted_as_global(self):
        seen=[]
        def provider(prompt,*_args,**_kwargs):
            seen.append(prompt)
            return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(
              planned(scope='global',search_queries=['festgehaltene Entscheidungen','aktuelle Beschlüsse']))}]}
        result=plan_query(provider,'Welche Entscheidungen sind aktuell festgehalten?',[],'2026-09-20','test-model')
        self.assertEqual(result['scope'],'global')
        self.assertIn('Unqualifizierte Übersichts- oder Bestandsfragen',seen[0])

    def test_conversationless_overview_enters_global_planner_route(self):
        value=planned(scope='global',search_queries=['gespeichertes Wissen','aktuelle Festlegungen'])
        result=self.service(value).answer(OWNER,{'request_id':QUESTION,'question':'Was wissen wir?'})
        retrieval=result['coverage']['retrieval']
        self.assertEqual(result['coverage']['context_messages'],0)
        self.assertEqual(retrieval['scope'],'global')
        self.assertEqual(retrieval['search_rounds'],2)

    def test_change_since_date_builds_a_time_bounded_search_snapshot(self):
        value=planned(search_queries=['Budgetbericht Veränderungen'],date_from='2026-09-01',date_to='2026-09-19')
        result=self.service(value).answer(OWNER,{'request_id':QUESTION,'question':'Wie hat sich der Budgetbericht seit September verändert?'})
        self.assertEqual(result['coverage']['retrieval']['time_range'],{'from':'2026-09-01','to':'2026-09-19'})

    def test_explicit_completion_writes_once_but_hypothetical_question_does_not(self):
        journal=ActionJournal(self.fixture.store,self.fixture.db,self.fixture.archive)
        write=planned(intent='write',explicit_write=True,write_operation='update_task',
          write_target='Budgetbericht abschließen',write_status='done')
        result=self.service(write,journal).answer(OWNER,{'request_id':QUESTION,
          'question':'Die Aufgabe Budgetbericht abschließen ist erledigt.'})
        self.assertEqual(result['memory_actions'][0]['status'],'applied')
        self.assertEqual(result['memory_actions'][0]['kind'],'update_task')
        self.assertEqual(result['memory_actions'][0]['action_id'],result['memory_actions'][0]['receipt'].get('command_id',result['memory_actions'][0]['action_id']))
        self.assertEqual(len(self.fixture.db.execute("select 1 from planning_events where json_extract(data_json,'$.action')='update_task'").fetchall()),1)
        second=str(uuid4())
        result=self.service(write,journal).answer(OWNER,{'request_id':second,
          'question':'Könntest du die Aufgabe Budgetbericht abschließen als erledigt markieren?'})
        self.assertEqual(result['memory_actions'],[])
        self.assertEqual(len(self.fixture.db.execute("select 1 from planning_events where json_extract(data_json,'$.action')='update_task'").fetchall()),1)

    def test_explicit_user_memory_is_provenance_bound_searchable_and_deletable(self):
        journal=ActionJournal(self.fixture.store,self.fixture.db,self.fixture.archive)
        create=planned(intent='write',explicit_write=True,write_operation='create_memory',
          write_title='Exportregel',write_claim='Der Export wird freitags geprüft.')
        result=self.service(create,journal).answer(OWNER,{'request_id':QUESTION,
          'question':'Merke dir: Der Export wird freitags geprüft.'})
        action=result['memory_actions'][0];self.assertEqual((action['status'],action['kind']),('applied','create_memory'))
        snapshot=review(self.fixture.db);memory=next(item for item in snapshot['knowledge'] if item['id']==action['target_id'])
        self.assertEqual(memory['data']['provenance']['kind'],'explicit_user_memory')
        docs=[row for row in search_documents(self.fixture.db,{'meeting_date':'2026-09-21'}) if row['target_id']==action['target_id']]
        self.assertEqual(len(docs),1);self.assertTrue(docs[0]['metadata']['user_memory'])
        self.assertEqual(docs[0]['metadata']['quotes'],['Der Export wird freitags geprüft.'])
        evidence,_=self.service(planned())._evidence(self.fixture.db,self.fixture.archive,snapshot,
          'Export freitags',self.provider(planned()),tasks=[])
        cited=next(row for row in evidence.rows if row['kind']=='user_memory')
        self.assertTrue(cited['label'].startswith('Nutzernotiz:'));self.assertEqual(cited['target']['params']['knowledge'],action['target_id'])

        record(self.fixture.db,command_id=str(uuid4()),actor_id=OWNER['id'],command={'action':'update_memory',
          'target_id':action['target_id'],'reason':'Explizite Korrektur','event_date':'2026-09-21',
          'patch':{'claim':'Der Export wird montags geprüft.'}})
        record(self.fixture.db,command_id=str(uuid4()),actor_id=OWNER['id'],command={'action':'delete_memory',
          'target_id':action['target_id'],'reason':'Explizit vergessen','event_date':'2026-09-22','patch':{}});self.fixture.db.commit()
        self.assertFalse(any(item['id']==action['target_id'] for item in review(self.fixture.db)['knowledge']))
        self.assertFalse(any(row['target_id']==action['target_id'] for row in search_documents(self.fixture.db,{'meeting_date':'2026-09-23'})))

    def _lost_completion_replays_existing_memory_action(self,operation,question,**plan_fields):
        target=str(uuid4())
        record(self.fixture.db,command_id=str(uuid4()),actor_id=OWNER['id'],command={'action':'create_memory',
          'target_id':target,'reason':'Vorhandene Nutzernotiz','event_date':'2026-09-20',
          'patch':{'title':'Exportregel','claim':'Der Export wird freitags geprüft.'}});self.fixture.db.commit()
        journal=ActionJournal(self.fixture.store,self.fixture.db,self.fixture.archive)
        value=planned(intent='write',explicit_write=True,write_operation=operation,
          write_target='Exportregel',**plan_fields)
        original=self.fixture.store.call;failed={'once':False}
        def uncertain(op,**fields):
            if op=='question_complete' and not failed['once']:
                failed['once']=True;return {'saved':False}
            return original(op,**fields)
        self.fixture.store.call=uncertain
        service=self.service(value,journal)
        with self.assertRaises(CompletionUnknown):
            service.answer(OWNER,{'request_id':QUESTION,'question':question})
        first=review(self.fixture.db)
        result=service.answer(OWNER,{'request_id':QUESTION,'question':question})
        action=result['memory_actions'][0]
        self.assertEqual((action['status'],action['kind'],action['target_id']),('applied',operation,target))
        self.assertTrue(action['receipt']['repeated']);self.assertEqual(action['receipt']['command_id'],action['action_id'])
        self.assertEqual(journal.decisions,1)
        return first,review(self.fixture.db),result

    def test_lost_completion_ack_replays_renamed_memory_update(self):
        first,second,_=self._lost_completion_replays_existing_memory_action('update_memory',
          'Ändere die Nutzernotiz Exportregel in Abrechnungskalender.',
          write_title='Abrechnungskalender',write_claim='Der Export wird montags geprüft.')
        for snapshot in (first,second):
            memory=next(item for item in snapshot['knowledge'] if item['data'].get('provenance',{}).get('kind')=='explicit_user_memory')
            self.assertEqual((memory['data']['title'],memory['data']['claim']),
              ('Abrechnungskalender','Der Export wird montags geprüft.'))

    def test_lost_completion_ack_replays_deleted_memory(self):
        first,second,result=self._lost_completion_replays_existing_memory_action('delete_memory',
          'Lösche die Nutzernotiz Exportregel.')
        self.assertEqual(result['answer'],'Gelöscht: Exportregel.')
        for snapshot in (first,second):
            self.assertFalse(any(item['data'].get('provenance',{}).get('kind')=='explicit_user_memory'
              for item in snapshot['knowledge']))

    def test_ambiguous_write_returns_clarification_without_mutation(self):
        prepared=prepare_action(QUESTION,'Markiere die Aufgabe als erledigt.',planned(intent='write',explicit_write=True,
          write_operation='update_task',write_target='Aufgabe',write_status='done'),{
            'personal':[{'id':'a','title':'Aufgabe Alpha'},{'id':'b','title':'Aufgabe Beta'}]})
        self.assertEqual(prepared['status'],'needs_clarification')
        self.assertEqual(prepared['action_id'],str(__import__('uuid').uuid5(__import__('uuid').UUID(QUESTION),'memory-action')))

    def test_claim_binding_must_quote_answer_text(self):
        response={'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({
          'answer':'Projekt X ist entschieden [E001].','citation_ids':['E001'],'insufficient_evidence':False,
          'claims':[{'text':'Ein ganz anderer Satz','citation_ids':['E001']}]})}]}
        with self.assertRaises(ValidationError):_decoded(response)

    def test_invalid_answer_binding_gets_one_strict_repair_attempt(self):
        answer_calls=[]
        def provider(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                values=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in values],
                  'usage_final':True,'usage':{'input_tokens':len(values),'output_tokens':0}}
            if schema==PLAN_SCHEMA:value=planned(scope='global',search_queries=['festgehaltene Entscheidungen'])
            else:
                answer_calls.append(prompt)
                value={'answer':'Belegt [E001].','citation_ids':['E001'],'insufficient_evidence':False,
                  'claims':[{'text':'Nicht wortgleich','citation_ids':['E001']}]} if len(answer_calls)==1 else {
                  'answer':'Belegt [E001].','citation_ids':['E001'],'insufficient_evidence':False,
                  'claims':[{'text':'Belegt [E001].','citation_ids':['E001']}]}
            return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(value)}],
              'usage_final':True,'usage':{'input_tokens':10,'output_tokens':5,'input_tokens_details':{}}}
        service=QuestionService(Journal(self.fixture.store,self.fixture.db,self.fixture.archive),provider,
          budget_micro_usd=10**9,outbox=self.fixture.tmp.name+'/outbox')
        result=service.answer(OWNER,{'request_id':QUESTION,'question':'Welche Entscheidungen sind aktuell festgehalten?'})
        self.assertEqual(result['answer'],'Belegt [E001].')
        self.assertEqual(len(answer_calls),2)
        self.assertIn('KORREKTUR DES ANTWORTFORMATS',answer_calls[1])
        answer_records=[row for row in self.fixture.store.calls.values()
          if json.loads(row['request_json']).get('schema')==ANSWER_SCHEMA]
        self.assertEqual(len(answer_records),2)
        self.assertNotEqual(answer_records[0]['request_hash'],answer_records[1]['request_hash'])

    def test_invalid_repair_remains_terminal(self):
        answer_calls=[]
        def provider(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                values=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in values],
                  'usage_final':True,'usage':{'input_tokens':len(values),'output_tokens':0}}
            value=planned(scope='global',search_queries=['festgehaltene Entscheidungen']) if schema==PLAN_SCHEMA else {
              'answer':'Belegt [E001].','citation_ids':['E001'],'insufficient_evidence':False,
              'claims':[{'text':'Nicht wortgleich','citation_ids':['E001']}]}
            if schema!=PLAN_SCHEMA:answer_calls.append(prompt)
            return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(value)}],
              'usage_final':True,'usage':{'input_tokens':10,'output_tokens':5,'input_tokens_details':{}}}
        service=QuestionService(Journal(self.fixture.store,self.fixture.db,self.fixture.archive),provider,
          budget_micro_usd=10**9,outbox=self.fixture.tmp.name+'/outbox')
        with self.assertRaises(AnswerUnverified):service.answer(
          OWNER,{'request_id':QUESTION,'question':'Welche Entscheidungen sind aktuell festgehalten?'})
        self.assertEqual(len(answer_calls),2)
        self.assertEqual(json.loads(self.fixture.store.questions[QUESTION]['response_json']),
          {'_question_error':'answer_unverified'})
        with self.assertRaises(AnswerUnverified):service.answer(
          OWNER,{'request_id':QUESTION,'question':'Welche Entscheidungen sind aktuell festgehalten?'})
        self.assertEqual(len(answer_calls),2)

    def test_provider_outcome_unknown_does_not_trigger_answer_repair(self):
        from durable_calls import OutcomeUnknown
        answer_calls=[]
        def provider(prompt,model,max_tokens=0,schema=None):
            if model=='text-embedding-3-small':
                values=json.loads(prompt);return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*1535 for _ in values],
                  'usage_final':True,'usage':{'input_tokens':len(values),'output_tokens':0}}
            if schema==PLAN_SCHEMA:value=planned(scope='global',search_queries=['festgehaltene Entscheidungen'])
            else:
                answer_calls.append(prompt)
                raise OutcomeUnknown('provider outcome unknown')
            return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(value)}],
              'usage_final':True,'usage':{'input_tokens':10,'output_tokens':5,'input_tokens_details':{}}}
        service=QuestionService(Journal(self.fixture.store,self.fixture.db,self.fixture.archive),provider,
          budget_micro_usd=10**9,outbox=self.fixture.tmp.name+'/outbox')
        with self.assertRaises(OutcomeUnknown):service.answer(
          OWNER,{'request_id':QUESTION,'question':'Welche Entscheidungen sind aktuell festgehalten?'})
        self.assertEqual(len(answer_calls),1)

    def test_persisted_followup_context_drives_next_week_task_filter(self):
        class ConversationStore(Store):
            def __init__(self):super().__init__();self.conversations={}
            def call(self,op,**value):
                if op=='conversation_create':
                    row={'conversation_id':value['conversation_id'],'title':value.get('title') or 'Neues Gespräch'}
                    repeated=value['conversation_id'] in self.conversations;self.conversations.setdefault(value['conversation_id'],row)
                    return {**self.conversations[value['conversation_id']],'repeated':repeated}
                if op=='conversation_get':
                    row=self.conversations.get(value['conversation_id'])
                    if not row:return None
                    messages=[]
                    for identifier,q in self.questions.items():
                        if identifier==value.get('before_question_id'):break
                        if q.get('conversation_id')!=value['conversation_id']:continue
                        raw=json.loads(q['request_json']);messages.append({'message_id':'u','role':'user','content':raw['question'],'created_at':'now'})
                        if q.get('response_json'):
                            response=json.loads(q['response_json']);messages.append({'message_id':'a','role':'assistant','content':response['answer'],'created_at':'now'})
                    return {'conversation':row,'messages':messages}
                return super().call(op,**value)
        store=ConversationStore();journal=Journal(store,self.fixture.db,self.fixture.archive);conversations=ConversationService(journal)
        conversation=str(uuid4());conversations.create(OWNER,{'conversation_id':conversation})
        record(self.fixture.db,command_id=str(uuid4()),actor_id=OWNER['id'],command={'action':'create_task',
          'target_id':str(uuid4()),'reason':'Sebastians nächste Woche','event_date':'2026-09-19',
          'patch':{'title':'Lieferantenrisiko prüfen','owner':'Sebastian Krüger','due_date':'2026-09-25'}});self.fixture.db.commit()
        seen=[]
        def provider(prompt,model,max_tokens=0,schema=None):
            if schema==PLAN_SCHEMA:
                seen.append(prompt)
                value=planned(intent='tasks',people=['Sebastian'],task_status='all',search_queries=[])
                if 'Und welche davon' in prompt:value.update(date_from='2026-09-21',date_to='2026-09-27')
                return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(value)}],
                  'usage_final':True,'usage':{'input_tokens':10,'output_tokens':5,'input_tokens_details':{}}}
            raise AssertionError('Structured task followups need no answer generation')
        service=QuestionService(journal,provider,budget_micro_usd=10**9,outbox=self.fixture.tmp.name+'/outbox',conversations=conversations)
        first=str(uuid4());service.answer(OWNER,{'request_id':first,'conversation_id':conversation,'question':'Welche Aufgaben hat Sebastian?'})
        second=str(uuid4());result=service.answer(OWNER,{'request_id':second,'conversation_id':conversation,'question':'Und welche davon betreffen nächste Woche?'})
        self.assertEqual(result['coverage']['matched_tasks'],1);self.assertIn('Lieferantenrisiko',result['answer'])
        self.assertIn('Welche Aufgaben hat Sebastian?',seen[-1]);self.assertIn('Lieferantenrisiko',seen[-1])


class ConversationServiceTests(unittest.TestCase):
    class ConversationStore:
        space_id='10000000-0000-4000-8000-000000000001'
        def __init__(self):self.rows={}
        def space(self):return {'id':self.space_id,'owner_id':OWNER['id']}
        def call(self,op,**value):
            if op=='conversation_create':
                old=self.rows.get(value['conversation_id']);title=value['title'] or 'Neues Gespräch'
                if old:return {**old,'repeated':True}
                row={'conversation_id':value['conversation_id'],'title':title,'created_at':'now','updated_at':'now'};self.rows[row['conversation_id']]=row
                return {**row,'repeated':False}
            if op=='conversations_list':return {'conversations':list(self.rows.values())}
            if op=='conversation_get':
                row=self.rows.get(value['conversation_id'])
                if not row:return None
                messages=[{'message_id':str(i),'role':'user' if i%2==0 else 'assistant','content':'x'*1100,'created_at':'now'} for i in range(30)]
                return {'conversation':row,'messages':messages}
            raise AssertionError(op)
    class ConversationJournal:
        def __init__(self):self.store=ConversationServiceTests.ConversationStore()
        def authorize(self,identity,space):
            if identity!=OWNER or space['owner_id']!=identity['id']:raise PermissionError

    def test_create_list_load_and_bounded_context(self):
        service=ConversationService(self.ConversationJournal());identifier=str(uuid4())
        self.assertEqual(service.create(OWNER,{'conversation_id':identifier})['repeated'],False)
        self.assertEqual(service.create(OWNER,{'conversation_id':identifier})['repeated'],True)
        self.assertEqual(len(service.list(OWNER)['conversations']),1)
        self.assertEqual(len(service.get(OWNER,identifier)['messages']),30)
        messages,omitted=service.context(OWNER,identifier,str(uuid4()))
        self.assertLessEqual(len(messages),24);self.assertLessEqual(sum(len(m['content'].encode()) for m in messages),24000)
        self.assertGreater(omitted,0)
        with self.assertRaises(ConversationNotFound):service.get(OWNER,str(uuid4()))


if __name__=='__main__':unittest.main()
