import copy,unittest,tempfile
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch
from memory import connect,fingerprint,overview,ValidationError
from journal_projection import prepare_source,apply_saved,digest
from generation_review import compile_generation,verify_generation,materialize,logical_entries,expand_generation
from test_memory import TEXT,proposal,observation
OWNER='00000000-0000-4000-8000-000000000001'
CMD='20000000-0000-4000-8000-000000000001'

def source(key,body=TEXT,day='2026-07-15'):
 h=fingerprint(body)
 return dict(id=fingerprint(key+':'+h),source_id=key,content_hash=h,transcript=body,title=key,event_date=day,observed_at='2026-09-06T00:00:00Z')
def entry(db,key,body=TEXT,day='2026-07-15',obs=None):
 s=source(key,body,day);p=prepare_source(db,s,proposal(obs or observation()),pipeline='manual-v1',model='codex_direct_review',provenance={'review':'fixture'})
 apply_saved(db,s,p);return {'kind':'source','source':s,'payload':p}

class GenerationTests(unittest.TestCase):
 def setUp(self):
  self.db=connect(':memory:');self.first=entry(self.db,'drive:first');self.wid=overview(self.db)['personal'][0]['id']
  self.human={'kind':'human','command_id':CMD,'actor_id':OWNER,'payload':{'action':'correct','target_id':self.wid,'reason':'Persönlicher Titel und Termin','patch':{'title':'Mein eigener Titel','due_date':'2026-10-01'},'event_date':'2026-09-06'}}
  self.base=[self.first,self.human]
 def tearDown(self):self.db.close()
 def changed(self):
  db=connect(':memory:')
  try:
   e=entry(db,'drive:first',TEXT+'\nZusätzlicher belegter Kontext.');new_id=overview(db)['personal'][0]['id']
   h=copy.deepcopy(self.human);h['payload']['target_id']=new_id
   return [e,h],[{'old_id':self.wid,'new_id':new_id,'reason':'Dieselbe Zusage aus der korrigierten Originalfassung'}]
  finally:db.close()
 def compile(self,plan,links=None,reviews=None):
  return compile_generation(self.base,plan,source_reviews=reviews or {'drive:first':'Korrigiertes Original vollständig geprüft'},identity_links=links or [],reason='Geändertes Original kontrolliert übernehmen')
 def test_changed_source_preserves_personal_title_date_and_uuid_without_model_calls(self):
  plan,links=self.changed()
  with patch('processor.anthropic') as api:
   result=self.compile(plan,links);self.assertTrue(verify_generation(self.base,result));api.assert_not_called()
  restored,_=materialize(expand_generation(self.base,result))
  try:
   item=overview(restored)['personal'][0];self.assertEqual(item['title'],'Mein eigener Titel');self.assertEqual(item['due_date'],'2026-10-01')
   self.assertEqual(overview(restored)['human_decisions'][0]['command_id'],CMD)
  finally:restored.close()
  self.assertEqual(result['personal_decisions_preserved'],1)
  self.assertEqual(self.first['source']['transcript'],TEXT)
 def test_omitted_changed_same_id_personal_identity_is_blocked(self):
  plan=copy.deepcopy(self.base);plan[0]['payload']['proposal']['observations'][0]['title']='Different task at same index'
  with self.assertRaisesRegex(ValidationError,'explicit identity link'):self.compile(plan)
 def test_dropped_or_rewritten_personal_decision_is_blocked(self):
  plan,links=self.changed()
  with self.assertRaisesRegex(ValidationError,'preserve every'):self.compile(plan[:1],links)
  plan[-1]['payload']['patch']['title']='Silently overwritten'
  with self.assertRaisesRegex(ValidationError,'cannot be rewritten'):self.compile(plan,links)
 def test_late_source_can_be_inserted_before_existing_history_without_reimport(self):
  db=connect(':memory:')
  try:late=entry(db,'drive:late',day='2026-07-14')
  finally:db.close()
  result=self.compile([late,*self.base],reviews={'drive:late':'Verspätetes Original und vorhandener Kontext manuell geprüft'})
  self.assertEqual(result['observation_counts'],{'before':1,'after':2})
  self.assertTrue(verify_generation(self.base,result))
  with self.assertRaisesRegex(ValidationError,'chronological'):self.compile([*self.base,late],reviews={'drive:late':'Geprüft'})
 def test_tampered_review_or_stale_base_cannot_replay(self):
  plan,links=self.changed();result=self.compile(plan,links)
  changed=copy.deepcopy(result);changed['after_counts']['personal']=100
  with self.assertRaisesRegex(ValidationError,'checksum'):verify_generation(self.base,changed)
  with self.assertRaisesRegex(ValidationError,'base'):verify_generation(self.base[:1],result)
 def test_json_object_reordering_preserves_review_but_content_changes_do_not(self):
  import json
  plan,links=self.changed();result=self.compile(plan,links)
  self.assertEqual(result['state_hash_format'],'canonical-knowledge-v1')
  reordered=json.loads(json.dumps(result,sort_keys=True))
  self.assertTrue(verify_generation(json.loads(json.dumps(self.base,sort_keys=True)),reordered))
  reordered['after_counts']['personal']+=1
  with self.assertRaisesRegex(ValidationError,'checksum'):verify_generation(self.base,reordered)
 def test_topic_assignment_is_retained_validated_and_signed_without_followup_references(self):
  plan,links=self.changed()
  db,_=materialize(plan)
  try:topic=db.execute('select id from matters').fetchone()[0]
  finally:db.close()
  old_topic=self.db.execute('select id from matters').fetchone()[0]
  topics=[{'old_id':old_topic,'new_id':topic,'reason':'Dasselbe geprüfte Thema trotz korrigierter Quelle'}]
  result=compile_generation(self.base,plan,source_reviews={'drive:first':'Korrigiert'},identity_links=links,reason='Geprüft',topic_identity_links=topics)
  self.assertEqual(result['topic_identity_links'],topics);self.assertTrue(verify_generation(self.base,result))
  invalid=copy.deepcopy(topics);invalid[0]['new_id']='unknown'
  with self.assertRaisesRegex(ValidationError,'endpoint'):
   compile_generation(self.base,plan,source_reviews={'drive:first':'Korrigiert'},identity_links=links,reason='Geprüft',topic_identity_links=invalid)
  result['topic_identity_links'][0]['reason']='Ungeprüfte Änderung'
  with self.assertRaisesRegex(ValidationError,'checksum'):verify_generation(self.base,result)
 def test_legacy_state_hash_remains_explicitly_supported(self):
  plan,links=self.changed()
  result=compile_generation(self.base,plan,source_reviews={'drive:first':'Original geprüft'},identity_links=links,reason='Legacy fixture',state_hash_format=None)
  self.assertNotIn('state_hash_format',result);self.assertEqual(result['projection_rules'],'field-v1');self.assertTrue(verify_generation(self.base,result))
 def test_legacy_generation_without_projection_rule_reproduces_legacy_source_wire_format(self):
  plan,links=self.changed()
  result=compile_generation(self.base,plan,source_reviews={'drive:first':'Original geprüft'},identity_links=links,
      reason='Legacy accepted fixture',projection_rules='legacy')
  self.assertNotIn('projection_rules',result)
  self.assertTrue(all('human_guard' not in entry['payload'] for entry in expand_generation(self.base,result) if entry['kind']=='source'))
  self.assertTrue(verify_generation(self.base,result))
 def test_new_field_guard_source_does_not_reprepare_retained_legacy_sources(self):
  legacy=copy.deepcopy(self.first);legacy['payload'].pop('human_guard',None)
  db=connect(':memory:')
  try:new=entry(db,'drive:new',body=TEXT+'\nNeue Quelle.',day='2026-07-16')
  finally:db.close()
  result=compile_generation([legacy],[legacy,new],source_reviews={'drive:new':'Neue Quelle vollständig geprüft'},
      identity_links=[],reason='Neue Quelle ergänzen',projection_rules='field-v1')
  expanded=expand_generation([legacy],result)
  self.assertEqual(expanded[0],legacy)
  self.assertEqual(expanded[1]['payload']['human_guard'],'field-v1')
  self.assertTrue(verify_generation([legacy],result))
 def test_unreviewed_source_change_and_identity_collision_fail(self):
  plan,links=self.changed()
  with self.assertRaisesRegex(ValidationError,'Each changed source'):self.compile(plan,links,{'drive:other':'Wrong source'})
  with self.assertRaisesRegex(ValidationError,'one-to-one'):self.compile(plan,links+links)
 def test_nested_generation_flattens_only_after_complete_verification(self):
  plan,links=self.changed();result=self.compile(plan,links)
  self.assertEqual(logical_entries([*self.base,{'kind':'generation','payload':result}]),expand_generation(self.base,result))

 def test_dependent_update_cannot_silently_attach_to_replaced_same_index(self):
  later=entry(self.db,'drive:later',day='2026-07-16',obs=observation(kind='status',update='progress',update_target=self.wid,due_text=None))
  self.base=[self.first,later]
  plan=copy.deepcopy(self.base);plan[0]['payload']['proposal']['observations'][0]['title']='Andere Zusage am selben Index'
  with self.assertRaisesRegex(ValidationError,'dependent updates'):self.compile(plan)
  result=self.compile(plan,[{'old_id':self.wid,'new_id':self.wid,'reason':'Nur Titel korrigiert; inhaltlich dieselbe Zusage und Folgebezug geprüft'}])
  self.assertTrue(verify_generation(self.base,result))
 def test_personal_decision_cannot_move_behind_later_updates(self):
  from human_decisions import record
  record(self.db,command_id=CMD,actor_id=OWNER,command=self.human['payload'])
  later=entry(self.db,'drive:later',day='2026-07-16',obs=observation(kind='status',update='progress',update_target=self.wid,due_text=None))
  self.base=[self.first,self.human,later]
  plan=copy.deepcopy([self.first,later,self.human]);plan[0]['payload']['proposal']['coverage_notes']=['Manuell ergänzt']
  with self.assertRaisesRegex(ValidationError,'anchored'):self.compile(plan)
 def test_journal_rebuild_preserves_old_revision_and_rejects_broken_replacement(self):
  from journal_projection import rebuild
  plan,links=self.changed();result=self.compile(plan,links)
  entries=[{**self.first,'source_version':self.first['source']['id']},self.human,{'kind':'generation','payload':result}]
  store=Mock();store.space.return_value={'id':'fixture-space','revision':3}
  store.entries.side_effect=lambda through:entries[:through]
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'current.sqlite';previous=Path(tmp)/'previous.sqlite'
   rebuild(store,target);rebuild(store,previous,through=2)
   current=connect(target);old=connect(previous)
   try:
    self.assertEqual(overview(current)['personal'][0]['title'],'Mein eigener Titel')
    self.assertNotEqual(overview(current)['personal'][0]['id'],overview(old)['personal'][0]['id'])
    self.assertEqual(overview(old)['personal'][0]['id'],self.wid)
   finally:current.close();old.close()
   old_bytes=target.read_bytes();entries[-1]['payload']['state_sha256']='0'*64
   with self.assertRaises(ValidationError):rebuild(store,target)
   self.assertEqual(target.read_bytes(),old_bytes)

 def test_explicit_same_day_reorder_replays_and_keeps_personal_decision(self):
  second=entry(self.db,'drive:second')
  base=[self.first,second,self.human];plan=[second,self.first,self.human]
  audit={'before':['drive:first','drive:second'],'after':['drive:second','drive:first'],'reason':'Original says second meeting preceded first on the same day'}
  with patch('processor.anthropic') as api:
   result=compile_generation(base,plan,source_reviews={},identity_links=[],reason='Chronology audit',source_order_review=audit)
   self.assertTrue(verify_generation(base,result));api.assert_not_called()
  db,_=materialize(expand_generation(base,result))
  try:
   decision=overview(db)['human_decisions'][0]
   self.assertEqual(decision['command_id'],CMD)
   self.assertTrue(any(w['id']==self.wid and w['title']=='Mein eigener Titel' for w in overview(db)['personal']))
  finally:db.close()
  result['source_order_review']['reason']='Tampered'
  with self.assertRaisesRegex(ValidationError,'checksum'):verify_generation(base,result)

 def test_order_correction_requires_exact_review_and_cannot_cross_owner_decision(self):
  second=entry(self.db,'drive:second')
  base=[self.first,second];plan=[second,self.first]
  audit={'before':['drive:first','drive:second'],'after':['drive:second','drive:first'],'reason':'Same-day chronology'}
  with self.assertRaisesRegex(ValidationError,'no reviewed source change'):
   compile_generation(base,plan,source_reviews={},identity_links=[],reason='No audit')
  for bad in ({**audit,'before':[]},{**audit,'after':['drive:first','drive:second']},{**audit,'reason':''}):
   with self.assertRaises(ValidationError):compile_generation(base,plan,source_reviews={},identity_links=[],reason='Bad audit',source_order_review=bad)
  with self.assertRaisesRegex(ValidationError,'anchored'):
   compile_generation([self.first,self.human,second],[second,self.human,self.first],source_reviews={},identity_links=[],reason='Crossed decision',source_order_review=audit)

 def test_reorder_cannot_cross_dates_even_with_a_corresponding_date_change(self):
  second=entry(self.db,'drive:second',day='2026-07-16')
  plan=copy.deepcopy([second,self.first]);plan[0]['source']['event_date']='2026-07-14'
  audit={'before':['drive:first','drive:second'],'after':['drive:second','drive:first'],'reason':'Attempt across dates'}
  with self.assertRaisesRegex(ValidationError,'same-day'):
   compile_generation([self.first,second],plan,source_reviews={'drive:second':'Date changed'},identity_links=[],reason='Invalid chronology correction',source_order_review=audit)

if __name__=='__main__':unittest.main()
