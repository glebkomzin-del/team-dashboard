import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from memory import connect, register, claim, record_failure, ValidationError
from service_worker import next_job, policy, Worker
from call_budget import BudgetExceeded


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'memory.sqlite'
        self.db=connect(self.path)
    def tearDown(self):
        self.db.close();self.directory.cleanup()
    def add(self,day,pipeline='p'):
        return register(self.db,source_id='drive:'+day,event_date=day,title=day,transcript='Original '+day,pipeline=pipeline)
    def test_earlier_failure_blocks_later_meeting(self):
        first=self.add('2026-09-07');self.add('2026-09-08')
        token=claim(self.db,first);record_failure(self.db,first,token,'semantic failure')
        row,state=next_job(self.db,'p','2026-09-07')
        self.assertIsNone(row);self.assertEqual(state['reason'],'earlier_job_failed')
        self.assertEqual(state['job_id'],first)
    def test_active_lease_blocks_later_and_expired_retry_is_bounded(self):
        first=self.add('2026-09-07');self.add('2026-09-08')
        claim(self.db,first,now=100,seconds=50)
        self.assertEqual(next_job(self.db,'p','2026-09-07',120)[1]['reason'],'earlier_job_leased')
        self.assertEqual(next_job(self.db,'p','2026-09-07',151)[0]['job_id'],first)
        self.db.execute('UPDATE jobs SET attempts=3 WHERE id=?',(first,))
        self.assertEqual(next_job(self.db,'p','2026-09-07',151)[1]['reason'],'attempt_limit')
    def test_changed_pipeline_does_not_skip_old_jobs(self):
        self.add('2026-09-07','old');self.add('2026-09-08','new')
        self.assertEqual(next_job(self.db,'new','2026-09-07')[1]['reason'],'pipeline_changed')
    def test_legacy_date_never_runs_even_if_just_registered(self):
        self.add('2026-06-01');self.add('2026-09-07')
        self.assertEqual(next_job(self.db,'p','2026-09-07')[1]['reason'],'legacy_requires_direct_review')
    def test_applied_sources_do_not_block_future_work(self):
        first=self.add('2026-06-01');second=self.add('2026-09-07')
        self.db.execute("UPDATE jobs SET status='applied' WHERE id=?",(first,))
        self.assertEqual(next_job(self.db,'p','2026-09-07')[0]['job_id'],second)
    def test_budget_date_and_rules_are_mandatory(self):
        with patch('processor.PROMPT_VERSION','v9'),patch('processor.ACTION_GATE',True):
            for env in ({},{'MEMORY_AUTOMATIC_FROM_DATE':'2026-09-07'},
                        {'MEMORY_AUTOMATIC_FROM_DATE':'2026-09-07','MEMORY_BUDGET_USD':'nan'},
                        {'MEMORY_AUTOMATIC_FROM_DATE':'2026-09-07','MEMORY_BUDGET_USD':'inf'}):
                with self.assertRaises((ValueError,ValidationError)):policy(env)
        with patch('processor.PROMPT_VERSION','v4'):
            with self.assertRaises(ValidationError):policy({'MEMORY_AUTOMATIC_FROM_DATE':'2026-09-07','MEMORY_BUDGET_USD':'1'})
    def test_every_injected_call_reserves_budget_and_restart_keeps_it(self):
        self.add('2026-09-07')
        env={'MEMORY_AUTOMATIC_FROM_DATE':'2026-09-07','MEMORY_BUDGET_USD':'1'}
        api=Mock(return_value={'error':'TimeoutError'})
        def fake_process(db,meeting,model,*,api):
            token=claim(db,meeting['id'])
            try:
                api('Initial extraction',model)
                api('Independent gate',model)  # Must exceed the remaining $1 fixture ceiling.
            except Exception as error:
                record_failure(db,meeting['id'],token,error);raise
        with patch('processor.PROMPT_VERSION','v9'),patch('processor.ACTION_GATE',True),patch('processor.pipeline_version',return_value='p'),patch('processor.anthropic',api),patch('processor.process',fake_process):
            worker=Worker(self.db,self.path,'claude-opus-5',env)
            status=worker.step();spent=status['accounted_usd'];worker.close()
            self.assertEqual(status['reason'],'BudgetExceeded');self.assertGreater(spent,.6)
            api.assert_called_once()
            worker=Worker(self.db,self.path,'claude-opus-5',env)
            self.assertEqual(worker.step()['reason'],'earlier_job_failed')
            self.assertEqual(worker.budget.total(),spent);worker.close()
            api.assert_called_once()

if __name__=='__main__':unittest.main()
