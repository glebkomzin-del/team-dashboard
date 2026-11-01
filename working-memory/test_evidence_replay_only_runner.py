import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from durable_calls import DurableCalls,encode,sha
from hybrid_index import DIMENSIONS,EMBED_SCHEMA,MODEL,digest
from memory import ValidationError
from future_summary import from_response


SCRIPT=Path(__file__).parent.parent/'.codex-deploy/memory-20260920/replay_evidence_repair_saved_job.py'
SPEC=importlib.util.spec_from_file_location('evidence_replay_only_runner',SCRIPT)
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)


class Store:
    space_id=runner.evidence.replay.SPACE_ID
    def __init__(self,response_hash=None):self.response_hash=response_hash;self.calls=[]
    def call(self,op,**fields):
        self.calls.append((op,fields))
        return {'response_hash':self.response_hash,'response_json':'{}','send':False}


class RecordStore:
    space_id=runner.evidence.replay.SPACE_ID
    def __init__(self,calls):self.calls={call['call_index']:call for call in calls}
    def call(self,op,**fields):return {**self.calls[fields['call_index']],'send':False}


class DurableReplayStore:
    space_id=runner.evidence.replay.SPACE_ID
    def __init__(self,response,wrong_hash=False):
        self.response=encode(response);self.wrong_hash=wrong_hash;self.actions=[]
    def call(self,op,**fields):
        self.actions.append(op)
        if op!='reserve_call':raise AssertionError(op)
        return {'request_hash':sha(fields['request_json']),'response_json':self.response,
                'response_hash':'0'*64 if self.wrong_hash else sha(self.response),'send':False}


