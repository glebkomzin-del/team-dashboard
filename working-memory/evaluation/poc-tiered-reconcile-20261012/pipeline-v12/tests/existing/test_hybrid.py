import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_memory import observation,proposal,TEXT
from memory import validate,ValidationError,connect,register,claim,apply,overview
from hybrid_pipeline import confidence,resolve_v10,lifecycle_results
from hybrid_index import documents,SearchIndex,parts,encode,digest,MODEL,DIMENSIONS
from processor import units
from durable_calls import DurableCalls
from hybrid_schema import extraction_schema
from test_durable_calls import Store

class HybridTests(unittest.TestCase):
 def test_evidence_catalog_uses_one_shared_enum_definition(self):
  ids=[f'U{i:04d}' for i in range(1,381)];schema=extraction_schema(ids);ref={'$ref':'#/$defs/evidence_id'}
  self.assertEqual(schema['$defs']['evidence_id'],{'type':'string','enum':ids})
  self.assertEqual([
   schema['properties']['observations']['items']['properties']['evidence_ids']['items'],
   schema['properties']['observations']['items']['properties']['state_evidence_ids']['items'],
   schema['properties']['meeting_summary']['items']['properties']['evidence_ids']['items'],
   schema['properties']['meeting_display_title']['anyOf'][1]['properties']['evidence_ids']['items'],
   schema['properties']['search_queries']['items']['properties']['evidence_ids']['items'],
  ],[ref]*5)
  def enum_count(value):
   if isinstance(value,dict):return len(value.get('enum',[]))+sum(enum_count(v) for k,v in value.items() if k!='enum')
   if isinstance(value,list):return sum(map(enum_count,value))
   return 0
  self.assertLessEqual(enum_count(schema),1000)
 def test_archive_keeps_existing_chunk_identities_when_semantic_chunking_changes(self):
  from test_canonical_archive import fixture
  from canonical_archive import rebuild_archive
  from archive_index import connect as archive_connect
  from hybrid_index import archive_parts
  text='Gleb: '+('Ein bestehender Absatz. '*80)+'\nKimia: Zweiter Absatz.'
  self.assertEqual(list(archive_parts(text)),[(i,text[i:i+1400]) for i in range(0,len(text),1400)])
  store,doc,note=fixture()
  with tempfile.TemporaryDirectory() as tmp:
   archive=Path(tmp)/'archive.sqlite';rebuild_archive(store,archive);db=connect(Path(tmp)/'memory.sqlite')
   a=archive_connect(archive);a.execute('update passages set text=?,end=start+?',(text,len(text)));a.commit();a.close()
   with patch('hybrid_index.parts',side_effect=AssertionError('Archive must not be rechunked')):
    rows=documents(db,{'meeting_date':'2026-09-08','observed_at':'2026-09-08T12:00:00Z'},str(archive))
   self.assertEqual([r['text'] for r in sorted((r for r in rows if r['kind']=='passage'),key=lambda r:r['metadata']['part_start'])],[text[i:i+1400] for i in range(0,len(text),1400)])
   db.close()
 def test_gate_doubt_cannot_display_high_confidence(self):
  for verdict,score in [('ambiguous',1),('unsupported',0)]:
   value=confidence(proposal(observation(assignment_score=2,change_score=2,confidence_reason='Vorprüfung',work_gate={'verdict':verdict,'reason':'Am Original nicht bestätigt'})))['observations'][0]
   self.assertEqual(value['change_score'],score);self.assertTrue(value['required_review']);self.assertEqual(value['confidence_reason'],'Am Original nicht bestätigt')
 def test_luna_long_context_budget_uses_decimal_arithmetic(self):
  from call_budget import reserve_micro_usd
  cheap=reserve_micro_usd('x'*280000,'gpt-5.6-luna',12000,{})
  reference=reserve_micro_usd('x'*280000,'gpt-5.6-terra',12000,{})
  self.assertIsInstance(cheap,int);self.assertGreater(cheap,0);self.assertLess(cheap,reference)
 def test_gate_cannot_close_parent_task_when_only_prerequisite_is_finished(self):
  from hybrid_pipeline import guard_gate_escalation
  before=proposal(observation(update_target='parent',update='progress',work_state='waiting'))
  after=copy.deepcopy(before);after['observations'][0].update(update='done',work_state='done')
  checked=guard_gate_escalation(before,after)['observations'][0]
  self.assertEqual(checked['update'],'progress');self.assertTrue(checked['required_review']);self.assertTrue(checked['action_uncertainty'])
 def test_catalog_retains_all_candidate_texts_and_identity_without_transport_metadata(self):
  from hybrid_pipeline import candidate_catalog
  hit={'id':'h','kind':'knowledge','target_id':'target','text':'Vollständiger Text',
       'metadata':{'matter_id':'m','quotes':['Alter Beleg']},'content_hash':'sha','embedding_model':'model'}
  value=candidate_catalog([{'id':'task','claim':'Vollständige Zusage','original_commitment_evidence':['Original']}],[hit])
  self.assertEqual(value['search_hits'][0],{'id':'h','kind':'knowledge','target_id':'target','matter_id':'m','text':'Vollständiger Text'})
  self.assertEqual(value['work'][0],{'id':'task','claim':'Vollständige Zusage'})
 def test_candidate_compaction_is_lossless_and_reuses_repeated_originals(self):
  from hybrid_pipeline import compact_candidates
  text='Originaler Wortlaut. '*200
  value=compact_candidates({'work':[{'original_commitment_evidence':[text]}],'hits':[{'text':text,'metadata':{'quotes':[text]}}]})
  self.assertEqual(list(value['historical_texts'].values()),[text])
  self.assertEqual(value['candidates']['work'][0]['original_commitment_evidence_refs'],['B0001'])
  self.assertEqual(value['candidates']['hits'][0]['text_ref'],'B0001')
 def test_nested_legacy_summaries_are_indexed_with_original_provenance(self):
  from test_canonical_archive import fixture
  from canonical_archive import rebuild_archive
  for wrap in (lambda x:x,lambda x:{'legacy_record':x},lambda x:{'legacy_record':{'payload':x}}):
   store,doc,note=fixture()
   note['note_json']=encode(wrap({'ai_summary':'Bestehende Übersicht','topics':[{'summary':'Bestehendes Thema'}]}))
   note['note_hash']=digest(note['note_json']);note['id']=digest(':'.join([note['document_id'],note['origin'],note['origin_id'],note['note_hash']]))
   with tempfile.TemporaryDirectory() as tmp:
    archive=Path(tmp)/'archive.sqlite';rebuild_archive(store,archive);db=connect(Path(tmp)/'memory.sqlite')
    rows=documents(db,{'meeting_date':'2026-09-08','observed_at':'2026-09-08T12:00:00Z'},str(archive));db.close()
    summaries=[r for r in rows if r['kind']=='summary']
    self.assertEqual({r['text'] for r in summaries},{'Bestehende Übersicht','Bestehendes Thema'})
    self.assertTrue(all(r['source_id']==doc['source_id'] and r['metadata']['document_id']==doc['id'] for r in summaries))
 def test_scores_cannot_override_source_guard(self):
  for score in (0,1):
   p=confidence(proposal(observation(assignment_score=score,change_score=2,confidence_reason='Unklarer Bezug')))
   self.assertFalse(validate(p,TEXT,set())[0]['creates_work'])
  p=confidence(proposal(observation(assignment_score=2,change_score=2,confidence_reason='Explizit',required_review=True)))
  self.assertFalse(validate(p,TEXT,set())[0]['creates_work'])
 def test_repeated_quote_keeps_selected_position(self):
  text='Gleb: Ich sende den Bericht.\nGleb: Ich sende den Bericht.';u=units(text)
  o=observation(due_text=None,evidence_ids=['U0002'],state_evidence_ids=[],assignment_score=2,change_score=2,confidence_reason='Explizit')
  p=resolve_v10(proposal(o),u)
  self.assertEqual(validate(p,text,set())[0]['spans'][0]['start'],29)
  p['observations'][0]['source_spans'][0]['start']=0
  with self.assertRaises(ValidationError):validate(p,text,set())
 def test_compact_unchanged_requires_complete_unique_coverage(self):
  w=[{'id':'a'},{'id':'b'}]
  self.assertEqual(len(lifecycle_results({'unchanged':['a','b'],'changes':[]},w)),2)
  for ids in (['a'],['a','a','b'],['a','foreign']):
   with self.assertRaises(ValidationError):lifecycle_results({'unchanged':ids,'changes':[]},w)
  self.assertEqual([r['work_id'] for r in lifecycle_results({'results':{'0':'unchanged','1':'unchanged'}},w)],['a','b'])
  with self.assertRaises(ValidationError):lifecycle_results({'results':{'0':'unchanged'}},w)
 def test_blank_chunks_are_not_paid_embedding_inputs(self):
  self.assertEqual(list(parts(' '*1600)),[])
  from call_budget import reserve_micro_usd
  with self.assertRaises(ValueError):reserve_micro_usd('[" "]','text-embedding-3-small',1,{})
 def test_embedding_model_change_fails_closed_before_body_cache_lookup(self):
  with patch('hybrid_index.MODEL','future-embedding-model'):
   with self.assertRaisesRegex(ValidationError,'cache migration'):SearchIndex(object(),object())
 def test_cold_index_uses_bounded_multi_document_writes(self):
  class SearchStore:
   def __init__(self):self.writes=[]
   def call(self,op,**values):
    if op=='search_missing':return values['document_ids']
    if op=='search_cached':return {}
    if op=='search_put':self.writes.append(values['documents']);return {'saved':len(values['documents'])}
    raise AssertionError(op)
  store=SearchStore()
  def api(prompt,model,**kwargs):
   return {'stop_reason':'end_turn','embeddings':[[1.0]+[0.0]*(DIMENSIONS-1) for _ in json.loads(prompt)]}
  rows=[{'id':str(i),'kind':'passage','target_id':str(i),'source_id':'source','source_version':'version',
         'event_date':'2026-09-19','observed_at':None,'text':f'text {i}','metadata':{},
         'content_hash':digest(f'text {i}'),'embedding_model':MODEL} for i in range(17)]
  SearchIndex(store,api).persist(rows)
  self.assertEqual([len(batch) for batch in store.writes],[8,8,1])
  self.assertTrue(all(len(encode(batch).encode())<750000 for batch in store.writes))
 def test_knowledge_confirmation_does_not_create_work(self):
  from human_decisions import record
  from uuid import uuid4
  with tempfile.TemporaryDirectory() as tmp:
   db=connect(Path(tmp)/'db');job=register(db,source_id='synthetic:fact',event_date='2026-09-01',title='Fact',transcript=TEXT)
   apply(db,job,claim(db,job),proposal(observation(kind='fact',commitment_strength='not_applicable',required_review=True)),model='fixture')
   oid=db.execute('select id from observations').fetchone()[0]
   record(db,command_id=str(uuid4()),actor_id=str(uuid4()),command={'action':'confirm_knowledge','target_id':oid,'reason':'Am Original bestätigt','patch':{},'event_date':'2026-09-02','feedback_kind':'interpretation'})
   state=overview(db);self.assertEqual(state['personal'],[]);self.assertFalse(state['knowledge'][0]['data']['required_review']);db.close()
 def test_content_chunks_do_not_drop_tail(self):
  text='Ä🙂\n'*3000
  chunks=list(parts(text))
  self.assertEqual(chunks[0][0],0);self.assertEqual(chunks[-1][0]+len(chunks[-1][1]),len(text))
  self.assertTrue(all(body==text[start:start+len(body)] for start,body in chunks))
  self.assertTrue(all(chunks[i+1][0]<=chunks[i][0]+len(chunks[i][1]) for i in range(len(chunks)-1)))
  self.assertTrue(all(len(t.encode())<=5600 for _,t in chunks))
 def test_chunks_prefer_speaker_boundaries_and_overlap_only_oversized_blocks(self):
  text='Gleb: Kurzer erster Block.\nKimia: Kurzer zweiter Block.\n\n'+('LangerBlock '*20)
  chunks=list(parts(text,size=32,overlap=8))
  self.assertEqual(chunks[0][1],'Gleb: Kurzer erster Block.\n')
  self.assertTrue(chunks[1][1].startswith('Kimia:'))
  self.assertTrue(any(chunks[i+1][0]<chunks[i][0]+len(chunks[i][1]) for i in range(len(chunks)-1)))
  self.assertEqual(chunks[-1][0]+len(chunks[-1][1]),len(text))
 def test_old_work_is_indexed_and_future_sources_are_not(self):
  with tempfile.TemporaryDirectory() as temp:
   db=connect(Path(temp)/'db')
   for day,source in [('2025-01-01','old'),('2026-09-09','future')]:
    job=register(db,source_id=source,event_date=day,title=source,transcript=TEXT)
    apply(db,job,claim(db,job),proposal(observation()),model='fixture')
   rows=documents(db,{'meeting_date':'2026-09-08'})
   self.assertTrue(any(r['kind']=='work' for r in rows))
   self.assertEqual({r['event_date'] for r in rows},{'2025-01-01'})
   db.close()
 def test_request_hash_resume_handles_skipped_cached_embedding_slots(self):
  store=Store();sent=[];job={'id':'a'*64,'lease_token':'lease','pipeline':'v10','expected_revision':110}
  def api(prompt,*a,**k):sent.append(prompt);return {'usage_final':True,'usage':{'input_tokens':2,'output_tokens':1}}
  with tempfile.TemporaryDirectory() as tmp:
   first=DurableCalls(store,job,api,{},tmp,prior_calls=[])
   first('extract','gpt-5.6-terra');first('embed','gpt-5.6-terra');first('align','gpt-5.6-terra')
   prior=[{'index':i,'request_hash':r['request_hash']} for i,r in store.rows.items()]
   resumed=DurableCalls(store,job,api,{},tmp,start_index=3,prior_calls=prior)
   resumed('extract','gpt-5.6-terra');resumed('align','gpt-5.6-terra');resumed('gate','gpt-5.6-terra')
   self.assertEqual(sent,['extract','embed','align','gate']);self.assertEqual(resumed.index,4)
 def test_changed_context_never_reuses_old_response(self):
  store=Store();sent=[]
  def api(*a,**k):sent.append(1);return {'usage_final':True,'usage':{'input_tokens':2,'output_tokens':1}}
  with tempfile.TemporaryDirectory() as tmp:
   a={'id':'a'*64,'lease_token':'lease','pipeline':'v10','expected_revision':1}
   DurableCalls(store,a,api,{},tmp,prior_calls=[])('same','gpt-5.6-terra')
   prior=[{'index':0,'request_hash':store.rows[0]['request_hash']}]
   DurableCalls(store,{**a,'expected_revision':2},api,{},tmp,start_index=1,prior_calls=prior)('same','gpt-5.6-terra')
   self.assertEqual(len(sent),2)

