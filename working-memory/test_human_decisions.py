import json,tempfile,unittest
from pathlib import Path
from uuid import uuid4
from memory import connect,register,claim,apply,overview,known_work_ids,ValidationError
from human_decisions import record
from test_memory import observation,proposal,TEXT

ACTOR='00000000-0000-4000-8000-000000000001'
class HumanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=connect(Path(self.tmp.name)/'memory.sqlite')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def source(self,obs,day='2026-07-15'):
        job=register(self.db,source_id='drive:'+day,event_date=day,title='Synthetic',transcript=TEXT)
        apply(self.db,job,claim(self.db,job),proposal(obs),model='fixture')
        return self.db.execute('SELECT id FROM observations WHERE job_id=?',(job,)).fetchone()[0]
    def decide(self,target,action,patch=None,day='2026-07-16',command_id=None,reason='Explizite synthetische Nutzerentscheidung'):
        return record(self.db,command_id=command_id or str(uuid4()),actor_id=ACTOR,
          command={'action':action,'target_id':target,'reason':reason,
                   'patch':patch or {},'event_date':day})
    def test_acceptance_and_rejection_notes_are_optional_but_corrections_still_need_context(self):
        accepted=self.source(observation(required_review=True))
        self.decide(accepted,'approve',reason='')
        rejected=self.source(observation(required_review=True),'2026-07-17')
        self.decide(rejected,'reject',day='2026-07-18',reason='')
        self.assertEqual(len(overview(self.db)['personal']),1)
        self.assertEqual(len(overview(self.db)['human_decisions']),2)
        with self.assertRaisesRegex(ValidationError,'reason'):
            self.decide(accepted,'correct',{'title':'Ohne Begründung'},day='2026-07-19',reason='')
    def test_confirm_uncertain_person_without_rewriting_evidence(self):
        oid=self.source(observation(owner='Speaker 1',required_review=True))
        original=self.db.execute('SELECT data_json FROM observations WHERE id=?',(oid,)).fetchone()[0]
        with self.assertRaises(ValidationError):self.decide(oid,'approve')
        self.decide(oid,'approve',{'owner':'Gleb'})
        self.assertEqual(len(overview(self.db)['personal']),1)
        self.assertIn(oid,known_work_ids(self.db))
        self.assertEqual(overview(self.db,'2026-07-15')['personal'],[])
        self.assertEqual(self.db.execute('SELECT data_json FROM observations WHERE id=?',(oid,)).fetchone()[0],original)
    def test_later_model_cannot_overwrite_manual_status(self):
        oid=self.source(observation())
        self.decide(oid,'set_status',{'status':'waiting'})
        update=self.source(observation(kind='status',update='done',update_target=oid),'2026-07-17')
        state=overview(self.db)
        self.assertEqual(state['completed'],[])
        self.assertEqual(len(state['waiting_dependencies']),1)
        self.assertTrue(next(o['data']['required_review'] for o in state['knowledge'] if o['id']==update))
        self.decide(update,'approve',day='2026-07-18')
        self.assertEqual(len(overview(self.db)['completed']),1)
        repeated=self.source(observation(kind='status',update='done',update_target=oid,
            due_text=None,work_state='done',state_quotes=[TEXT.splitlines()[0]]),'2026-07-19')
        self.assertFalse(next(o['data']['required_review'] for o in overview(self.db)['knowledge'] if o['id']==repeated))
    def test_manual_field_guard_allows_equivalent_and_unrelated_evidenced_updates(self):
        oid=self.source(observation())
        self.decide(oid,'set_status',{'status':'waiting'})
        owner_update=self.source(observation(kind='status',update='owner_changed',update_target=oid,
            owner='Kimia',due_text=None),'2026-07-17')
        state=overview(self.db);item=state['waiting'][0]
        self.assertEqual(item['owner'],'Kimia');self.assertEqual(item['status'],'waiting')
        self.assertFalse(next(o['data']['required_review'] for o in state['knowledge'] if o['id']==owner_update))
        progress=self.source(observation(kind='status',update='progress',update_target=oid,
            owner=None,due_text=None,work_state='waiting'),'2026-07-18')
        state=overview(self.db);item=state['waiting'][0]
        self.assertEqual(item['owner'],'Kimia');self.assertEqual(item['status'],'waiting')
        self.assertFalse(next(o['data']['required_review'] for o in state['knowledge'] if o['id']==progress))
        self.assertEqual(self.db.execute("SELECT count(*) FROM work_events WHERE work_id=?",(oid,)).fetchone()[0],3)
    def test_approval_without_patch_does_not_lock_future_fields(self):
        oid=self.source(observation(required_review=True))
        self.decide(oid,'approve')
        update=self.source(observation(kind='status',update='done',update_target=oid,
            due_text=None,work_state='done',state_quotes=[TEXT.splitlines()[0]]),'2026-07-17')
        state=overview(self.db)
        self.assertEqual(state['personal'],[]);self.assertEqual(state['completed'][0]['id'],oid)
        self.assertFalse(next(o['data']['required_review'] for o in state['knowledge'] if o['id']==update))
    def test_reject_update_does_not_cancel_existing_work(self):
        oid=self.source(observation())
        update=self.source(observation(kind='status',update='done',update_target=oid,required_review=True),'2026-07-16')
        self.decide(update,'reject')
        self.assertEqual(len(overview(self.db)['personal']),1)
        repeated=self.source(observation(kind='status',update='done',update_target=oid,
            due_text=None,work_state='done',state_quotes=[TEXT.splitlines()[0]]),'2026-07-17')
        data=next(o['data'] for o in overview(self.db)['knowledge'] if o['id']==repeated)
        self.assertTrue(data['required_review']);self.assertEqual(data['human_conflict_fields'],['status'])
    def test_reject_manually_approved_proposal_removes_work(self):
        oid=self.source(observation(required_review=True))
        self.decide(oid,'approve');self.decide(oid,'reject')
        self.assertEqual(overview(self.db)['personal'],[])
        self.assertEqual(len(overview(self.db)['cancelled']),1)
    def test_correction_and_cancellation_preserve_full_history(self):
        oid=self.source(observation())
        self.decide(oid,'correct',{'title':'Von mir korrigiert','due_date':'2026-08-01'})
        self.decide(oid,'set_status',{'status':'cancelled'})
        state=overview(self.db);item=state['cancelled'][0]
        self.assertEqual(item['title'],'Von mir korrigiert');self.assertEqual(item['due_date'],'2026-08-01')
        self.assertEqual(len(item['history']),3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],1)
    def test_retry_is_idempotent_but_changed_command_rejected(self):
        oid=self.source(observation());identifier=str(uuid4())
        self.decide(oid,'set_status',{'status':'done'},command_id=identifier)
        self.decide(oid,'set_status',{'status':'done'},command_id=identifier)
        self.assertEqual(len(overview(self.db)['human_decisions']),1)
        with self.assertRaises(ValidationError):self.decide(oid,'set_status',{'status':'open'},command_id=identifier)
    def test_unknown_targets_knowledge_promotion_and_evidence_patches_rejected(self):
        oid=self.source(observation(kind='dependency',commitment_strength='not_applicable'))
        with self.assertRaises(ValidationError):self.decide(oid,'approve')
        with self.assertRaises(ValidationError):self.decide('unknown','correct',{'title':'Other'})
        with self.assertRaises(ValidationError):self.decide(oid,'correct',{'quotes':['invented']})
    def test_human_approved_work_is_valid_target_for_future_proposals(self):
        oid=self.source(observation(required_review=True));self.decide(oid,'approve')
        self.source(observation(kind='status',update='done',update_target=oid),'2026-07-17')
        self.assertEqual(len(overview(self.db)['personal']),1)

    def test_partial_knowledge_correction_preserves_original_and_history(self):
        oid=self.source(observation(kind='fact',commitment_strength='not_applicable',required_review=True))
        before=self.db.execute('SELECT data_json FROM observations WHERE id=?',(oid,)).fetchone()[0]
        self.decide(oid,'correct_confirm',{'claim':'Der Export funktioniert; nur Kimia prüft die Rechte.'})
        state=overview(self.db);data=state['knowledge'][0]['data']
        self.assertEqual(data['claim'],'Der Export funktioniert; nur Kimia prüft die Rechte.')
        self.assertEqual(data['title'],json.loads(before)['title'])
        self.assertEqual(data['quotes'],json.loads(before)['quotes'])
        self.assertEqual(data['original_interpretation']['claim'],json.loads(before)['claim'])
        self.assertFalse(data['required_review']);self.assertEqual(state['personal'],[])
        self.assertEqual(self.db.execute('SELECT data_json FROM observations WHERE id=?',(oid,)).fetchone()[0],before)
        self.assertEqual(overview(self.db,'2026-07-15')['knowledge'][0]['data']['claim'],json.loads(before)['claim'])
        self.decide(oid,'correct_confirm',{'title':'Präziser Titel'},day='2026-07-17')
        self.assertEqual(overview(self.db)['knowledge'][0]['data']['claim'],data['claim'])
        self.assertEqual(len(overview(self.db)['knowledge'][0]['data']['correction_history']),2)
        self.assertEqual(overview(self.db)['personal'],[])
        self.assertEqual(overview(self.db)['waiting'],[])
        self.assertNotIn(oid,known_work_ids(self.db))

    def test_correct_confirm_creates_one_task_and_feedback_with_temporal_bounds(self):
        from hybrid_index import documents
        oid=self.source(observation(owner='Speaker 1',required_review=True))
        identifier=str(uuid4());patch={'owner':'Kimia','claim':'Kimia prüft ausschließlich den Export.'}
        self.decide(oid,'correct_confirm',patch,command_id=identifier)
        self.decide(oid,'correct_confirm',patch,command_id=identifier)
        state=overview(self.db);self.assertEqual(len(state['waiting']),1)
        self.assertEqual(state['waiting'][0]['owner'],'Kimia');self.assertIn(oid,known_work_ids(self.db))
        self.assertEqual(len(state['human_decisions']),1)
        prior=documents(self.db,{'meeting_date':'2026-07-16'})
        later=documents(self.db,{'meeting_date':'2026-07-17'})
        self.assertFalse(any(r['kind']=='feedback' for r in prior))
        self.assertTrue(any(r['kind']=='feedback' and 'Kimia' in r['text'] for r in later))
        self.assertTrue(any(r['kind']=='knowledge' and patch['claim'] in r['text'] and r['metadata'].get('human_correction') for r in later))
        self.assertEqual(later,documents(self.db,{'meeting_date':'2026-07-17'}))
        self.source(observation(kind='status',update='done',update_target=oid),'2026-07-18')
        self.assertEqual(overview(self.db)['completed'],[])

    def test_corrected_update_changes_only_requested_task(self):
        oid=self.source(observation())
        update=self.source(observation(kind='status',update='done',update_target=oid,required_review=True),'2026-07-16')
        self.decide(update,'correct_confirm',{'claim':'Nur ein Teil ist fertig, die Aufgabe bleibt offen.','status':'open'},day='2026-07-17')
        item=overview(self.db)['personal'][0]
        self.assertEqual(item['id'],oid);self.assertEqual(item['owner'],'Gleb')
        self.assertEqual(item['status'],'open');self.assertEqual(len(overview(self.db)['completed']),0)
        with self.assertRaises(ValidationError):self.decide(update,'correct_confirm',{'claim':'Erneute Anwendung'},day='2026-07-18')

    def test_rejected_task_proposal_can_be_explicitly_corrected_later(self):
        oid=self.source(observation(owner='Speaker 1',required_review=True))
        self.decide(oid,'reject')
        self.decide(oid,'correct_confirm',{'owner':'Kimia','claim':'Kimia übernimmt nur den Export.'})
        self.assertEqual(overview(self.db)['waiting'][0]['owner'],'Kimia')

    def test_correction_validation_and_rejection_are_separate(self):
        oid=self.source(observation(kind='fact',commitment_strength='not_applicable',required_review=True))
        for patch in ({},{'claim':''},{'claim':'x'*12001},{'owner':'Gleb'},{'status':'open'},{'quotes':['Invented']}):
            with self.assertRaises(ValidationError):self.decide(oid,'correct_confirm',patch)
        self.decide(oid,'reject')
        self.assertNotIn('original_interpretation',overview(self.db)['knowledge'][0]['data'])
        self.decide(oid,'correct_confirm',{'claim':'Jetzt bewusst korrigiert.'})
        self.assertEqual(overview(self.db)['personal'],[])

    def test_rejected_knowledge_is_auditable_but_not_an_active_search_document(self):
        from hybrid_index import documents
        oid=self.source(observation(kind='fact',commitment_strength='not_applicable',owner=None,due_text=None,required_review=True))
        self.decide(oid,'reject')
        projected=overview(self.db)['knowledge'][0]['data']
        self.assertEqual(projected['knowledge_status'],'rejected')
        self.assertEqual([d['action'] for d in projected['human_decision_history']],['reject'])
        rejected=documents(self.db,{'meeting_date':'2026-07-17'})
        self.assertFalse(any(r['kind']=='knowledge' and r['target_id']==oid for r in rejected))
        self.assertTrue(any(r['kind']=='feedback' and r['metadata']['observation_id']==oid for r in rejected))
        self.decide(oid,'correct_confirm',{'claim':'Bewusst korrigierte Fassung.'},day='2026-07-17')
        active=documents(self.db,{'meeting_date':'2026-07-18'})
        self.assertTrue(any(r['kind']=='knowledge' and r['target_id']==oid and 'Bewusst korrigierte Fassung.' in r['text'] for r in active))
        projected=overview(self.db)['knowledge'][0]['data']
        self.assertEqual(projected['knowledge_status'],'active')
        self.assertEqual([d['action'] for d in projected['human_decision_history']],['reject','correct_confirm'])

if __name__=='__main__':unittest.main()
