import copy
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
from unittest import mock
ROOT=Path(__file__).resolve().parent

def load(name):
    s=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
build=load('build_filtered_requests');selection=load('select_calls')

def fixture(job='test',index=1,padding=0):
    packed={'tables':{'work':{'fields':['id','title','work_index'],'text_fields':['title','work_index'],'rows':[['W1',2,0],['W2',3,1]]}},'texts':['7','19','shared','removed'],'metadata':{'archive_navigation':{'texts':['archive'],'tables':{'work':{'rows':[[0]]}}}},'format':'packed'}
    schema={'type':'object','properties':{'work_results':{'anyOf':[{'type':'object','properties':{'7':{'type':'string'},'19':{'type':'string'}},'required':['7','19'],'additionalProperties':False},{'type':'null'}]},'observations':{'type':'array','items':{'type':'object','properties':{'update_target':{'enum':[None,'W1','W2']}},'required':['update_target'],'additionalProperties':False}},'open_ids':{'type':'array','items':{'type':'string'}}},'required':['work_results','observations','open_ids'],'additionalProperties':False}
    return {'job_id':job,'call_index':index,'request_json':{'prompt':'prefix\nKandidaten:\n'+json.dumps(packed)+'\nsuffix'+'x'*padding,'schema':schema,'max_tokens':100,'transport':{'reasoning_effort':'medium'}},'reference_text':json.dumps({'work_results':{'7':'done','19':'unchanged'},'observations':[{'update_target':'W1'}],'open_ids':[]})}

class BuildTests(unittest.TestCase):
    def test_reduction_and_namespace_identity(self):
        source=fixture();result=build.filter_record(source,['W2']);prefix,p,suffix=build.unpack_prompt(result['request_json']['prompt'])
        self.assertEqual(prefix,'prefix\nKandidaten:\n');self.assertEqual(suffix,'\nsuffix');self.assertEqual(p['texts'],['7','shared']);self.assertEqual(p['tables']['work']['rows'],[['W1',1,0]])
        self.assertEqual(p['metadata'],build.unpack_prompt(source['request_json']['prompt'])[1]['metadata']);self.assertEqual(build.aliases(p),{'W1':'7'})
        props=result['request_json']['schema']['properties'];self.assertEqual(props['work_results']['anyOf'][0]['required'],['7']);self.assertEqual(props['observations']['items']['properties']['update_target']['enum'],[None,'W1'])
        self.assertLess(len(result['request_json']['prompt']),len(source['request_json']['prompt']));self.assertEqual(result['original_request_json'],source['request_json']);self.assertEqual(result['filter_metadata']['alias_work_indices'],{'W1':'7','W2':'19'})
    def test_shared_text_survives(self):
        r=fixture();pre,p,suf=build.unpack_prompt(r['request_json']['prompt']);p['tables']['work']['rows'][1][1]=2;r['request_json']['prompt']=pre+json.dumps(p)+suf
        self.assertEqual(build.unpack_prompt(build.filter_record(r,['W2'])['request_json']['prompt'])[1]['texts'],['7','shared'])
    def test_missing_text_cell_preserved(self):
        r=fixture();pre,p,suf=build.unpack_prompt(r['request_json']['prompt'])
        p['tables']['work']['rows'][0][1]={'missing':True}
        r['request_json']['prompt']=pre+json.dumps(p)+suf
        row=build.unpack_prompt(build.filter_record(r,['W2'])['request_json']['prompt'])[1]['tables']['work']['rows'][0]
        self.assertEqual(row,['W1',{'missing':True},0])
    def test_prefix_collision_rejected(self):
        a=fixture('testtest-a');b=fixture('testtest-b')
        rows=[{'job':'testtest','index':1,'alias':alias,'age':31,'best':5,'exact':False} for alias in ('W1','W2')]
        with self.assertRaises(ValueError):build.decision_rows({'rows':rows},[a,b])
    def test_unknown_removed_alias(self):
        with self.assertRaises(ValueError):build.filter_record(fixture(),['W404'])
    def test_missing_unknown_evidence(self):
        rows=[{'job':'test','index':1,'alias':'W1','age':31,'best':5,'exact':False}]
        with self.assertRaises(ValueError):build.decision_rows({'rows':rows},[fixture()])
        rows.append(dict(rows[0],alias='W2',age=None))
        with self.assertRaises(ValueError):build.decision_rows({'rows':rows},[fixture()])
        rows[1]['age']=30;self.assertEqual(build.decision_rows({'rows':rows},[fixture()])[0]['removed_aliases'],['W1'])
    def test_hotset_or_boundaries(self):
        rows=[{'job':'test','index':1,'alias':'W1','age':31,'best':4,'exact':False},{'job':'test','index':1,'alias':'W2','age':31,'best':5,'exact':True}]
        self.assertEqual(build.decision_rows({'rows':rows},[fixture()])[0]['removed_aliases'],[])
    def test_endform_used_positive_negative_unknown(self):
        r=fixture();self.assertTrue(build.is_final_used(r))
        for value in (None,'invalid',json.dumps({'work_results':None,'observations':[],'open_ids':[]})):
            other=copy.deepcopy(r);other['reference_text']=value;self.assertFalse(build.is_final_used(other))
        for answer in ({'work_results':{'7':'unchanged','19':'unchanged'},'observations':[],'open_ids':[]},{'work_results':{'7':'done'},'observations':[],'open_ids':[]}):
            other=copy.deepcopy(r);other['reference_text']=json.dumps(answer);self.assertFalse(build.is_final_used(other))

