import copy
import unittest
from uuid import uuid4
from memory import connect, overview, ValidationError
from human_decisions import record
from planner import state, DEFAULT_TEAM
from review_api import review
from test_generation_review import entry, OWNER, TEXT
from generation_review import compile_generation, materialize, expand_generation, verify_generation
from test_memory import observation, proposal
from memory import register, claim, apply


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        self.source = entry(self.db, 'drive:planning')
        self.work = overview(self.db)['personal'][0]

    def tearDown(self):
        self.db.close()

    def save(self, action, target, patch, day='2026-09-07', command_id=None):
        command = dict(action=action, target_id=target, patch=patch, reason='Bewusste Planung', event_date=day)
        cmd = command_id or str(uuid4())
        record(self.db, command_id=cmd, actor_id=OWNER, command=command)
        return {'kind': 'human', 'command_id': cmd, 'actor_id': OWNER, 'payload': command}

    def apply_done(self, target, source, day='2026-09-09'):
        text='Gleb: Der Budgetbericht ist jetzt abgeschlossen.'
        job=register(self.db,source_id=source,event_date=day,title='Follow-up',transcript=text)
        update=observation(matter='Eigene Planung',kind='status',title='Budgetbericht abgeschlossen',
            claim='Der Budgetbericht ist abgeschlossen.',owner=None,due_text=None,update_target=target,update='done',
            work_state='done',quotes=[text],state_quotes=[text],commitment_strength='not_applicable')
        result=apply(self.db,job,claim(self.db,job),proposal(update),model='fixture')[0]
        observation_id=self.db.execute('SELECT id FROM observations WHERE source_version=(SELECT source_version FROM jobs WHERE id=?)',(job,)).fetchone()[0]
        return result,observation_id

    def test_source_planning_preserves_meeting_projection_and_quotes(self):
        before = overview(self.db)
        self.save('plan_task', self.work['id'], {'scheduled_date': '2026-09-09', 'estimate_minutes': 40, 'priority': 'high'})
        self.assertEqual(before, overview(self.db))
        task = review(self.db)['personal'][0]
        self.assertEqual(task['scheduled_date'], '2026-09-09')
        self.assertEqual(task['due_text'], self.work['due_text'])
        self.assertEqual(len(task['planning_history']), 1)
        self.assertNotIn('scheduled_date', review(self.db, '2026-09-06')['personal'][0])

    def test_manual_todo_and_completion_need_no_meeting_or_model(self):
        fresh = connect(':memory:')
        try:
            target = str(uuid4())
            command = dict(action='create_task', target_id=target, reason='Direkt angelegt', event_date='2026-09-07', patch={'title': 'Testbericht', 'owner': 'Kimia Safei', 'due_date': '2026-09-11', 'scheduled_date': '2026-09-09'})
            record(fresh, command_id=str(uuid4()), actor_id=OWNER, command=command)
            self.assertEqual(len(review(fresh)['sources']), 0)
            todo = review(fresh)['waiting'][0]
            self.assertEqual(todo['due_date'], '2026-09-11')
            self.assertEqual(todo['scheduled_date'], '2026-09-09')
            self.assertEqual(todo['origin'], 'manual')
            record(fresh, command_id=str(uuid4()), actor_id=OWNER, command={**command, 'action': 'update_task', 'patch': {'status': 'done'}})
            self.assertEqual(review(fresh)['completed'][0]['status'], 'done')
            self.assertEqual(len(review(fresh)['completed'][0]['planning_history']), 2)
        finally:
            fresh.close()

    def test_unknown_work_unsupported_fields_and_invalid_dates_are_rejected(self):
        for target, patch in [('missing', {'scheduled_date': None}), (self.work['id'], {'due_date': '2026-09-09'}), (self.work['id'], {'scheduled_date': '2026-02-30'}), (self.work['id'], {'estimate_minutes': True}), (self.work['id'], {'estimate_minutes': -1})]:
            with self.assertRaises(ValueError): self.save('plan_task', target, patch)

    def test_repeated_command_is_idempotent_but_changed_content_fails(self):
        cmd = str(uuid4())
        self.save('plan_task', self.work['id'], {'scheduled_date': None}, command_id=cmd)
        self.save('plan_task', self.work['id'], {'scheduled_date': None}, command_id=cmd)
        self.assertEqual(len(state(self.db)['plans'][self.work['id']]['history']), 1)
        with self.assertRaises(ValidationError): self.save('plan_task', self.work['id'], {'scheduled_date': '2026-09-08'}, command_id=cmd)

    def test_former_member_cannot_receive_new_manual_work(self):
        for name in ('Mathias Hummel', 'Hummel, Mathias'):
            with self.assertRaisesRegex(ValidationError, 'inactive'): self.save('create_task', str(uuid4()), {'title': 'Aufgabe', 'owner': name})
        self.assertEqual([m['name'] for m in state(self.db)['team'] if m['active']], ['Jan Gieselberg', 'Giannas, Nikolaos', 'Kimia Safei'])
        self.assertIn('Nikolaos Ginnas', state(self.db)['team'][1]['aliases'])
        self.assertIn('Nikolaus Ginas', state(self.db)['team'][1]['aliases'])

    def test_conflicting_team_aliases_fail_and_team_change_is_historical(self):
        members = copy.deepcopy(DEFAULT_TEAM)
        members[0]['aliases'].append(members[1]['name'])
        with self.assertRaises(ValidationError): self.save('configure_team', 'team', {'members': members})
        members = copy.deepcopy(DEFAULT_TEAM); members[0]['active'] = False
        self.save('configure_team', 'team', {'members': members})
        self.assertFalse(state(self.db)['team'][0]['active'])
        self.assertTrue(state(self.db, '2026-09-06')['team'][0]['active'])

    def test_generation_preserves_manual_planning_and_rejects_silent_changes(self):
        task = str(uuid4())
        human = self.save('create_task', task, {'title': 'Wochenaufgabe', 'owner': 'Komzin, Gleb'})
        base = [self.source, human]
        scratch = connect(':memory:')
        try: changed = entry(scratch, 'drive:planning', TEXT + '\nWeitere Notiz.')
        finally: scratch.close()
        plan = [changed, human]
        result = compile_generation(base, plan, source_reviews={'drive:planning': 'Original ergänzt'}, identity_links=[], reason='Geprüft')
        self.assertTrue(verify_generation(base, result))
        restored, _ = materialize(expand_generation(base, result))
        try: self.assertEqual(state(restored)['tasks'][task]['title'], 'Wochenaufgabe')
        finally: restored.close()
        altered = copy.deepcopy(plan); altered[1]['payload']['patch']['title'] = 'Still ersetzt'
        with self.assertRaisesRegex(ValidationError, 'cannot be rewritten'):
            compile_generation(base, altered, source_reviews={'drive:planning': 'Original ergänzt'}, identity_links=[], reason='Geprüft')

    def test_manual_task_enters_retrieval_matching_and_evidenced_lifecycle_updates(self):
        from hybrid_index import documents
        from reconcile import candidates
        task = str(uuid4())
        self.save('create_task', task, {'title': 'Budgetbericht abschließen', 'owner': 'Komzin, Gleb'}, day='2026-09-08')
        meeting = {'meeting_date': '2026-09-09'}
        self.assertIn(task, {row['target_id'] for row in documents(self.db, meeting) if row['kind']=='work'})
        self.assertIn(task, {row['id'] for row in candidates(self.db, meeting, {'observations':[]})})

        self.apply_done(task,'drive:manual-task-update')
        matches=[item for item in review(self.db)['completed'] if item['id']==task]
        self.assertEqual(len(matches),1);self.assertEqual(matches[0]['origin'],'manual')
        self.assertEqual(matches[0]['title'],'Budgetbericht abschließen')
        self.assertEqual(len(matches[0]['planning_history']),1);self.assertEqual(len(matches[0]['history']),1)

    def test_later_manual_status_correction_blocks_conflicting_source_update(self):
        task = str(uuid4())
        self.save('create_task', task, {'title': 'Budgetbericht abschließen', 'owner': 'Komzin, Gleb'}, day='2026-09-08')
        self.save('update_task', task, {'status': 'waiting'}, day='2026-09-09')
        applied,_=self.apply_done(task,'drive:manual-conflict',day='2026-09-10')
        self.assertTrue(applied['required_review']);self.assertEqual(applied['human_conflict_fields'],['status'])
        matches=[item for item in review(self.db)['waiting_dependencies'] if item['id']==task]
        self.assertEqual(len(matches),1);self.assertEqual(matches[0]['status'],'waiting')

    def test_same_day_source_after_create_wins_but_later_manual_status_wins(self):
        task=str(uuid4())
        self.save('create_task',task,{'title':'Budgetbericht abschließen','owner':'Komzin, Gleb'},day='2026-09-09')
        applied,_=self.apply_done(task,'drive:same-day-source',day='2026-09-09')
        self.assertFalse(applied['required_review'])
        self.assertEqual([item['status'] for item in review(self.db)['completed'] if item['id']==task],['done'])
        self.save('update_task',task,{'status':'waiting'},day='2026-09-09')
        self.assertEqual([item['status'] for item in review(self.db)['waiting_dependencies'] if item['id']==task],['waiting'])

    def test_same_day_manual_status_before_source_requires_review(self):
        task=str(uuid4())
        self.save('create_task',task,{'title':'Budgetbericht abschließen','owner':'Komzin, Gleb'},day='2026-09-09')
        self.save('update_task',task,{'status':'waiting'},day='2026-09-09')
        applied,_=self.apply_done(task,'drive:same-day-conflict',day='2026-09-09')
        self.assertTrue(applied['required_review'])
        self.assertEqual([item['status'] for item in review(self.db)['waiting_dependencies'] if item['id']==task],['waiting'])

    def test_approval_after_manual_conflict_supersedes_old_planning_status(self):
        task=str(uuid4())
        self.save('create_task',task,{'title':'Budgetbericht abschließen','owner':'Komzin, Gleb'},day='2026-09-09')
        self.save('update_task',task,{'status':'waiting'},day='2026-09-09')
        first,observation_id=self.apply_done(task,'drive:approval-needed',day='2026-09-09')
        self.assertTrue(first['required_review'])
        record(self.db,command_id=str(uuid4()),actor_id=OWNER,command={
            'action':'approve','target_id':observation_id,'reason':'Abschluss im Original geprüft',
            'patch':{},'event_date':'2026-09-09'})
        self.assertEqual([item['status'] for item in review(self.db)['completed'] if item['id']==task],['done'])
        repeated,_=self.apply_done(task,'drive:approved-repeat',day='2026-09-09')
        self.assertFalse(repeated['required_review'])
