import importlib.util
from pathlib import Path
import unittest


SCRIPT=Path(__file__).parent.parent/'.codex-deploy/memory-20260920/replay_evidence_repair_job.py'
SPEC=importlib.util.spec_from_file_location('evidence_repair_runner',SCRIPT)
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)


class Store:
    space_id=runner.replay.SPACE_ID
    def __init__(self,response_hash):self.response_hash=response_hash
    def call(self,op,**fields):
        if op!='reserve_call':raise AssertionError(op)
        return {'response_hash':self.response_hash,'response_json':'{}','send':False}


class EvidenceRepairRunnerTests(unittest.TestCase):
    def detail(self):
        return {'job':{'id':runner.replay.JOB_ID},
                'calls':[{'index':i,'request_hash':value,'received':True}
                         for i,value in enumerate(runner.replay.EXPECTED_HASHES)]}

    def test_redacted_job_detail_accepts_valid_private_replay_hash(self):
        guarded=runner.guarded_store(Store(runner.EXPECTED_RESPONSE_HASHES[0]),self.detail())
        self.assertNotIn('response_hash',self.detail()['calls'][0])
        result=guarded.base.call('reserve_call',call_index=0)
        self.assertEqual(result['response_hash'],runner.EXPECTED_RESPONSE_HASHES[0])

    def test_redacted_job_detail_rejects_wrong_private_replay_hash(self):
        guarded=runner.guarded_store(Store('0'*64),self.detail())
        with self.assertRaisesRegex(RuntimeError,'Saved response identity changed'):
            guarded.base.call('reserve_call',call_index=0)


if __name__=='__main__':unittest.main()
