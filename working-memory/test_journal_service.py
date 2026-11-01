from contextlib import contextmanager
from datetime import datetime,timezone
import tempfile,threading,time,unittest
from unittest.mock import Mock,patch
from memory import connect,ValidationError
from journal_projection import apply_saved,prepare_source
from journal_service import JournalService,business_date
from journal_store import RevisionConflict

OWNER={'id':'00000000-0000-4000-8000-000000000001','role':'owner'}
SPACE={'id':'10000000-0000-4000-8000-000000000001','owner_id':OWNER['id'],'revision':3}
REQUEST={'command_id':'20000000-0000-4000-8000-000000000001','expected_revision':3,
         'action':'reject','target_id':'fixture','reason':'Original geprüft','patch':{}}
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Mock();self.store.space.return_value=SPACE
        self.store.command.return_value=None;self.service=JournalService(self.store,self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_other_owner_and_service_cannot_submit_human_decision(self):
        for identity in ({**OWNER,'id':'other'},{**OWNER,'role':'service'}):
            with self.assertRaises(PermissionError):self.service.decide(identity,REQUEST)
        self.store.append.assert_not_called()
    def test_repeat_across_dates_uses_saved_receipt(self):
        self.store.command.return_value={'kind':'human','actor_id':OWNER['id'],'revision':2,
            'payload':{'action':'reject','target_id':'fixture','reason':'Original geprüft','patch':{},'event_date':'2026-01-01'}}
        self.assertEqual(self.service.decide(OWNER,REQUEST),{'revision':2,'repeated':True})
        self.store.append.assert_not_called()
    def test_changed_repeat_and_stale_revision_are_not_silently_saved(self):
        self.store.command.return_value={'kind':'human','actor_id':OWNER['id'],'revision':2,'payload':{}}
        with self.assertRaises(RevisionConflict):self.service.decide(OWNER,REQUEST)
        self.store.command.return_value=None
        with self.assertRaises(RevisionConflict):self.service.decide(OWNER,{**REQUEST,'expected_revision':2})
        self.store.append.assert_not_called()
    def test_actor_and_event_date_are_server_bound(self):
        @contextmanager
        def projection(identity):yield Mock(),SPACE
        with patch.object(self.service,'projection',projection),patch('journal_service.prepare'):
            self.service.decide(OWNER,REQUEST)
        args=self.store.append.call_args.kwargs
        self.assertEqual(args['actor_id'],OWNER['id'])
        self.assertEqual(args['payload']['event_date'],business_date())
        with self.assertRaises(ValidationError):self.service.decide(OWNER,{**REQUEST,'actor_id':'forged'})

    def test_decision_day_uses_berlin_even_before_utc_midnight(self):
        self.assertEqual(business_date(datetime(2026,9,6,22,30,tzinfo=timezone.utc)),'2026-09-07')
        self.assertEqual(business_date(datetime(2026,1,6,22,30,tzinfo=timezone.utc)),'2026-01-06')

    def test_cache_maintenance_drains_active_readers_and_blocks_new_ones(self):
        release=threading.Event();reader_open=threading.Event();maintenance_open=threading.Event()
        def reader():
            with self.service.cache_reader():reader_open.set();release.wait(1)
        first=threading.Thread(target=reader);first.start();self.assertTrue(reader_open.wait(1))
        def maintenance():
            with self.service.exclusive_cache_maintenance():maintenance_open.set()
        worker=threading.Thread(target=maintenance);worker.start();time.sleep(.02)
        self.assertFalse(maintenance_open.is_set())
        release.set();first.join(1);self.assertTrue(maintenance_open.wait(1));worker.join(1)
        self.assertFalse(first.is_alive() or worker.is_alive())

if __name__=='__main__':unittest.main()
