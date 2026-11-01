import tempfile
from pathlib import Path
import unittest
from memory import connect, register, claim, apply, overview, validate
from test_memory import TEXT, observation, proposal
from context_window import retrieval
from temporal_guard import guard
from reconcile import candidates


class IdentityAndTimeTests(unittest.TestCase):
    def test_anonymous_labels_never_become_identified_work(self):
        for name in ('Speaker 1', 'Speaker 2', 'Sprecher 3', 'Unknown Speaker'):
            checked=validate(proposal(observation(owner=name)),TEXT,set())[0]
            self.assertFalse(checked['creates_work'])
            self.assertEqual(checked['unresolved_speaker_label'],name)
            self.assertTrue(checked['required_review'])
        self.assertTrue(validate(proposal(observation(owner='Gleb')),TEXT,set())[0]['creates_work'])

    def test_same_day_has_identity_only_and_cannot_close_existing_work(self):
        with tempfile.TemporaryDirectory() as directory:
            db=connect(Path(directory)/'memory.sqlite')
            jid=register(db,source_id='drive:a',event_date='2026-07-15',title='A',transcript=TEXT)
            apply(db,jid,claim(db,jid),proposal(observation()),model='fixture')
            work=overview(db)['personal'][0]
            meeting={'meeting_date':'2026-07-15','title':'B','raw_transcript':TEXT}
            retrieved=retrieval(db,meeting,prior_days_only=True)
            self.assertEqual(retrieved['work'],[])
            self.assertEqual(retrieved['observations'],[])
            self.assertEqual(retrieved['unordered_same_day_work'][0]['id'],work['id'])
            self.assertNotIn('status',retrieved['unordered_same_day_work'][0])
            self.assertEqual(candidates(db,meeting,proposal(),prior_days_only=True),[])
            change=proposal(observation(kind='status',update_target=work['id'],update='done'))
            guarded=guard(db,meeting,change)['observations'][0]
            self.assertEqual(guarded['update'],'none')
            self.assertTrue(guarded['required_review'])
            tomorrow={**meeting,'meeting_date':'2026-07-16'}
            self.assertEqual(retrieval(db,tomorrow,prior_days_only=True)['work'][0]['id'],work['id'])
            self.assertEqual(len(candidates(db,tomorrow,proposal(),prior_days_only=True)),1)
            db.close()


if __name__=='__main__':unittest.main()