class SelectionTests(unittest.TestCase):
    def records(self):return [build.filter_record(fixture('4e7b6e03-mandatory' if i==3 else str(i),i,i*10),['W2']) for i in range(4)]
    def test_budget_mandatory_controls(self):
        rs=self.records();unit=selection.estimate(rs[-1]);out,summary=selection.select(rs,unit*3,950000)
        self.assertEqual(summary['filtered_calls'],3);self.assertEqual(summary['control_calls'],3);self.assertTrue(summary['feasible']);self.assertTrue(all(r['selection_budget']['feasible'] for r in out));self.assertLessEqual(summary['filtered_upper_micro_usd'],unit*3);self.assertLessEqual(summary['control_upper_micro_usd'],950000);self.assertEqual(len({r['replay_id'] for r in out}),6)
        self.assertTrue(any(r['job_id'].startswith('4e7b6e03') and r['replay_variant']=='filtered' for r in out))
        self.assertEqual([r['job_id'] for r in out[:3]],[r['job_id'] for r in out[3:]])
        for r in out[3:]:self.assertEqual(r['request_json'],r['original_request_json']);self.assertEqual(r['filter_metadata']['removed_aliases'],[])
    def test_invalid_budget_rejected(self):
        from decimal import Decimal
        for cap in (0,-1,Decimal('NaN'),Decimal('Infinity'),Decimal('1'),True):
            with self.assertRaises(ValueError):selection.select(self.records(),cap,950000)
    def test_budget_and_mandatory_failures(self):
        with self.assertRaises(ValueError):selection.select(self.records(),1,950000)
        planned,summary=selection.select(self.records(),2500000,1)
        self.assertFalse(summary['feasible']);self.assertTrue(summary['infeasible_control_budget'])
        self.assertTrue(all(not r['selection_budget']['feasible'] for r in planned))
        self.assertEqual(sum(r['replay_variant']=='control' for r in planned),3)
        self.assertEqual(summary['control_budget_micro_usd'],1)
        self.assertGreater(summary['control_upper_micro_usd'],summary['control_budget_micro_usd'])
        self.assertEqual(summary['minimum_possible_control_micro_usd'],summary['control_upper_micro_usd'])
        with self.assertRaises(ValueError):selection.select(self.records()[:3])

    def test_cache_write_estimate_and_rounding(self):
        r=self.records()[0];source=r['request_json']
        from decimal import Decimal, ROUND_CEILING
        tokens=int((Decimal(len(source['prompt'])+len(json.dumps(source['schema'],ensure_ascii=False)))/Decimal('3.6')).to_integral_value(rounding=ROUND_CEILING))
        expected=int((Decimal(tokens)*Decimal('2.50')+160000).to_integral_value(rounding=ROUND_CEILING))
        self.assertEqual(selection.estimate(r),expected)

    def test_remaining_skip_multiple_files_and_keep_controls(self):
        planned,_=selection.select(self.records())
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            a=Path(temp)/'a.jsonl';b=Path(temp)/'b.jsonl'
            a.write_text(json.dumps(planned[0])+'\n');b.write_text(json.dumps(planned[1])+'\n')
            remaining,summary=selection.remaining_selection(planned,[a,b])
            self.assertEqual(summary['skipped_done_calls'],2)
            self.assertEqual(summary['filtered_calls'],2)
            self.assertEqual(summary['control_calls'],3)
            self.assertTrue(summary['feasible'])
            self.assertFalse({planned[0]['replay_id'],planned[1]['replay_id']} & {r['replay_id'] for r in remaining})

    def test_remaining_prunes_largest_filtered_never_controls(self):
        planned,_=selection.select(self.records())
        costs={r['replay_id']:i*100+100 for i,r in enumerate(planned)}
        # Controls alone cost 500+600+700; remove 400 and then 300 filtered.
        with mock.patch.object(selection,'estimate',side_effect=lambda r:costs[r['replay_id']]):
            remaining,summary=selection.remaining_selection(planned,[],2100)
        self.assertEqual(summary['before_reduction_upper_micro_usd'],2800)
        self.assertEqual(summary['removed_largest_filtered_calls'],2)
        self.assertEqual(summary['filtered_calls'],2)
        self.assertEqual(summary['control_calls'],3)
        self.assertLessEqual(summary['total_upper_micro_usd'],2100)
        self.assertEqual({r['replay_id'] for r in remaining if r['replay_variant']=='control'},
                         {r['replay_id'] for r in planned if r['replay_variant']=='control'})
        filtered=[r for r in remaining if r['replay_variant']=='filtered']
        self.assertEqual({costs[r['replay_id']] for r in filtered},{100,200})

    def test_remaining_invalid_evidence_and_control_budget(self):
        planned,_=selection.select(self.records())
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'invalid.jsonl';path.write_text(json.dumps({'replay_id':planned[0]['replay_id']})+'\n')
            with self.assertRaises(ValueError):selection.remaining_selection(planned,[path])
        with mock.patch.object(selection,'estimate',return_value=400000):
            remaining,summary=selection.remaining_selection(planned,[],1000000)
        self.assertFalse(summary['feasible'])
        self.assertEqual(summary['control_calls'],3)

if __name__=='__main__':unittest.main()
