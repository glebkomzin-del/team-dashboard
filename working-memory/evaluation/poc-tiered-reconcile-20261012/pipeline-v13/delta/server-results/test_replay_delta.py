"""Offline synthetic checks: cost gate, crash durability, response handling and quality."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

r = load('replay_delta')
c = load('compare_delta')


def fixture():
    return {'job_id': 'fixture', 'call_index': 0, 'replay_id': 'fixture:0:delta',
            'request_json': {'prompt': 'synthetic', 'schema': {'type': 'object',
             'properties': {'ok': {'type':'boolean'}}, 'required': ['ok'], 'additionalProperties':False}, 'max_tokens':100},
            'max_output_tokens':100, 'reference_usage': {'input_tokens':100,'output_tokens':100}}


def answer(status='completed', usage=True):
    body = {'status':status,'model':r.MODEL,'service_tier':'default',
            'output':[{'type':'message','role':'assistant','status':'completed',
            'content':[{'type':'output_text','text':'{"ok":true}'}]}]}
    if usage: body['usage']={'input_tokens':10,'output_tokens':10}
    return {'http_status':200,'raw_response':json.dumps(body)}


class ReplayTests(unittest.TestCase):
    def test_dryrun_no_transport(self):
        result = r.replay([fixture()])
        self.assertEqual(result['calls'],1)
        self.assertEqual(result['attempts'],0)
    def test_payload_parameters(self):
        p=r.build_request(fixture())
        self.assertEqual(p['reasoning'],{'effort':'medium'})
        self.assertEqual(p['prompt_cache_options'],{'mode':'explicit'})
        self.assertEqual(p['max_output_tokens'],100)
        self.assertTrue(p['text']['format']['strict'])
    def test_reserve_utf8_all_cachewrite(self):
        f=fixture(); f['request_json']['prompt']='ä'*100
        p=r.build_request(f)
        expected=200+len(json.dumps(p['text']['format']['schema'],ensure_ascii=False).encode())+4096
        self.assertEqual(r.estimate(f)['reserved_input_tokens'],expected)
        self.assertEqual(r.estimate(f)['reserved_micro_usd'],int(expected*2.5+1000))
    def test_reference_input_lower_bound(self):
        f=fixture(); f['reference_usage']['input_tokens']=100000
        self.assertEqual(r.estimate(f)['reserved_input_tokens'],100000)
    def test_observed_anchor_positive_deltas(self):
        f=fixture(); f['reference_request_json']=dict(f['request_json'])
        f['request_json']=dict(f['request_json']); f['request_json']['prompt']+='ä'
        self.assertEqual(r.estimate(f)['reserved_input_tokens'],100+2+4096)
    def test_invalid_anchor_rejected(self):
        f=fixture(); f['reference_request_json']={}
        with self.assertRaises(ValueError):r.estimate(f)
    def test_hard_cap(self):
        with self.assertRaises(ValueError):r.replay([fixture()],1000001)
    def test_selection_gate_before_transport(self):
        called=[]; events=[]
        result=r.replay([fixture()],1,lambda p:called.append(p),events.append)
        self.assertEqual(result['blocked'],1); self.assertEqual(called,[]); self.assertEqual(events,[])
    def test_reservation_precedes_transport(self):
        events=[]
        def transport(p):
            self.assertEqual(events[0]['record_type'],'reservation')
            return answer()
        result=r.replay([fixture()],transport=transport,writer=events.append)
        self.assertEqual(result['attempts'],1)
        self.assertEqual(events[1]['status'],'ok')
        self.assertEqual(events[1]['raw_response'],answer()['raw_response'])
        self.assertEqual(result['actual_micro_usd'],120)
    def test_unknown_usage_stops(self):
        a=fixture(); b=fixture(); b.update(call_index=1,replay_id='fixture:1:delta')
        events=[]
        result=r.replay([a,b],transport=lambda p:answer(usage=False),writer=events.append)
        self.assertEqual(result['attempts'],1)
        self.assertEqual(result['stopped'],'uncertain_budget')
        self.assertTrue(r.prior_state(events)['blocked'])
    def test_crash_reservation_blocks_restart(self):
        event=dict(fixture(),record_type='reservation',reserved_micro_usd=100)
        result=r.replay([fixture()],previous=[event])
        self.assertEqual(result['blocked'],1)
        self.assertEqual(result['calls'],0)
    def test_completed_attempt_never_repeated(self):
        events=[]
        r.replay([fixture()],transport=lambda p:answer(),writer=events.append)
        result=r.replay([fixture()],previous=events)
        self.assertEqual(result['skipped'],1); self.assertEqual(result['calls'],0)
        self.assertEqual(result['previous_micro_usd'],120)
    def test_previous_cost_applies_to_budget(self):
        events=[]; r.replay([fixture()],transport=lambda p:answer(),writer=events.append)
        f=fixture();f.update(call_index=1,replay_id='fixture:1:delta')
        result=r.replay([f],r.estimate(f)['reserved_micro_usd'],previous=events)
        self.assertEqual(result['blocked'],1)
    def test_nonfinal_response_not_ok(self):
        events=[]
        result=r.replay([fixture()],transport=lambda p:answer('incomplete'),writer=events.append)
        self.assertEqual(result['failed'],1); self.assertEqual(events[-1]['status'],'error')
    def test_duplicate_identity_rejected(self):
        with self.assertRaises(ValueError):r.replay([fixture(),fixture()])
    def test_duplicate_terminal_stream_invalid(self):
        body=json.loads(answer()['raw_response'])
        event='data: '+json.dumps({'type':'response.completed','response':body})+'\n\n'
        _,error=r.common.response_body(event+event)
        self.assertIsNotNone(error)
    def test_partial_stream_retained(self):
        raw='data: {"type":"response.output_text.delta","delta":"synthetic"}\n\n'
        events=[]
        result=r.replay([fixture()],transport=lambda p:{'http_status':200,'raw_response':raw},writer=events.append)
        self.assertEqual(events[-1]['raw_response'],raw)
        self.assertEqual(result['blocked'],1)


class CompareTests(unittest.TestCase):
    def full(self):
        return {'observations':[{'source_index':0,'update_target':None,'update':None,'matter_id':None}],
                'work_results':{'0':'unchanged'},'open_ids':[]}
    def test_positive_decision_and_coverage(self):
        f=self.full(); result=c.compare_full(f,f)
        self.assertEqual(result,dict(coverage=1,decisions=1,lifecycle=1,final=1))
    def test_missing_coverage_rejects_decisions(self):
        f=self.full(); a=self.full(); a['observations']=[]
        result=c.compare_full(a,f)
        self.assertEqual(result['coverage'],0);self.assertEqual(result['decisions'],0)
    def test_decision_change_rejected(self):
        f=self.full(); a=self.full(); a['observations'][0]['update_target']='1'
        self.assertEqual(c.compare_full(a,f)['decisions'],0)
    def test_lifecycle_details_rejected(self):
        f=self.full(); a=self.full()
        f['work_results']={'0':{'action':'close','evidence_ids':['1']}}
        a['work_results']={'0':{'action':'close','evidence_ids':['2']}}
        self.assertEqual(c.compare_full(a,f)['lifecycle'],0)
    def test_open_ids_nonfinal(self):
        f=self.full(); f['open_ids']=['1']
        self.assertEqual(c.compare_full(f,f)['final'],0)
    def compare_record(self):
        obs_schema={'type':'object','properties':{'source_index':{'type':'integer'},
             **{k:{'type':['string','null']} for k in ('update_target','update','matter_id')}},
             'required':['source_index','update_target','update','matter_id'],'additionalProperties':False}
        full_schema={'type':'object','properties':{'observations':{'type':'array','items':obs_schema},
             'work_results':{'type':['object','null']},'open_ids':{'type':'array','items':{'type':'string'}}},
             'required':['observations','work_results','open_ids'],'additionalProperties':False}
        f=self.full()
        return dict(reference_schema=full_schema,reference_full=f,obs_in=f['observations'],
             work=[{}],request_json={'schema':{'type':'object'}},reference_usage={'output_tokens':100})
    def test_compare_attempt_semantic_decision(self):
        record=self.compare_record()
        delta=c.codec.to_delta(record['reference_full'],record['obs_in'],record['work'])
        attempt={'status':'ok','text':json.dumps(delta),'usage':{'output_tokens':10}}
        result=c.compare_attempt(attempt,record)
        self.assertEqual(result['accepted'],1)
        delta['observations'][0]['changes']=[{'update_target':'1'}]
        attempt['text']=json.dumps(delta)
        result=c.compare_attempt(attempt,record)
        self.assertEqual(result['schema'],1)
        self.assertEqual(result['decisions'],0)
        self.assertEqual(result['accepted'],0)
    def test_compare_attempt_nonfinal_counts(self):
        record=self.compare_record()
        delta={'observations':[],'work_results':None,'open_ids':['H0']}
        result=c.compare_attempt({'status':'ok','text':json.dumps(delta),
             'usage':{'output_tokens':12}},record)
        self.assertEqual(result['schema'],1)
        self.assertEqual(result['final'],0)
        self.assertEqual(result['accepted'],0)
        self.assertEqual(result['output_tokens'],12)
        self.assertEqual(result['reference_output_tokens'],100)
    def test_type_sensitive(self):
        self.assertFalse(c.strict_equal(True,1))
    def test_duplicate_coverage_rejected(self):
        f=self.full();f['observations']*=2
        self.assertEqual(c.compare_full(f,f)['coverage'],0)

if __name__=='__main__':unittest.main()
