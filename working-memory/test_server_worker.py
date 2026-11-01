import io
import json
import unittest
from contextlib import redirect_stderr
from unittest.mock import Mock,patch

import server
from journal_store import JournalUnavailable


class StopAfterWaits:
    def __init__(self,count):
        self.count=count;self.delays=[];self.states=[]

    def is_set(self):return len(self.delays)>=self.count

    def wait(self,delay):
        self.delays.append(delay);self.states.append(dict(server.WORKER_STATUS));return self.is_set()


class CanonicalWorkerLoopTests(unittest.TestCase):
    def run_loop(self,side_effect):
        worker=Mock();worker.step.side_effect=side_effect
        stop=StopAfterWaits(len(side_effect));stderr=io.StringIO();journal=Mock()
        with patch.multiple(server,JOURNAL=journal,STOP=stop,WORKER_STATUS={'state':'starting'}), \
             patch.object(server,'CanonicalWorker',return_value=worker) as constructor,redirect_stderr(stderr):
            server.work()
        return worker,constructor,stop,stderr.getvalue(),journal

    def test_unexpected_error_is_redacted_and_next_step_runs(self):
        worker,constructor,stop,diagnostics,journal=self.run_loop([
          RuntimeError('private transcript must never be logged'),{'state':'idle'}])

        constructor.assert_called_once_with(journal,server.MODEL)
        self.assertEqual(worker.step.call_count,2)
        self.assertEqual(stop.delays,[5,5])
        self.assertEqual(stop.states[0],{
          'state':'unavailable','reason':'unexpected_worker_error','retryable':True,
          'transient':False,'retry_in_seconds':5,'error_type':'RuntimeError'})
        self.assertEqual(stop.states[1],{'state':'idle'})
        self.assertNotIn('private transcript',diagnostics)
        diagnostic=json.loads(diagnostics)
        self.assertEqual((diagnostic['component'],diagnostic['error_type'],diagnostic['attempt']),
          ('canonical_worker','RuntimeError',1))
        self.assertTrue(diagnostic['frames'])
        self.assertEqual(set(diagnostic['frames'][0]),{'file','line','function'})

    def test_storage_error_is_classified_without_diagnostic_payload(self):
        worker,_,stop,diagnostics,_=self.run_loop([
          JournalUnavailable('private provider body'),{'state':'idle'}])

        self.assertEqual(worker.step.call_count,2)
        self.assertEqual(stop.states[0],{
          'state':'unavailable','reason':'storage_unavailable','retryable':True,
          'transient':False,'retry_in_seconds':5,'error_type':'JournalUnavailable'})
        self.assertEqual(stop.states[1],{'state':'idle'})
        self.assertEqual(diagnostics,'')

    def test_transport_error_is_classified_as_transient(self):
        worker,_,stop,diagnostics,_=self.run_loop([OSError('private host'),{'state':'idle'}])

        self.assertEqual(worker.step.call_count,2)
        self.assertEqual(stop.states[0],{
          'state':'unavailable','reason':'storage_unavailable','retryable':True,
          'transient':True,'retry_in_seconds':5,'error_type':'OSError'})
        self.assertEqual(stop.states[1],{'state':'idle'})
        self.assertEqual(diagnostics,'')

    def test_repeated_fault_backoff_is_bounded_and_resets_after_success(self):
        faults=[RuntimeError('redact') for _ in range(6)]
        worker,_,stop,diagnostics,_=self.run_loop([*faults,{'state':'idle'}])

        self.assertEqual(worker.step.call_count,7)
        self.assertEqual(stop.delays,[5,10,20,40,60,60,5])
        self.assertEqual(stop.states[-1],{'state':'idle'})
        self.assertEqual(len(diagnostics.strip().splitlines()),6)


if __name__=='__main__':unittest.main()
