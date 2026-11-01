import copy
import io
import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import openai_provider as provider
import processor
from call_budget import CallBudget, reserve_micro_usd, usage_micro_usd, BudgetExceeded
from durable_calls import DurableCalls, OutcomeUnknown
from test_durable_calls import Store
from test_canonical_worker import CanonicalStore, CanonicalWorkerTest
from canonical_worker import CanonicalWorker
from journal_service import JournalService


def terminal(text='{}', status='completed', model=provider.MODEL):
    return {'type': 'response.' + status, 'response': {
        'id': 'resp_synthetic', 'model': model, 'status': status,
        'usage': {'input_tokens': 100, 'output_tokens': 20,
                  'input_tokens_details': {'cached_tokens': 20, 'cache_write_tokens': 40}},
        'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                    'content': [{'type': 'output_text', 'text': text}]}]}}


def stream(*events):
    return io.BytesIO(''.join('data: ' + json.dumps(e) + '\n\n' for e in events).encode())


class TerraTransportTests(unittest.TestCase):
    def test_gpt6_requests_keep_model_and_none_effort(self):
        schema={'type':'object','properties':{},'required':[],'additionalProperties':False}
        def send(req, timeout):
            payload=json.loads(req.data)
            self.assertEqual(payload['reasoning'], {'effort': 'none'})
            return stream(terminal(model=payload['model']))
        with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic'}),patch.object(provider.urllib.request,'urlopen',side_effect=send) as network:
            for model in ('gpt-6-sol','gpt-6-luna'):
                result=provider.request('Synthetic',model,schema=schema)
                self.assertEqual(result['model'],model)
                self.assertEqual(result['stop_reason'],'end_turn')
        self.assertEqual(network.call_count,2)

    def test_request_contract_and_final_response(self):
        schema={'type':'object','properties':{},'required':[],'additionalProperties':False}
        def send(req, timeout):
            self.assertEqual(req.full_url,'https://api.openai.com/v1/responses')
            p=json.loads(req.data)
            self.assertEqual(p['model'],provider.MODEL)
            self.assertEqual(p['reasoning'],{'effort':'none'})
            self.assertEqual(p['text']['format']['schema'],schema)
            self.assertTrue(p['text']['format']['strict'])
            self.assertFalse(p['store']);self.assertEqual(p['truncation'],'disabled')
            self.assertNotIn('temperature',p);self.assertNotIn('tools',p)
            self.assertEqual(p['max_output_tokens'],6000)
            return stream({'type':'response.output_text.delta','delta':'partial'},terminal())
        with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic'}),patch.object(provider.urllib.request,'urlopen',side_effect=send) as network:
            result=processor.model_request('Synthetic',provider.MODEL,max_tokens=6000,schema=schema)
        self.assertEqual(network.call_count,1)
        self.assertEqual(result['stop_reason'],'end_turn')
        self.assertEqual(result['content'],[{'type':'text','text':'{}'}])
        self.assertTrue(result['usage_final'])

    def test_incomplete_and_refusal_never_publish_but_account_usage(self):
        for event in [terminal(status='incomplete'),terminal(status='failed')]:
            result=provider.collect_stream(stream(event),time.monotonic()+5,provider.MODEL)
            self.assertIsNone(result['stop_reason']);self.assertTrue(result['usage_final'])
        event=terminal();event['response']['output'][0]['content']=[{'type':'refusal','refusal':'synthetic'}]
        result=provider.collect_stream(stream(event),time.monotonic()+5,provider.MODEL)
        self.assertIsNone(result['stop_reason']);self.assertTrue(result['usage_final'])

    def test_partial_error_wrong_model_and_timeout_fail_closed(self):
        for response,deadline in [
            (stream({'type':'response.output_text.delta','delta':'{}'}),time.monotonic()+5),
            (stream({'type':'error','message':'PRIVATE KEY'}),time.monotonic()+5),
            (stream(terminal(model='unexpected')),time.monotonic()+5),
            (stream(terminal()),time.monotonic()-1)]:
            result=provider.collect_stream(response,deadline,provider.MODEL)
            self.assertIsNone(result['stop_reason']);self.assertFalse(result['usage_final'])
            self.assertNotIn('PRIVATE KEY',json.dumps(result))

    def test_http_errors_do_not_retry_or_leak_response_body(self):
        error=provider.urllib.error.HTTPError('https://api.openai.com',429,'private',{},io.BytesIO(b'PRIVATE KEY'))
        with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic'}),patch.object(provider.urllib.request,'urlopen',side_effect=error) as network:
            result=provider.request('Synthetic',provider.MODEL,schema={})
        self.assertEqual(network.call_count,1);self.assertEqual(result['error'],'HTTP 429')
        self.assertNotIn('PRIVATE KEY',json.dumps(result))

    def test_all_existing_schemas_are_strict_without_weakening(self):
        import future_summary,reconcile
        schemas=[json.loads((processor.ROOT/'evaluation/schema-v9.json').read_text()),
                 json.loads((processor.ROOT/'evaluation/work-gate-schema-v9.json').read_text()),reconcile.SCHEMA]
        schemas.append(future_summary.schema(schemas[0]))
        def check(s):
            if isinstance(s,dict):
                if s.get('type')=='object':
                    self.assertIs(s['additionalProperties'],False)
                    self.assertEqual(set(s['properties']),set(s['required']))
                for v in s.values():check(v)
            elif isinstance(s,list):
                for v in s:check(v)
        for s in schemas:check(s)


class TerraBudgetTests(unittest.TestCase):
    def test_gpt6_prices_are_below_terra_and_reserve_long_context(self):
        for model, input_price, output_price in [('gpt-6-sol', 2, 10), ('gpt-6-luna', .1, .5)]:
            response={'usage_final':True,'usage':{'input_tokens':1000,'output_tokens':100,
                       'input_tokens_details':{'cached_tokens':100,'cache_write_tokens':100}}}
            expected=(800*input_price+100*input_price*.1+100*input_price*1.25+100*output_price)
            self.assertEqual(usage_micro_usd(response,model),math.ceil(expected))
            self.assertLess(usage_micro_usd(response,model),usage_micro_usd(response,provider.MODEL))
            long_response=copy.deepcopy(response);long_response['usage']['input_tokens']=272001
            self.assertGreater(usage_micro_usd(long_response,model),0)
            self.assertGreater(reserve_micro_usd('x',model,100,{},counted_input_tokens=300000),
                               usage_micro_usd(response,model))

    def test_real_saved_usage_pricing_and_no_reasoning_double_charge(self):
        r={'usage_final':True,'usage':{'input_tokens':5283,'output_tokens':3088,
            'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':5280},
            'output_tokens_details':{'reasoning_tokens':100}}}
        self.assertEqual(usage_micro_usd(r,provider.MODEL),50262)

    def test_long_context_prices_full_request_and_reserves_cache_writes(self):
        for size in [272000,272001]:
            r={'usage_final':True,'usage':{'input_tokens':size,'output_tokens':100,
                'input_tokens_details':{'cached_tokens':1000,'cache_write_tokens':1000}}}
            expected=(size-2000)*2+1000*.2+1000*2.5+100*12 if size==272000 else (size-2000)*4+1000*.4+1000*5+100*18
            self.assertEqual(usage_micro_usd(r,provider.MODEL),int(expected))
        self.assertEqual(reserve_micro_usd('x'*300000,provider.MODEL,100,{}),(300000+2+4096)*5+1800)

    def test_invalid_usage_stays_reserved_and_budget_survives_restart(self):
        for detail in [{'cached_tokens':True},{'cache_write_tokens':-1},{'cached_tokens':101},None]:
            r=terminal()['response'];r['usage_final']=True;r['usage']['input_tokens_details']=detail
            self.assertIsNone(usage_micro_usd(r,provider.MODEL))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'budget.sqlite';b=CallBudget(p,.4)
            calls=[]
            b.wrap(lambda *a,**kw:calls.append(1) or {'usage_final':False},{})('x',provider.MODEL)
            total=b.total();b.close();b=CallBudget(p,.4)
            self.assertEqual(b.total(),total)
            with self.assertRaises(BudgetExceeded):b.wrap(lambda *a,**kw:calls.append(1),{})('x',provider.MODEL)
            self.assertEqual(calls,[1]);b.close()

    def test_terra_receipt_replays_without_second_network_call(self):
        store=Store();job={'id':'a'*64,'lease_token':'synthetic'};sent=[]
        with tempfile.TemporaryDirectory() as d:
            def api(*a,**kw):sent.append(1);return provider.normalize(terminal()['response'],provider.MODEL)
            first=DurableCalls(store,job,api,{},d)('Synthetic',provider.MODEL)
            second=DurableCalls(store,job,api,{},d)('Synthetic',provider.MODEL)
            self.assertEqual(first,second);self.assertEqual(sent,[1])


class TerraCanonicalTests(CanonicalWorkerTest):
    def test_terra_transport_through_rules_and_canonical_publication(self):
        def send(req,timeout):
            p=json.loads(req.data)
            parsed=self.api(p['input'][0]['content'],p['model'],schema=p['text']['format']['schema'])
            return stream(terminal(parsed['content'][0]['text']))
        store=CanonicalStore();service=JournalService(store,self.tmp.name)
        with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic'}),patch.object(provider.urllib.request,'urlopen',side_effect=send) as network:
            worker=CanonicalWorker(service,provider.MODEL)
            self.assertEqual(worker.step()['state'],'applied')
            self.assertEqual(worker.step()['state'],'idle')
        self.assertEqual(network.call_count,1)
        self.assertIn('zwei Filialen',store.prepared['archive_note']['note_json'])

    def test_terra_historical_source_cannot_reach_transport(self):
        store=CanonicalStore('2026-06-01')
        with patch.object(provider.urllib.request,'urlopen') as network:
            result=CanonicalWorker(JournalService(store,self.tmp.name),provider.MODEL).step()
        self.assertEqual(result['reason'],'validation_failed');network.assert_not_called()


if __name__=='__main__':unittest.main()
