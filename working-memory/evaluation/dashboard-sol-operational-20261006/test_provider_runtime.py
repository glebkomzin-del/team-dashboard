"""Offline Sol request/cost and durable error classification; no provider transport."""
import json
import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

CANDIDATE = Path('/private/tmp/dashboard-sol-operational-20261006/candidate')
sys.path.insert(0, str(CANDIDATE))
from call_budget import reserve_micro_usd, usage_micro_usd
from durable_calls import DurableCalls, OutcomeUnknown, SharedProviderFailure, encode, sha
from question_calls import QuestionCalls
from canonical_worker import CanonicalWorker
import processor
from qa_service import QuestionService
import openai_provider

MODEL = 'gpt-6.1-sol'
SCHEMA = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}

class FakeStore:
    space_id='10000000-0000-0000-0000-000000000001'
    def __init__(self): self.calls=[]; self.records={}
    def call(self,op,**fields):
        self.calls.append((op, fields))
        if op=='reserve_call':
            slot=fields['call_index']; request_hash=sha(fields['request_json'])
            if slot in self.records:
                record=self.records[slot]
                if record['request_hash']!=request_hash: raise AssertionError('request changed')
                return {'send':False,**record}
            record={'index':slot,'request_hash':request_hash,'response_json':None,'response_hash':None,
                    'reserved_micro_usd':fields['reserved_micro_usd']}
            self.records[slot]=record
            return {'send':True,**record}
        if op=='receive_call':
            record=self.records[fields['call_index']]
            record.update(response_json=fields['response_json'],response_hash=sha(fields['response_json']),
                          actual_micro_usd=fields['actual_micro_usd'])
            return {'saved':True}
        raise AssertionError(op)

