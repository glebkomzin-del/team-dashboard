"""Offline regression for Sol count transport and visible worker transient status."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path('/private/tmp/dashboard-sol-operational-20261006')
sys.path.insert(0, str(ROOT / 'candidate-token-fix'))
import openai_provider as provider
import server
from durable_calls import DurableCalls, SharedProviderFailure, OutcomeUnknown, encode, sha
from gateway_journal import TransientGateway

spec = importlib.util.spec_from_file_location('frozen_provider', ROOT / 'candidate' / 'openai_provider.py')
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
SCHEMA = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
MODEL = 'gpt-6.1-sol'

class Response:
    status = 200
    def __init__(self, payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, *args): return json.dumps(self.payload).encode()

class Store:
    space_id='10000000-0000-0000-0000-000000000001'
    def __init__(self):self.ops=[];self.saved=None
    def call(self,op,**fields):
        self.ops.append(op)
        if op=='reserve_call':
            if self.saved is not None:
                if self.saved['request_hash']!=sha(fields['request_json']):raise AssertionError('request changed')
                return {'send':False,**self.saved}
            self.saved={'request_hash':sha(fields['request_json']),'response_json':None}
            return {'send':True,**self.saved}
        if op=='receive_call':
            self.saved.update(response_json=fields['response_json'],response_hash=sha(fields['response_json']))
            return {'saved':True}
        raise AssertionError(op)

JOB={'id':'a'*64,'lease_token':'20000000-0000-0000-0000-000000000001',
     'pipeline':'test','expected_revision':0}

class CounterFixTest(unittest.TestCase):
    def test_counter_five_fields_and_generation_unchanged(self):
        self.assertEqual(provider.response_input('ping',MODEL,SCHEMA),frozen.response_input('ping',MODEL,SCHEMA))
        sent=[]
        def urlopen(request,timeout):
            sent.append(json.loads(request.data));return Response({'object':'response.input_tokens','input_tokens':17})
        with patch.object(provider,'api_key',return_value='fixture'),patch.object(provider.urllib.request,'urlopen',side_effect=urlopen):
            self.assertEqual(provider.count_input_tokens('ping',MODEL,SCHEMA),17)
        self.assertEqual(set(sent[0]),{'model','input','reasoning','text','truncation'})
        self.assertEqual(sent[0]['reasoning'],{'effort':'medium'})
        self.assertEqual(provider.response_input('ping',MODEL,SCHEMA)['service_tier'],'default')

    def test_invalid_unknown_and_http_counter_never_reserve_or_generate(self):
        responses=[Response({'object':'response.input_tokens','input_tokens':0}),
                   Response({'object':'unexpected','input_tokens':17}),
                   Response({'object':'response.input_tokens'}),
                   Response({'object':'response.input_tokens','input_tokens':True}),
                   HTTPError('https://example.invalid',400,'Bad Request',{},io.BytesIO(b'{"error":{"message":"private"}}')),
                   URLError('fixture')]
        for response in responses:
            with self.subTest(response=type(response).__name__):
                store=Store();sent=[]
                def urlopen(*args,**kwargs):
                    if isinstance(response,Exception):raise response
                    return response
                with patch.object(provider,'api_key',return_value='fixture'),patch.object(provider.urllib.request,'urlopen',side_effect=urlopen),contextlib.redirect_stderr(io.StringIO()) as stderr:
                    with tempfile.TemporaryDirectory() as tmp:
                        calls=DurableCalls(store,JOB,lambda *a,**k:sent.append(1),SCHEMA,tmp,
                                           prior_calls=[],token_counter=provider.count_input_tokens)
                        with self.assertRaises(SharedProviderFailure):calls('ping',MODEL,100,schema=SCHEMA)
                self.assertEqual(store.ops,[])
                self.assertEqual(sent,[])
                self.assertNotIn('private',stderr.getvalue())
        with self.assertRaises(ValueError):provider.count_input_tokens('ping','unknown',SCHEMA)
        with (patch.object(provider,'api_key',side_effect=RuntimeError('secret credential detail')),
              contextlib.redirect_stderr(io.StringIO()) as stderr):
            with self.assertRaises(provider.CounterUnavailable) as caught:
                provider.count_input_tokens('ping',MODEL,SCHEMA)
        self.assertEqual(caught.exception.kind,'credential')
        self.assertNotIn('secret',stderr.getvalue())

    def test_prior_paid_unknown_still_never_resends(self):
        store=Store();sent=[]
        def api(*args,**kwargs):
            sent.append(1);return {'error':'TimeoutError','usage_final':False,'terminal_status':None,'stop_reason':None}
        with tempfile.TemporaryDirectory() as tmp:
            calls=DurableCalls(store,JOB,api,SCHEMA,tmp,prior_calls=[],token_counter=None)
            with self.assertRaises(OutcomeUnknown):calls('ping',MODEL,100,schema=SCHEMA)
            self.assertEqual(sent,[1])
            self.assertEqual(store.ops,['reserve_call','receive_call'])
            replay=DurableCalls(store,JOB,api,SCHEMA,tmp,start_index=1,
                prior_calls=[{'index':0,'request_hash':store.saved['request_hash']}],token_counter=provider.count_input_tokens)
            with self.assertRaises(OutcomeUnknown):replay('ping',MODEL,100,schema=SCHEMA)
            self.assertEqual(sent,[1])
            self.assertEqual(store.ops,['reserve_call','receive_call','reserve_call'])

    def test_transient_diagnostic_retained_only_for_same_waiting_job(self):
        diagnostic={'component':'canonical_worker','error_type':'OSError','frames':[]}
        recent={'diagnostic':diagnostic,'job_id':None}
        waiting={'state':'waiting','reason':'earlier_job_leased','job_id':'a'}
        status,recent=server.retain_worker_transient(waiting,recent)
        self.assertEqual(status['previous_transient'],diagnostic)
        status,recent=server.retain_worker_transient(waiting,recent)
        self.assertEqual(status['previous_transient'],diagnostic)
        status,recent=server.retain_worker_transient({**waiting,'job_id':'b'},recent)
        self.assertNotIn('previous_transient',status);self.assertIsNone(recent)
        status,recent=server.retain_worker_transient({'state':'applied','job_id':'a'},
            {'diagnostic':diagnostic,'job_id':'a'})
        self.assertIsNone(recent)

    def test_outer_transient_logger_redacts_http_and_gateway_details(self):
        for error in (TransientGateway('archive_document','http',http_status=503),
                      HTTPError('https://example.invalid/private',400,'private-body',{},io.BytesIO(b'private-body'))):
            try:raise error
            except Exception as caught:
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    diagnostic=server.worker_error(caught,1)
            self.assertNotIn('private',stderr.getvalue())
            self.assertEqual(json.loads(stderr.getvalue())['error_type'],type(error).__name__)
            if isinstance(error,TransientGateway):
                self.assertEqual(diagnostic['gateway']['op'],'archive_document')
                self.assertEqual(diagnostic['gateway']['http_status'],503)
            else:self.assertEqual(diagnostic['http_status'],400)

if __name__=='__main__':unittest.main()
