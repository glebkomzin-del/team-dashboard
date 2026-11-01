import threading,time,unittest
import tempfile
from unittest.mock import Mock

from journal_service import JournalService
from journal_store import RevisionConflict
from question_jobs import QuestionJobs


OWNER={'id':'00000000-0000-4000-8000-000000000001','role':'owner'}
REQUEST={'request_id':'20000000-0000-4000-8000-000000000001','question':'Was ist offen?'}


class QuestionJobTests(unittest.TestCase):
    def test_polling_runs_one_background_copy_and_returns_result(self):
        gate=threading.Event();service=Mock()
        def answer(identity,request):
            gate.wait(1);return {'request_id':request['request_id'],'answer':'ok'}
        service.answer.side_effect=answer
        jobs=QuestionJobs()
        self.assertEqual(jobs.submit(service,OWNER,REQUEST)['state'],'processing')
        self.assertEqual(jobs.submit(service,OWNER,REQUEST)['state'],'processing')
        gate.set()
        for _ in range(100):
            result=jobs.submit(service,OWNER,REQUEST)
            if result.get('state')!='processing':break
            time.sleep(.01)
        self.assertEqual(result['answer'],'ok');self.assertEqual(service.answer.call_count,1)

    def test_same_identity_rejects_changed_payload_while_running(self):
        gate=threading.Event();service=Mock()
        service.answer.side_effect=lambda *_:gate.wait(1)
        jobs=QuestionJobs();jobs.submit(service,OWNER,REQUEST)
        with self.assertRaises(RevisionConflict):jobs.submit(service,OWNER,{**REQUEST,'question':'Andere Frage'})
        gate.set()

    def test_background_error_is_delivered_by_poll(self):
        service=Mock();service.answer.side_effect=ValueError('bad')
        jobs=QuestionJobs();jobs.submit(service,OWNER,REQUEST)
        for _ in range(100):
            try:result=jobs.submit(service,OWNER,REQUEST)
            except ValueError:break
            self.assertEqual(result['state'],'processing');time.sleep(.01)
        else:self.fail('Background error was not delivered')

    def test_long_poll_returns_fast_completion_without_a_processing_round_trip(self):
        service=Mock();service.answer.return_value={'request_id':REQUEST['request_id'],'answer':'ok'}
        result=QuestionJobs().submit(service,OWNER,REQUEST,wait_seconds=1)
        self.assertEqual(result['answer'],'ok');service.answer.assert_called_once()

    def test_privacy_maintenance_waits_for_answer_storage_then_clears_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=JournalService(Mock(),tmp);jobs=QuestionJobs();journal.register_privacy_cleanup(jobs.clear_completed)
            entered=threading.Event();release=threading.Event();finished=threading.Event()
            service=Mock();service.journal=journal
            def answer(*_args):entered.set();release.wait(2);return {'request_id':REQUEST['request_id'],'answer':'private'}
            service.answer.side_effect=answer;jobs.submit(service,OWNER,REQUEST);self.assertTrue(entered.wait(1))
            def maintain():
                with journal.exclusive_privacy_maintenance():journal.clear_private_runtime()
                finished.set()
            thread=threading.Thread(target=maintain);thread.start()
            self.assertFalse(finished.wait(.05));release.set();self.assertTrue(finished.wait(1));thread.join(1)
            self.assertEqual(jobs.jobs,{})


if __name__=='__main__':unittest.main()
