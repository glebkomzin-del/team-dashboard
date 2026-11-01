import tempfile
from pathlib import Path
import unittest
from memory import connect,register,claim,apply,record_failure,overview,context,ValidationError,BusyError,ReplayRequired

# Synthetic infrastructure fixtures; not counted as real-meeting quality labels.
TEXT = '00:01 Gleb: Ich sende den Bericht morgen.\n00:02 Gleb: Sobald die Kurse vorliegen, ist der Bericht möglich.'
def observation(**changes):
    return dict(matter='Monatsbericht',matter_id=None,kind='commitment',title='Bericht senden',claim='Gleb sendet den Bericht.',
        owner='Gleb',commitment_strength='explicit',due_text='morgen',update_target=None,update='none',
        quotes=[TEXT.splitlines()[0]],uncertainty=None,required_review=False,**changes) if not changes else {**observation(),**changes}
def proposal(*items): return {'observations':list(items),'coverage_notes':[]}

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'memory.sqlite';self.db=connect(self.path)
        self.job=register(self.db,source_id='drive:file-1',event_date='2026-07-15',title='Finance',transcript=TEXT)
    def tearDown(self): self.db.close();self.tmp.cleanup()
    def apply(self,p):
        token=claim(self.db,self.job)
        return apply(self.db,self.job,token,p,model='fixture')
    def test_repeated_import_does_not_duplicate_work(self):
        self.apply(proposal(observation()))
        again=register(self.db,source_id='drive:file-1',event_date='2026-07-15',title='Finance',transcript=TEXT)
        self.assertEqual(again,self.job);self.assertIsNone(claim(self.db,again))
        self.assertEqual(len(overview(self.db)['personal']),1)
    def test_parallel_connections_one_lease_owner(self):
        other=connect(self.path)
        try:
            claim(self.db,self.job)
            with self.assertRaises(BusyError): claim(other,self.job)
        finally: other.close()
    def test_expired_worker_cannot_apply_or_release_new_lease(self):
        old=claim(self.db,self.job,now=100,seconds=10)
        new=claim(self.db,self.job,now=111,seconds=100)
        with self.assertRaises(BusyError): apply(self.db,self.job,old,proposal(observation()),model='fixture',now=112)
        record_failure(self.db,self.job,old,'stale worker')
        apply(self.db,self.job,new,proposal(observation()),model='fixture',now=113)
        self.assertEqual(len(overview(self.db)['personal']),1)
    def test_invalid_second_observation_rolls_back_entire_projection(self):
        with self.assertRaises(ValidationError): self.apply(proposal(observation(),observation(quotes=['invented quote'])))
        self.assertEqual(self.db.execute('select count(*) from observations').fetchone()[0],0)
        self.assertEqual(self.db.execute('select count(*) from runs').fetchone()[0],1)
    def test_dependency_is_knowledge_without_personal_task(self):
        self.apply(proposal(observation(kind='dependency',commitment_strength='not_applicable',due_text=None,quotes=[TEXT.splitlines()[1]])))
        self.assertEqual(overview(self.db)['personal'],[])
        self.assertEqual(len(overview(self.db)['knowledge']),1)
    def test_unknown_update_target_rejected(self):
        with self.assertRaises(ValidationError): self.apply(proposal(observation(update='done',update_target='foreign-project-item')))
    def test_future_context_excluded(self):
        self.apply(proposal(observation()));self.assertEqual(context(self.db,'2026-07-14'),[])
    def test_changed_version_requires_replay_preserving_old_source(self):
        self.apply(proposal(observation()))
        job=register(self.db,source_id='drive:file-1',event_date='2026-07-15',title='Finance',transcript=TEXT+'\nCorrection')
        token=claim(self.db,job)
        with self.assertRaises(ReplayRequired): apply(self.db,job,token,proposal(observation()),model='fixture')
        self.assertEqual(self.db.execute('select count(*) from source_versions').fetchone()[0],2)
        self.assertEqual(len(overview(self.db)['personal']),1)
    def test_invented_due_expression_rejected(self):
        with self.assertRaises(ValidationError): self.apply(proposal(observation(due_text='2026-07-16')))
    def test_uncertain_close_does_not_finish_real_work(self):
        self.apply(proposal(observation()));wid=overview(self.db)['personal'][0]['id']
        job=register(self.db,source_id='drive:file-2',event_date='2026-07-16',title='Finance',transcript=TEXT)
        token=claim(self.db,job)
        apply(self.db,job,token,proposal(observation(kind='status',update='done',update_target=wid,uncertainty='Unsicherer Bezug')),model='fixture')
        self.assertEqual(len(overview(self.db)['personal']),1)
    def test_no_task_limit(self):
        self.apply(proposal(*(observation(title=f'Unabhängiges Ergebnis {i}') for i in range(30))))
        self.assertEqual(len(overview(self.db)['personal']),30)
    def test_review_flag_blocks_creation_even_without_uncertainty_text(self):
        self.apply(proposal(observation(required_review=True)))
        self.assertEqual(overview(self.db)['personal'],[])
        self.assertEqual(len(overview(self.db)['knowledge']),1)
    def test_review_flag_blocks_closure_even_with_positive_gate(self):
        self.apply(proposal(observation()));wid=overview(self.db)['personal'][0]['id']
        job=register(self.db,source_id='drive:needs-review',event_date='2026-07-16',title='Finance',transcript=TEXT)
        token=claim(self.db,job)
        apply(self.db,job,token,proposal(observation(kind='status',update='done',update_target=wid,
              required_review=True,action_uncertainty=None,work_gate={'verdict':'supported'})),model='fixture')
        self.assertEqual(len(overview(self.db)['personal']),1)
    def test_work_completed_in_meeting_is_not_open(self):
        text='00:02 Gleb: Ich habe den Bericht versendet.'
        self.job=register(self.db,source_id='drive:completed',event_date='2026-07-15',title='Fixture',transcript=text)
        self.apply(proposal(observation(work_state='done',quotes=[text],state_quotes=[text],due_text=None)))
        self.assertEqual(overview(self.db)['personal'],[])
        self.assertEqual(len(overview(self.db)['completed']),1)
    def test_real_conditional_commitment_kept_but_waiting(self):
        self.apply(proposal(observation(work_state='waiting',action_uncertainty=None,uncertainty='Zeitpunkt der Datenlieferung unbekannt',condition_text='Sobald die Kurse vorliegen',quotes=TEXT.splitlines())))
        self.assertEqual(overview(self.db)['personal'],[])
        self.assertEqual(len(overview(self.db)['waiting_dependencies']),1)
    def test_pipeline_upgrade_does_not_duplicate_imported_source(self):
        self.apply(proposal(observation()))
        again=register(self.db,source_id='drive:file-1',event_date='2026-07-15',title='Finance',transcript=TEXT,pipeline='new-model-new-prompt')
        self.assertEqual(again,self.job);self.assertIsNone(claim(self.db,again))
    def test_exact_matter_title_repairs_unknown_generated_id(self):
        self.apply(proposal(observation()))
        matter=self.db.execute('SELECT id FROM matters WHERE title=?',('Monatsbericht',)).fetchone()[0]
        job=register(self.db,source_id='drive:file-2',event_date='2026-07-16',title='Finance',transcript=TEXT)
        token=claim(self.db,job)
        wrong=('0' if matter[0]!='0' else '1')+matter[1:]
        apply(self.db,job,token,proposal(observation(kind='fact',commitment_strength='not_applicable',
              owner=None,due_text=None,matter_id=wrong)),model='fixture')
        row=self.db.execute('SELECT matter_id,data_json FROM observations WHERE job_id=?',(job,)).fetchone()
        self.assertEqual(row['matter_id'],matter)
        self.assertEqual(__import__('json').loads(row['data_json'])['matter_id'],matter)

if __name__=='__main__': unittest.main()
