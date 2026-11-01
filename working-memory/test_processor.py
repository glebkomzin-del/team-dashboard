import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import processor
from memory import connect,overview,ValidationError
from test_memory import observation

class ProcessorTests(unittest.TestCase):
    def setUp(self):
        # This legacy fixture contains v4 rules only; production env must not
        # silently route it through the v10/v11 durable pipeline.
        version_patch=patch.object(processor,'PROMPT_VERSION','v4');version_patch.start()
        self.addCleanup(version_patch.stop)
        self.gate_patch=patch.object(processor,'ACTION_GATE',False);self.gate_patch.start()
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'evaluation').mkdir()
        for name in ('prompt-v4.txt','schema-v4.json','source-corrections.json','work-gate-prompt.txt'):(self.root/'evaluation'/name).write_text((processor.ROOT/'evaluation'/name).read_text())
        self.db=connect(self.root/'db.sqlite');self.meeting={'id':'fixture','source_id':'fixture:one','meeting_date':'2026-07-15','title':'Fixture','raw_transcript':'00:01 Gleb: Ich sende den Bericht morgen.'}
    def tearDown(self):self.db.close();self.tmp.cleanup();self.gate_patch.stop()
    def response(self,due,tokens):
        o=observation(due_text=due);o.pop('quotes');o['evidence_ids']=['U0001']
        return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({'observations':[o],'coverage_notes':[]})}],'usage':{'input_tokens':tokens,'output_tokens':10},'elapsed_seconds':1}
    def test_repairs_invalid_time_once_and_counts_both_paid_calls(self):
        with patch.object(processor,'ROOT',self.root),patch.object(processor,'model_request',side_effect=[self.response('tomorrow',100),self.response('morgen',200)]) as api:
            result=processor.process(self.db,self.meeting,'fixture')
        self.assertEqual(api.call_count,2);self.assertEqual(result['repair_calls'],1)
        self.assertEqual(len(overview(self.db)['personal']),1)
        rows=self.db.execute('SELECT outcome,usage_json FROM runs ORDER BY rowid').fetchall()
        self.assertEqual([r['outcome'] for r in rows],['rejected','applied'])
        self.assertEqual(sum(json.loads(r['usage_json'])['input_tokens'] for r in rows),300)
    def test_repeated_invalid_output_never_promotes_partial_data(self):
        with patch.object(processor,'ROOT',self.root),patch.object(processor,'model_request',return_value=self.response('tomorrow',100)) as api:
            with self.assertRaises(ValidationError):processor.process(self.db,self.meeting,'fixture')
        self.assertEqual(api.call_count,2);self.assertEqual(overview(self.db)['personal'],[])
        self.assertEqual(self.db.execute('SELECT status FROM jobs').fetchone()[0],'failed')
    def test_incomplete_output_is_recorded_and_rejected(self):
        with patch.object(processor,'ROOT',self.root),patch.object(processor,'model_request',return_value={'stop_reason':'max_tokens','usage':{'output_tokens':16000},'elapsed_seconds':1}):
            with self.assertRaises(ValidationError):processor.process(self.db,self.meeting,'fixture')
        self.assertEqual(self.db.execute('SELECT outcome FROM runs').fetchone()[0],'provider_incomplete')
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_versions').fetchone()[0],1)
    def test_action_gate_runs_before_atomic_projection_and_counts_both_calls(self):
        gate={'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({'verdicts':[{'index':0,'verdict':'unsupported','reason':'Fixture rejection','evidence_ids':['U0001']}]})}],'usage':{'input_tokens':50,'output_tokens':10},'elapsed_seconds':1}
        with patch.object(processor,'ROOT',self.root),patch.object(processor,'ACTION_GATE',True),patch.object(processor,'model_request',side_effect=[self.response('morgen',100),gate]) as api:
            result=processor.process(self.db,self.meeting,'fixture')
        self.assertEqual(api.call_count,2);self.assertEqual(result['new_work'],0)
        self.assertEqual(len(overview(self.db)['knowledge']),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM runs').fetchone()[0],2)
    def test_provider_transport_error_remains_classifiable_for_bounded_retry(self):
        with patch.object(processor,'ROOT',self.root),patch.object(processor,'model_request',return_value={'stop_reason':None,'error':'TimeoutError','elapsed_seconds':1}):
            with self.assertRaisesRegex(ValidationError,'TimeoutError'):processor.process(self.db,self.meeting,'fixture')

if __name__=='__main__':unittest.main()