class ReplayOnlyRunnerTests(unittest.TestCase):
    def receipt(self,change=None):
        calls=[];requests=['']*24;responses=['']*24
        for slot,text in ((22,'alpha'),(23,'beta')):
            request=encode({'model':MODEL,'prompt':encode([text]),'max_tokens':1,'schema':EMBED_SCHEMA,
                            'scope':{'pipeline':runner.evidence.replay.OLD_PIPELINE,'revision':169}})
            response=encode({'model':MODEL,'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*(DIMENSIONS-1)]})
            requests[slot]=sha(request);responses[slot]=sha(response)
            calls.append({'call_index':slot,'request_json':request,'request_hash':requests[slot],
                          'response_json':response,'response_hash':responses[slot],'reserved_micro_usd':1})
        value={'space_id':runner.evidence.replay.SPACE_ID,'job_id':runner.evidence.replay.JOB_ID,
               'pipeline':runner.evidence.replay.OLD_PIPELINE,'expected_revision':169,'calls':calls}
        if change:change(value)
        directory=tempfile.TemporaryDirectory();path=Path(directory.name)/'receipts.json'
        path.write_text(json.dumps(value));path.chmod(0o600)
        return directory,path,requests,responses

    def test_pins_complete_distinct_call_ledgers(self):
        self.assertEqual(len(runner.evidence.replay.EXPECTED_HASHES),24)
        self.assertEqual(len(set(runner.evidence.replay.EXPECTED_HASHES)),24)
        self.assertEqual(len(runner.evidence.EXPECTED_RESPONSE_HASHES),24)

    def test_new_slot_is_blocked_before_budget_reservation(self):
        base=Store();guarded=runner.ReplayOnlyTargetStore(base,{'id':runner.evidence.replay.JOB_ID},{},[])
        with self.assertRaisesRegex(RuntimeError,'forbids fresh model calls'):
            guarded.call('reserve_call',call_index=24)
        self.assertEqual(base.calls,[])

    def test_wrong_saved_response_hash_is_rejected(self):
        base=Store('0'*64);checked=runner.evidence.SavedResponseStore(base)
        with self.assertRaisesRegex(RuntimeError,'Saved response identity changed'):
            checked.call('reserve_call',call_index=23)
        self.assertEqual(len(base.calls),1)

    def test_provider_is_disabled(self):
        with self.assertRaisesRegex(RuntimeError,'cannot reach the provider'):
            runner.forbidden_provider('prompt','model')

    def test_only_repaired_extraction_becomes_final_primary_response(self):
        originals={'U0001':{'text':'Beleg','start':0,'end':5}}
        def response(evidence_id):
            value={'meeting_summary':[{'text':'Zusammenfassung','evidence_ids':[evidence_id]}],
                   'meeting_display_title':None}
            return {'content':[{'type':'text','text':encode(value)}]}
        invalid=response('U9999');valid=response('U0001')
        calls=type('Calls',(),{'primary_responses':[invalid]})()
        with self.assertRaisesRegex(ValidationError,'Summary lacks original evidence'):
            from_response(calls.primary_responses[-1],originals,'Titel')
        self.assertFalse(runner.mark_repaired_primary(calls,'0'*64,valid))
        self.assertIs(calls.primary_responses[-1],invalid)
        self.assertTrue(runner.mark_repaired_primary(
            calls,runner.evidence.replay.EXPECTED_HASHES[2],valid))
        self.assertEqual(from_response(calls.primary_responses[-1],originals,'Titel')['ai_summary'],
                         'Zusammenfassung')

    def test_actual_durable_call_marks_only_pinned_repair_without_extra_actions(self):
        response={'content':[{'type':'text','text':'{}'}]};schema={'type':'object'}
        scope={'pipeline':runner.evidence.replay.OLD_PIPELINE,'revision':169}
        def calls(prompt,explicit_schema,*,wrong_hash=False):
            effective=schema if explicit_schema is not None else {'type':'default'}
            request=encode({'model':'gpt-5.6-terra','prompt':prompt,'max_tokens':7,
                            'schema':effective,'scope':scope})
            store=DurableReplayStore(response,wrong_hash)
            durable=DurableCalls(store,{'id':runner.evidence.replay.JOB_ID,'lease_token':'lease',
                'pipeline':scope['pipeline'],'expected_revision':169},lambda *_args,**_kwargs:self.fail('provider called'),
                {'type':'default'},tempfile.mkdtemp(),start_index=24,
                prior_calls=[{'index':2,'request_hash':sha(request)}])
            return durable,store,sha(request)
        repaired,store,repaired_hash=calls('repair',schema)
        hashes=list(runner.evidence.replay.EXPECTED_HASHES);hashes[2]=repaired_hash
        original=DurableCalls.__call__
        try:
            with patch.object(runner.evidence.replay,'EXPECTED_HASHES',tuple(hashes)):
                runner.install_primary_repair()
                repaired('repair','gpt-5.6-terra',max_tokens=7,schema=schema)
                self.assertEqual(repaired.primary_responses,[response])
                self.assertEqual(store.actions,['reserve_call'])
                other,other_store,_=calls('other',schema)
                other('other','gpt-5.6-terra',max_tokens=7,schema=schema)
                self.assertEqual(other.primary_responses,[])
                self.assertEqual(other_store.actions,['reserve_call'])
                default,default_store,_=calls('default',None)
                default('default','gpt-5.6-terra',max_tokens=7)
                self.assertEqual(default.primary_responses,[response])
                self.assertEqual(default_store.actions,['reserve_call'])
                broken,_,_=calls('broken',schema,wrong_hash=True)
                with self.assertRaisesRegex(ValidationError,'Saved response hash mismatch'):
                    broken('broken','gpt-5.6-terra',max_tokens=7,schema=schema)
        finally:DurableCalls.__call__=original

    def test_rebatched_subset_uses_only_matching_saved_vectors(self):
        first=[2.0]+[0.0]*(DIMENSIONS-1);second=[3.0]+[0.0]*(DIMENSIONS-1)
        result=runner.fill_saved_embeddings({'one':first},['one','two','unknown'],{'one':second,'two':second})
        self.assertIs(result['one'],first);self.assertIs(result['two'],second);self.assertNotIn('unknown',result)

    def test_private_receipts_bind_text_model_dimensions_and_hashes(self):
        directory,path,requests,responses=self.receipt()
        try:
            saved,receipts=runner.load_embedding_receipts(path,requests,responses)
            self.assertEqual(set(saved),{digest('alpha'),digest('beta')})
            self.assertEqual([row['call_index'] for row in receipts],[22,23])
        finally:directory.cleanup()

    def test_virtual_claim_primes_both_original_embedding_calls(self):
        directory,path,requests,responses=self.receipt();artifact=json.loads(path.read_text())
        try:
            with patch.object(runner.evidence.replay,'EXPECTED_HASHES',tuple(requests)), \
                 patch.object(runner.evidence,'EXPECTED_RESPONSE_HASHES',tuple(responses)):
                saved,receipts=runner.load_embedding_receipts(path,requests,responses)
                guarded=runner.ReplayOnlyTargetStore(
                    runner.evidence.SavedResponseStore(RecordStore(artifact['calls'])),
                    {'id':runner.evidence.replay.JOB_ID},saved,receipts)
                guarded.call('claim_job',pipeline=runner.evidence.replay.OLD_PIPELINE,
                             lease_token='12345678-1234-1234-1234-123456789abc')
                self.assertEqual(guarded.seen,{22,23})
        finally:directory.cleanup()

    def test_wrong_request_or_response_identity_stops(self):
        for key in ('request_hash','response_hash'):
            directory,path,requests,responses=self.receipt(lambda value,k=key:value['calls'][0].__setitem__(k,'0'*64))
            try:
                with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'identity changed'):
                    runner.load_embedding_receipts(path,requests,responses)
            finally:directory.cleanup()

    def test_wrong_cache_scope_stops(self):
        directory,path,requests,responses=self.receipt(lambda value:value.__setitem__('space_id','wrong'))
        try:
            with self.assertRaisesRegex(RuntimeError,'scope changed'):
                runner.load_embedding_receipts(path,requests,responses)
        finally:directory.cleanup()


if __name__=='__main__':unittest.main()