class ProviderRuntimeTest(unittest.TestCase):
    def test_question_service_defaults_to_sol(self):
        self.assertEqual(inspect.signature(QuestionService.__init__).parameters['model'].default,MODEL)
    def test_sol_worker_registers_provider_counter_and_reserves_counted_input(self):
        class Service:
            store=FakeStore()
            cache=Path('/private/tmp/dashboard-sol-operational-20261006')
        old=processor.PROMPT_VERSION;processor.PROMPT_VERSION='v11'
        try:
            with patch.object(openai_provider,'count_input_tokens',return_value=123) as count:
                worker=CanonicalWorker(Service(),MODEL)
                self.assertIs(worker.token_counter,openai_provider.count_input_tokens)
                job={'id':'c'*64,'lease_token':'20000000-0000-0000-0000-000000000003',
                     'pipeline':worker.pipeline,'expected_revision':0}
                response={'content':[{'type':'text','text':'{"ok":true}'}],
                    'usage_final':True,'returned_service_tier':'default','stop_reason':'end_turn',
                    'usage':{'input_tokens':123,'output_tokens':20}}
                with tempfile.TemporaryDirectory() as tmp:
                    calls=DurableCalls(Service.store,job,lambda *a,**k:response,SCHEMA,tmp,
                                       prior_calls=[],token_counter=worker.token_counter)
                    calls('fixture',MODEL,100,schema=SCHEMA)
                count.assert_called_once_with('fixture',MODEL,SCHEMA)
                reserved=next(fields['reserved_micro_usd'] for op,fields in Service.store.calls if op=='reserve_call')
                self.assertEqual(reserved,reserve_micro_usd('fixture',MODEL,100,SCHEMA,counted_input_tokens=123))
        finally:processor.PROMPT_VERSION=old
    def test_medium_default_wire_and_normalization(self):
        payload=openai_provider.response_input('original',MODEL,SCHEMA)
        self.assertEqual(payload['service_tier'],'default')
        self.assertEqual(payload['reasoning'],{'effort':'medium'})
        raw={'id':'resp_test','model':MODEL,'status':'completed','service_tier':'default',
             'usage':{'input_tokens':1000,'output_tokens':100},
             'output':[{'type':'reasoning','id':'rs_test','summary':[], 'status':'completed'},
                       {'type':'message','role':'assistant','status':'completed',
                        'content':[{'type':'output_text','text':'{"ok":true}'}]}]}
        norm=openai_provider.normalize(raw,MODEL)
        self.assertEqual(norm['stop_reason'],'end_turn')
        self.assertEqual(norm['content'],[{'type':'text','text':'{"ok":true}'}])
        self.assertTrue(norm['usage_final'])
        raw['status']='incomplete';raw['incomplete_details']={'reason':'max_output_tokens'}
        incomplete=openai_provider.normalize(raw,MODEL)
        self.assertIsNone(incomplete['stop_reason'])
        self.assertEqual(incomplete['terminal_status'],'incomplete')
        self.assertEqual(incomplete['incomplete_reason'],'max_output_tokens')
        raw['status']='completed';raw['service_tier']='priority'
        self.assertIsNone(openai_provider.normalize(raw,MODEL)['stop_reason'])
    def test_cost_reservation_and_known_usage(self):
        reserve=reserve_micro_usd('original',MODEL,12000,SCHEMA)
        self.assertGreater(reserve,120000)
        actual=usage_micro_usd({'usage_final':True,'returned_service_tier':'default',
           'usage':{'input_tokens':1000,'output_tokens':100,
                    'input_tokens_details':{'cached_tokens':100,'cache_write_tokens':200}}},MODEL)
        self.assertEqual(actual,2910)
        self.assertIsNone(usage_micro_usd({'usage_final':True,'returned_service_tier':None,
            'usage':{'input_tokens':1000,'output_tokens':100}},MODEL))
    def test_shared_http_failures_persist_once_and_never_isolate(self):
        for status in (401,429,503):
            store=FakeStore(); sent=[]
            def api(*args,**kwargs):sent.append(1);return {'error':f'HTTP {status}','usage_final':False,
                'terminal_status':None,'stop_reason':None}
            job={'id':'a'*64,'lease_token':'20000000-0000-0000-0000-000000000001',
                 'pipeline':'test','expected_revision':0}
            with tempfile.TemporaryDirectory() as tmp:
                calls=DurableCalls(store,job,api,SCHEMA,tmp,prior_calls=[])
                with self.assertRaises(SharedProviderFailure): calls('original',MODEL,12000,schema=SCHEMA)
                self.assertEqual(len(sent),1)
                self.assertEqual(len(store.records),1)
                self.assertIsNotNone(store.records[0]['response_json'])
                self.assertIsNone(store.records[0]['actual_micro_usd'])
                self.assertEqual(list(Path(tmp).glob('*.json')),[])
                replay=DurableCalls(store,job,api,SCHEMA,tmp,start_index=1,prior_calls=[
                    {'index':0,'request_hash':store.records[0]['request_hash']}])
                with self.assertRaises(SharedProviderFailure): replay('original',MODEL,12000,schema=SCHEMA)
                self.assertEqual(len(sent),1)
    def test_lost_transport_receipt_is_unknown_and_never_resent(self):
        store=FakeStore();sent=[]
        def api(*args,**kwargs):sent.append(1);return {'error':'TimeoutError','usage_final':False,
            'terminal_status':None,'stop_reason':None}
        job={'id':'b'*64,'lease_token':'20000000-0000-0000-0000-000000000002',
             'pipeline':'test','expected_revision':0}
        with tempfile.TemporaryDirectory() as tmp:
            calls=DurableCalls(store,job,api,SCHEMA,tmp,prior_calls=[])
            with self.assertRaises(OutcomeUnknown): calls('original',MODEL,12000,schema=SCHEMA)
            self.assertEqual(len(sent),1)
            self.assertIsNotNone(store.records[0]['response_json'])
            replay=DurableCalls(store,job,api,SCHEMA,tmp,start_index=1,prior_calls=[
                {'index':0,'request_hash':store.records[0]['request_hash']}])
            with self.assertRaises(OutcomeUnknown): replay('original',MODEL,12000,schema=SCHEMA)
            self.assertEqual(len(sent),1)

    def test_question_request_identity_sol_transport_and_terra_legacy(self):
        class QuestionStore:
            space_id='10000000-0000-0000-0000-000000000001'
            def __init__(self):self.requests=[]
            def call(self,op,**fields):
                if op!='question_reserve':raise AssertionError(op)
                self.requests.append(fields['request_json'])
                return {'request_hash':sha(fields['request_json']),'response_json':None,
                        'send':False,'call_index':fields['call_index']}
        with tempfile.TemporaryDirectory() as tmp:
            store=QuestionStore()
            calls=QuestionCalls(store,question_id='q',actor_id='a',api=lambda *a,**k:None,
                                outbox=tmp,budget_micro_usd=None)
            for model in (MODEL,'gpt-5.6-terra'):
                with self.assertRaises(OutcomeUnknown):calls('prompt',model,max_tokens=100,schema=SCHEMA)
            sol,terra=map(json.loads,store.requests)
            self.assertEqual(sol['transport'],{'reasoning_effort':'medium','service_tier':'default'})
            self.assertNotIn('transport',terra)

if __name__=='__main__': unittest.main()