if __name__=='__main__':unittest.main()

class StageResumeTests(unittest.TestCase):
 def run_pipeline(self, transport=False, extraction_recovery=False, failure=None, model='gpt-5.6-terra', extraction_model=None):
  from hybrid_pipeline import process
  from journal_store import JournalUnavailable
  from test_memory import TEXT
  with tempfile.TemporaryDirectory() as temp:
   db=connect(Path(temp)/'db');job=register(db,source_id='old',event_date='2026-07-15',title='Old',transcript=TEXT)
   apply(db,job,claim(db,job),proposal(observation()),model='fixture')
   wid=overview(db)['personal'][0]['id'];calls=[]
   raw={'coverage_notes':[],'observations':[observation(kind='fact',commitment_strength='not_applicable',due_text=None,evidence_ids=['U0001'],state_evidence_ids=[],assignment_score=2,change_score=2,confidence_reason='Belegt',subject='Bericht',search_keywords=[])],
        'meeting_summary':[{'text':'Besprechung des Berichts','evidence_ids':['U0001']}],'search_queries':[]}
   class FakeIndex:
    def __init__(self,*a):pass
    def prepare(self,*a):return {'snapshot_id':'fixture','documents':1}
    def search(self,*a):return [{'id':'hit','kind':'work','target_id':wid,'metadata':{}}]
    def persist(self,*a):pass
   case=self;sent_models=[]
   class FakeAPI:
    store=object()
    def __init__(self):self.primary_responses=[]
    def __call__(self,prompt,model,max_tokens=0,schema=None):
     sent_models.append(model)
     if schema is None:
      name='extract';value=copy.deepcopy(raw)
     elif 'meeting_summary' in schema.get('properties',{}):
      name='extract';value=raw
      allowed=schema['$defs']['evidence_id']['enum'];reference={'$ref':'#/$defs/evidence_id'}
      case.assertEqual(allowed,['U0001','U0002'])
      case.assertEqual(schema['properties']['observations']['items']['properties']['evidence_ids']['items'],reference)
      case.assertEqual(schema['properties']['meeting_summary']['items']['properties']['evidence_ids']['items'],reference)
      case.assertEqual(schema['properties']['meeting_display_title']['anyOf'][1]['properties']['evidence_ids']['items'],reference)
      case.assertIn('Gültige Evidence-IDs sind ausschließlich',prompt)
     elif 'results' in schema['properties']:
      name='lifecycle'
      if transport:calls.append(name);raise JournalUnavailable('synthetic network outage')
      value={'results':{'0':'unchanged'} if 'lifecycle' in calls else {}}
     elif 'endstate' in schema['properties']:
      name='gate';value={'verdicts':[],
                         'endstate':[{'index':0,'status':'unchanged','reason':'Belegt','earlier_evidence_ids':[],
                                      'later_evidence_ids':[],'final_claim':None}],
                         'final_summary':[{'index':0,'status':'unchanged','reason':'Belegt',
                                           **raw['meeting_summary'][0]}]}
     else:
      name='align';value={'coverage_notes':[],'observations':[{**raw['observations'][0],'source_index':0}]}
     if name=='extract':
      attempt=calls.count('extract')
      value=copy.deepcopy(value)
      if (failure=='invalid' and attempt<2) or failure=='third_invalid':
       value['observations'][0]['evidence_ids']=['U9999']
      elif failure=='non_id_second':
       if attempt==0:value['observations'][0]['evidence_ids']=['U9999']
       else:value['observations'][0].update(kind='fact',commitment_strength='explicit')
      elif failure=='non_id_first':
       if attempt==0:value['observations'][0].update(kind='fact',commitment_strength='explicit')
       else:value['observations'][0]['evidence_ids']=['U9999']
     calls.append(name)
     response={'content':[{'type':'text','text':json.dumps(value)}],'stop_reason':'end_turn','usage':{},'elapsed_seconds':0}
     if schema is None:self.primary_responses.append(response)
     return response
   meeting={'id':'new','source_id':'new','meeting_date':'2026-07-16','title':'Followup','raw_transcript':TEXT}
   api=FakeAPI()
   with patch('hybrid_pipeline.SearchIndex',FakeIndex):
    if transport:
     with self.assertRaises(JournalUnavailable):process(db,meeting,'gpt-5.6-terra',api=api)
    elif failure and not extraction_recovery:
     with self.assertRaisesRegex(ValidationError,'Unknown or missing evidence ID'):
      process(db,meeting,'gpt-5.6-terra',api=api)
    elif failure=='third_invalid':
     with self.assertRaisesRegex(ValidationError,'Unknown or missing evidence ID'):
      process(db,meeting,'gpt-5.6-terra',api=api,extraction_recovery=True)
    elif failure=='non_id_first':
     with self.assertRaisesRegex(ValidationError,'Unknown or missing evidence ID'):
      process(db,meeting,'gpt-5.6-terra',api=api,extraction_recovery=True)
    elif failure=='non_id_second':
     with self.assertRaisesRegex(ValidationError,'Contradictory commitment classification'):
      process(db,meeting,'gpt-5.6-terra',api=api,extraction_recovery=True)
    else:self.assertEqual(process(db,meeting,model,api=api,extraction_recovery=extraction_recovery,extraction_model=extraction_model)['status'],'applied')
   db.close();self.primary_responses=api.primary_responses;self.sent_models=sent_models;return calls
 def test_explicit_mixed_model_routes_only_extraction(self):
  from hybrid_pipeline import version
  self.assertEqual(self.run_pipeline(model='gpt-6-sol',extraction_model='gpt-6-luna'),
                   ['extract','align','lifecycle','lifecycle','gate'])
  self.assertEqual(self.sent_models,['gpt-6-luna','gpt-6-sol','gpt-6-sol','gpt-6-sol','gpt-6-sol'])
  self.assertIn(':gpt-6-sol:extract=gpt-6-luna:',version('gpt-6-sol',extraction_model='gpt-6-luna'))
  self.assertNotIn(':extract=',version('gpt-5.6-terra'))
 def test_missing_lifecycle_id_repairs_only_that_stage(self):
  self.assertEqual(self.run_pipeline(),['extract','align','lifecycle','lifecycle','gate'])
 def test_transport_error_never_triggers_semantic_model_retry(self):
  self.assertEqual(self.run_pipeline(True),['extract','align','lifecycle'])
 def test_explicit_extraction_recovery_adds_one_catalog_constrained_call(self):
  self.assertEqual(self.run_pipeline(extraction_recovery=True,failure='invalid'),
                   ['extract','extract','extract','align','lifecycle','lifecycle','gate'])
  from future_summary import from_response
  from test_memory import TEXT
  self.assertEqual(from_response(self.primary_responses[-1],units(TEXT),'Followup')['ai_summary'],
                   'Besprechung des Berichts')
  self.assertEqual(len(self.primary_responses),3)
 def test_default_extraction_still_stops_after_two_invalid_responses(self):
  self.assertEqual(self.run_pipeline(failure='invalid'),['extract','extract'])
 def test_recovery_stops_after_third_invalid_evidence_response(self):
  self.assertEqual(self.run_pipeline(extraction_recovery=True,failure='third_invalid'),
                   ['extract','extract','extract'])
  self.assertEqual(len(self.primary_responses),2)
 def test_recovery_stops_after_second_non_evidence_validation_failure(self):
  self.assertEqual(self.run_pipeline(extraction_recovery=True,failure='non_id_second'),
                   ['extract','extract'])
 def test_recovery_stops_when_only_second_failure_is_evidence_related(self):
  self.assertEqual(self.run_pipeline(extraction_recovery=True,failure='non_id_first'),
                   ['extract','extract'])
