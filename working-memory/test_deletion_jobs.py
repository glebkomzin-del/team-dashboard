import threading,time,unittest
from unittest.mock import Mock

from deletion_jobs import DeletionJobs
from journal_store import RevisionConflict

OWNER={'id':'00000000-0000-4000-8000-000000000001','role':'owner'}
REQUEST={'deletion_id':'20000000-0000-4000-8000-000000000001','source_id':'drive:fixture'}


class DeletionJobTests(unittest.TestCase):
 def test_same_durable_identity_runs_once_and_can_be_polled(self):
  gate=threading.Event()
  def run(*_):gate.wait(1);return {'state':'verified'}
  executor=Mock(side_effect=run)
  jobs=DeletionJobs();self.assertEqual(jobs.submit(executor,object(),OWNER,REQUEST)['state'],'processing')
  self.assertEqual(jobs.submit(executor,object(),OWNER,REQUEST)['state'],'processing');gate.set()
  for _ in range(100):
   result=jobs.submit(executor,object(),OWNER,REQUEST)
   if result.get('state')!='processing':break
   time.sleep(.01)
  self.assertEqual(result['state'],'verified');self.assertEqual(executor.call_count,1)
 def test_changed_source_for_same_deletion_id_is_rejected(self):
  gate=threading.Event();jobs=DeletionJobs();jobs.submit(lambda *_:gate.wait(1),object(),OWNER,REQUEST)
  with self.assertRaises(RevisionConflict):jobs.submit(lambda *_:None,object(),OWNER,{**REQUEST,'source_id':'drive:changed'})
  gate.set()


if __name__=='__main__':unittest.main()
