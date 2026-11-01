from copy import deepcopy
import tempfile,unittest
from unittest.mock import patch
from generation_review import expand_generation,materialize
from journal_service import JournalService
from journal_store import RevisionConflict
from memory import ValidationError,overview
from source_edit import inspect,stage,FIELDS
from test_job_recovery import RecoveryStore,OWNER

REVIEW='77777777-7777-4777-8777-777777777777'
class EditStore(RecoveryStore):
 def __init__(self):super().__init__();self.staged=None;self.generation=None
 def call(self,op,**v):
  if op=='generation_review':return deepcopy(self.generation)
  if op=='generation_stage':self.staged=deepcopy(v);return {'review_id':v['review_id'],'state':'pending'}
  return super().call(op,**v)

class SourceEditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=EditStore();self.service=JournalService(self.store,self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def observation(self):
  return dict(matter='Bericht',matter_id=None,kind='fact',title='Zwei Filialen',claim='Der Bericht enthält zwei Filialen.',owner=None,
   commitment_strength='not_applicable',due_text=None,update_target=None,update='none',uncertainty=None,required_review=False,
   action_uncertainty=None,condition_text=None,work_state='not_applicable',evidence_ids=['U0001'],state_evidence_ids=[])
 def request(self):
  return dict(job_id=self.store.job['id'],review_id=REVIEW,expected_revision=0,expected_updated_at=self.store.job['updated_at'],
   reason='Den Berichtsumfang am Original geprüft',observations=[self.observation()],identity_links=[],topic_links=[])
 def test_manual_edit_stages_only_and_never_calls_model(self):
  self.store.job['reason']='validation_failed'
  with patch('processor.anthropic') as api:
   result=stage(self.service,OWNER,self.request());api.assert_not_called()
  self.assertEqual(result['state'],'pending');self.assertEqual(self.store.revision,0);self.assertFalse(self.store.applied)
  payload=self.store.staged['payload'];db,_=materialize(expand_generation([],payload))
  try:self.assertEqual(len(overview(db)['knowledge']),1);self.assertFalse(overview(db)['personal'])
  finally:db.close()
  self.assertEqual(payload['new_sources'][0]['transcript'],self.store.document['body'])
 def test_only_owner_can_inspect_or_stage(self):
  for who in ({'role':'service'},dict(OWNER,id='other')):
   with self.assertRaises(PermissionError):inspect(self.service,who,self.store.job['id'])
   with self.assertRaises(PermissionError):stage(self.service,who,self.request())
  self.assertIsNone(self.store.staged)
 def test_no_saved_result_still_exposes_exact_original_for_manual_review(self):
  self.store.calls=[{'received':False}]
  result=inspect(self.service,OWNER,self.store.job['id'])
  self.assertTrue(result['can_edit']);self.assertTrue(result['unknown_provider_outcome'])
  self.assertEqual(result['document']['units']['U0001'],self.store.document['body']);self.assertEqual(result['observations'],[])
 def test_incomplete_saved_result_prefills_without_null_controls_or_invented_evidence(self):
  self.store.job['prepared_payload']={'proposal':{'observations':[{'kind':'fact','title':'Altvorschlag','quotes':['not in this original']} ]}}
  row=inspect(self.service,OWNER,self.store.job['id'])['observations'][0]
  self.assertEqual(row['claim'],'');self.assertEqual(row['work_state'],'not_applicable');self.assertFalse(row['required_review'])
  self.assertEqual(row['evidence_ids'],[])
 def test_stale_job_and_revision_block_staging(self):
  request=self.request();self.store.job['updated_at']='2026-09-08T00:00:00Z'
  with self.assertRaises(RevisionConflict):stage(self.service,OWNER,request)
  request=self.request();self.store.revision=1
  with self.assertRaises(RevisionConflict):stage(self.service,OWNER,request)
  self.assertIsNone(self.store.staged)
 def test_running_or_finished_job_is_not_editable(self):
  for state in ('running','prepared','applied','queued','archived'):
   self.store.job.update(state=state,lease_until='2099-01-01T00:00:00Z')
   self.assertFalse(inspect(self.service,OWNER,self.store.job['id'])['can_edit'])
   with self.assertRaises(RevisionConflict):stage(self.service,OWNER,self.request())
 def test_invented_quote_or_unselected_task_cannot_enter_review(self):
  request=self.request();request['observations'][0]['evidence_ids']=['U9000']
  with self.assertRaises(ValidationError):stage(self.service,OWNER,request)
  request=self.request();request['observations'][0]['update']='done'
  with self.assertRaises(ValidationError):stage(self.service,OWNER,request)
  request=self.request();request['observations'][0]['due_text']='morgen'
  with self.assertRaises(ValidationError):stage(self.service,OWNER,request)
  self.assertIsNone(self.store.staged)
 def test_completed_promise_needs_state_evidence(self):
  request=self.request();request['observations'][0].update(kind='commitment',owner='Alice',commitment_strength='explicit',work_state='done')
  with self.assertRaises(ValidationError):stage(self.service,OWNER,request)
  request['observations'][0]['state_evidence_ids']=['U0001']
  stage(self.service,OWNER,request)
  self.assertIsNotNone(self.store.staged)
 def test_lost_stage_ack_uses_same_original_revision_and_payload(self):
  request=self.request();stage(self.service,OWNER,request);first=deepcopy(self.store.staged)
  self.store.generation={'space_id':self.store.space_id,'expected_revision':0,'payload':first['payload']}
  self.store.revision=1;self.store.job.update(state='applied',updated_at='2026-09-08T00:00:00Z')
  stage(self.service,OWNER,request)
  self.assertEqual(self.store.staged,first)
 def test_observation_cannot_smuggle_normalized_gate_or_source_fields(self):
  request=self.request();request['observations'][0]['creates_work']=True
  with self.assertRaises(ValidationError):stage(self.service,OWNER,request)
  self.assertIsNone(self.store.staged)
 def test_replacement_preserves_personal_decision_only_with_explicit_mapping(self):
  from memory import connect
  from test_generation_review import entry
  db=connect(':memory:');old=entry(db,'synthetic:future');wid=overview(db)['personal'][0]['id'];db.close()
  human={'kind':'human','command_id':'33333333-3333-4333-8333-333333333333','actor_id':OWNER['id'],
   'payload':{'action':'reject','target_id':wid,'reason':'Das war keine eigene Zusage','patch':{},'event_date':'2026-09-07'}}
  self.store.revision=2;self.store.entries=lambda **kw:[old,human][:kw.get('through',2)]
  inspected=inspect(self.service,OWNER,self.store.job['id'])
  self.assertEqual(len(inspected['previous_topics']),1)
  old_topic=inspected['previous_topics'][0]['id']
  self.assertEqual(inspected['previous_observations'][0]['matter_id'],old_topic)
  request=self.request();request['expected_revision']=2
  with self.assertRaises(ValidationError):stage(self.service,OWNER,request)
  self.assertIsNone(self.store.staged)
  request['identity_links']=[{'old_id':wid,'new_index':0,'reason':'Dieselbe fachlich korrigierte Aussage, persönliche Ablehnung bleibt erhalten'}]
  request['topic_links']=[{'old_id':old_topic,'new_index':0,'reason':'Das ursprüngliche Thema bleibt trotz korrigierter Aussage dasselbe'}]
  stage(self.service,OWNER,request)
  # The real gateway stores JSONB, so object order is not retained. A source
  # replacement must still reopen as the exact same reviewed generation.
  import json
  from generation_review import logical_entries,verify_generation
  roundtrip=json.loads(json.dumps(self.store.staged['payload'],sort_keys=True))
  self.assertTrue(verify_generation(logical_entries([old,human]),roundtrip))
  plan=expand_generation([old,human],self.store.staged['payload'])
  self.assertEqual(plan[1]['payload']['reason'],human['payload']['reason']);self.assertEqual(plan[1]['actor_id'],OWNER['id'])
  self.assertEqual(plan[1]['command_id'],human['command_id']);self.assertEqual(plan[1]['payload']['action'],'reject')
  rebuilt,_=materialize(plan)
  try:self.assertFalse(overview(rebuilt)['personal']);self.assertEqual(rebuilt.execute('select count(*) from human_decisions').fetchone()[0],1)
  finally:rebuilt.close()

if __name__=='__main__':unittest.main()
