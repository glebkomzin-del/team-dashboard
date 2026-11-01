import copy
import json
from pathlib import Path
import tempfile
import unittest
from durable_calls import DurableCalls,OutcomeUnknown,drain_outbox,sha,usage_cost
from call_budget import BudgetExceeded
from memory import ValidationError
from journal_store import JournalUnavailable

class Store:
    space_id='synthetic-space'
    def __init__(self):self.rows={};self.total=0;self.limit=10000000;self.fail_receive=False
    def call(self,op,**v):
        i=v['call_index']
        if op=='reserve_call':
            if i in self.rows:return {**self.rows[i],'send':False}
            if self.total+v['reserved_micro_usd']>self.limit:return {'state':'budget_exceeded','send':False}
            self.total+=v['reserved_micro_usd']
            self.rows[i]={**v,'request_hash':sha(v['request_json'])}
            return {**self.rows[i],'send':True}
        if op=='receive_call':
            if self.fail_receive:raise JournalUnavailable('synthetic unavailable')
            self.rows[i].update(response_json=v['response_json'],response_hash=sha(v['response_json']))
            return {'saved':True}
        raise AssertionError(op)

class DurableCallsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store();self.sent=0
        self.job={'id':'a'*64,'lease_token':'synthetic-lease'}
        self.result={'content':[{'type':'text','text':'{}'}],'usage_final':True,
                     'usage':{'input_tokens':12,'output_tokens':8},'elapsed_seconds':.1}
    def tearDown(self):self.tmp.cleanup()
    def api(self,*a,**k):self.sent+=1;return copy.deepcopy(self.result)
    def client(self):return DurableCalls(self.store,self.job,self.api,{'type':'object'},self.tmp.name)
    def test_response_replayed_after_restart_without_spending(self):
        first=self.client()('prompt','claude-opus-5')
        self.assertEqual(first,self.client()('prompt','claude-opus-5'))
        self.assertEqual(self.sent,1);self.assertEqual(list(Path(self.tmp.name).iterdir()),[])
    def test_lost_reservation_confirmation_never_sends_twice(self):
        c=self.client()
        reserve=self.store.call
        def ambiguous(op,**v):
            result=reserve(op,**v)
            if op=='reserve_call':raise JournalUnavailable('confirmation lost')
            return result
        self.store.call=ambiguous
        with self.assertRaises(JournalUnavailable):c('prompt','claude-opus-5')
        self.store.call=reserve
        with self.assertRaises(OutcomeUnknown):self.client()('prompt','claude-opus-5')
        self.assertEqual(self.sent,0)
    def test_outbox_survives_database_failure_and_restores_only_response(self):
        self.store.fail_receive=True
        with self.assertRaises(JournalUnavailable):self.client()('prompt','claude-opus-5')
        paths=list(Path(self.tmp.name).glob('*.json'));self.assertEqual(len(paths),1)
        self.assertEqual(paths[0].stat().st_mode&0o777,0o600)
        self.store.fail_receive=False
        self.assertEqual(drain_outbox(self.store,self.tmp.name),1)
        self.assertEqual(self.client()('prompt','claude-opus-5'),self.result)
        self.assertEqual(self.sent,1)
    def test_budget_denial_never_calls_provider(self):
        self.store.limit=1
        with self.assertRaises(BudgetExceeded):self.client()('prompt','claude-opus-5')
        self.assertEqual(self.sent,0)
    def test_tampered_saved_response_rejected(self):
        self.client()('prompt','claude-opus-5');self.store.rows[0]['response_json']='{"changed":true}'
        with self.assertRaises(ValidationError):self.client()('prompt','claude-opus-5')
        self.assertEqual(self.sent,1)
    def test_usage_is_conservative_and_integer(self):
        self.assertEqual(usage_cost(self.result,'claude-opus-5'),260)
        for v in (None,-1,True,1.5,float('nan')):
            result=copy.deepcopy(self.result);result['usage']['input_tokens']=v
            self.assertIsNone(usage_cost(result,'claude-opus-5'))
        result=copy.deepcopy(self.result);result['usage_final']=False
        self.assertIsNone(usage_cost(result,'claude-opus-5'))
    def test_reviewed_retry_appends_after_complete_prior_calls(self):
        self.client()('prompt-0','claude-opus-5')
        client=DurableCalls(self.store,self.job,self.api,{'type':'object'},self.tmp.name,start_index=1)
        client('prompt-1','claude-opus-5')
        self.assertEqual(sorted(self.store.rows),[0,1])
        self.assertEqual(client.index,2)
        with self.assertRaises(ValidationError):
            DurableCalls(self.store,self.job,self.api,{'type':'object'},self.tmp.name,start_index=1025)

    def test_call_slot_limit_is_enforced_before_reservation(self):
        client=DurableCalls(self.store,self.job,self.api,{'type':'object'},self.tmp.name,start_index=1023)
        client('last-slot','claude-opus-5')
        with self.assertRaisesRegex(ValidationError,'slots exhausted'):
            client('too-many','claude-opus-5')
        self.assertEqual(sorted(self.store.rows),[1023])

    def test_provider_count_reserves_before_sending_and_replay_does_not_recount(self):
        counted=[]
        def count(*args): counted.append(args); return 100
        client=DurableCalls(self.store,self.job,self.api,{'type':'object'},self.tmp.name,
                            prior_calls=[],token_counter=count)
        first=client('large prompt','gpt-5.6-terra',max_tokens=100)
        self.assertEqual(self.store.rows[0]['reserved_micro_usd'],(100+4096)*2.5+1200)
        self.assertEqual(client('large prompt','gpt-5.6-terra',max_tokens=100),first)
        self.assertEqual(len(counted),1);self.assertEqual(self.sent,1)

    def test_count_failure_cannot_generate_or_consume_a_slot(self):
        def count(*args): raise TimeoutError('count unavailable')
        client=DurableCalls(self.store,self.job,self.api,{'type':'object'},self.tmp.name,
                            prior_calls=[],token_counter=count)
        with self.assertRaises(TimeoutError):client('prompt','gpt-5.6-terra',max_tokens=100)
        self.assertEqual(self.sent,0);self.assertEqual(self.store.rows,{})

if __name__=='__main__':unittest.main()
