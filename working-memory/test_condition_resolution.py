import json, unittest
from uuid import uuid4
from memory import connect,register,claim,apply,overview,ValidationError
from human_decisions import record
import reconcile
from test_memory import observation,proposal

ORIGINAL='Gleb: Sobald die Freigabe und die Kurse vorliegen, sende ich morgen den Bericht.'
UPDATE='Gleb: Die Freigabe und die Kurse sind jetzt beide da. Den Bericht muss ich noch senden.'
CONDITION='Sobald die Freigabe und die Kurse vorliegen'
ACTOR='00000000-0000-4000-8000-000000000001'

class ConditionResolutionTests(unittest.TestCase):
 def setUp(self):
  self.db=connect(':memory:')
  self.wid=self.source(observation(work_state='waiting',condition_text=CONDITION,quotes=[ORIGINAL]),ORIGINAL,'2026-07-15')
 def tearDown(self):self.db.close()
 def source(self,o,text,day):
  job=register(self.db,source_id='synthetic:'+str(uuid4()),event_date=day,title='Synthetic condition',transcript=text)
  apply(self.db,job,claim(self.db,job),proposal(o),model='fixture')
  return self.db.execute('select id from observations where job_id=?',(job,)).fetchone()[0]
 def update(self,**patch):
  return observation(kind='status',owner=None,due_text=None,update_target=self.wid,update='condition_met',
   commitment_strength='not_applicable',condition_text=None,work_state='open',quotes=[UPDATE],state_quotes=[UPDATE],**patch) if not patch else {**self.update(),**patch}
 def decide(self,target,action,patch,day):
  record(self.db,command_id=str(uuid4()),actor_id=ACTOR,command={'target_id':target,'action':action,'patch':patch,'reason':'Synthetic explicit decision','event_date':day})
 def test_all_conditions_met_releases_work_preserving_owner_due_and_original(self):
  original=self.db.execute('select data_json from observations where id=?',(self.wid,)).fetchone()[0]
  self.source(self.update(),UPDATE,'2026-07-16')
  state=overview(self.db);self.assertFalse(state['completed']);self.assertFalse(state['waiting_dependencies'])
  item=state['personal'][0]
  self.assertEqual(item['owner'],'Gleb');self.assertEqual(item['due_text'],'morgen');self.assertEqual(item['due_reference_date'],'2026-07-15')
  self.assertIsNone(item['condition_text']);self.assertEqual(item['history'][-1]['resolved_condition_text'],CONDITION)
  self.assertEqual(self.db.execute('select data_json from observations where id=?',(self.wid,)).fetchone()[0],original)
  self.assertEqual(len(overview(self.db,'2026-07-15')['waiting_dependencies']),1)
 def test_progress_and_ambiguous_resolution_keep_condition(self):
  self.source(self.update(update='progress',work_state='waiting',state_quotes=[]),UPDATE,'2026-07-16')
  self.source(self.update(required_review=True,action_uncertainty='Es ist nur eine von zwei Freigaben klar'),UPDATE,'2026-07-17')
  item=overview(self.db)['waiting_dependencies'][0];self.assertEqual(item['condition_text'],CONDITION)
  self.assertEqual(len(item['history']),2)
 def test_missing_confirmation_wrong_state_or_new_condition_reject_atomically(self):
  for patch in ({'state_quotes':[]},{'state_quotes':['invented']},{'work_state':'waiting'},{'condition_text':'Freigabe'},{'update_target':None}):
   with self.subTest(patch=patch),self.assertRaises(ValidationError):self.source(self.update(**patch),UPDATE,'2026-07-16')
   self.assertEqual(self.db.execute('select count(*) from observations').fetchone()[0],1)
 def test_done_work_cannot_reopen_from_condition_resolution(self):
  self.source(self.update(update='done',work_state='done'),UPDATE,'2026-07-16')
  with self.assertRaises(ValidationError):self.source(self.update(),UPDATE,'2026-07-17')
  self.assertEqual(len(overview(self.db)['completed']),1)
 def test_no_recorded_condition_cannot_be_cleared_twice(self):
  self.source(self.update(),UPDATE,'2026-07-16')
  with self.assertRaises(ValidationError):self.source(self.update(),UPDATE,'2026-07-17')
  self.assertEqual(len(overview(self.db)['personal']),1)
 def test_title_correction_does_not_block_evidenced_condition_resolution(self):
  self.decide(self.wid,'correct',{'title':'Mein geprüfter Bericht'},'2026-07-16')
  oid=self.source(self.update(),UPDATE,'2026-07-17')
  item=overview(self.db)['personal'][0]
  self.assertEqual(item['title'],'Mein geprüfter Bericht');self.assertIsNone(item['condition_text'])
  self.assertFalse(next(o['data']['required_review'] for o in overview(self.db)['knowledge'] if o['id']==oid))
  self.assertEqual(len(overview(self.db)['human_decisions']),1)
 def test_lifecycle_uses_explicit_condition_resolution_not_completion(self):
  item=overview(self.db)['waiting_dependencies'][0]
  result=dict(work_id=self.wid,action='condition_met',title='Voraussetzungen da',claim=UPDATE,reason='Beide ausdrücklich bestätigt',evidence_ids=['U0001'],owner=None,due_text=None)
  rows=reconcile.observations([item],[result],{'U0001':{'text':UPDATE}})
  self.assertEqual(rows[0]['work_state'],'open');self.assertEqual(rows[0]['state_quotes'],[UPDATE])
  self.source(rows[0],UPDATE,'2026-07-16');self.assertFalse(overview(self.db)['completed'])
  with self.assertRaises(ValidationError):reconcile.observations([{**item,'condition_text':None}],[result],{'U0001':{'text':UPDATE}})
 def test_multiple_condition_fragments_each_need_verbatim_original_evidence(self):
  from memory import validate
  text='Gleb: Ich sende nach Freigabe.\nGleb: Und sobald die Kurse da sind.'
  o=observation(due_text=None,condition_text='nach Freigabe\nsobald die Kurse da sind',work_state='waiting',quotes=text.splitlines())
  self.assertEqual(validate(proposal(o),text,set())[0]['condition_text'],o['condition_text'])
  with self.assertRaises(ValidationError):validate(proposal({**o,'condition_text':'nach Freigabe\nnach unterschriebenem Vertrag'}),text,set())

if __name__=='__main__':unittest.main()
