"""Offline previews for two separately guarded jobs, notes and reverse generation."""
import copy,hashlib,json,os,sqlite3,sys,traceback,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PRIVATE=ROOT/'private'
sys.path[:0]=[str(ROOT/'overlay'),str(PRIVATE/'runtime')];sys.dont_write_bytecode=True
for key in list(os.environ):
 if key.startswith(('OPENAI_','ANTHROPIC_','DASHBOARD_','MEMORY_','SUPABASE_')):os.environ.pop(key)
def audit(event,args):
 if event.startswith('socket.') or event in ('subprocess.Popen','os.system'):raise RuntimeError('Offline preview forbids network and subprocesses')
sys.addaudithook(audit)
import memory
from journal_projection import prepare_source,digest
from generation_service import make_plan
from generation_review import logical_entries,compile_generation,verify_generation
from canonical_archive import verify_note,verify_document
from processor import units
from future_summary import from_response
from durable_calls import encode,sha
old=json.loads((PRIVATE/'inputs.json').read_text());current=json.loads((PRIVATE/'current-inputs.json').read_text());notes=json.loads((PRIVATE/'existing-notes.json').read_text())
prior=json.loads((ROOT/'current-preview-results.json').read_text())
patchhash=hashlib.sha256(Path(memory.__file__).read_bytes()).hexdigest()
assert prior['memory_sha256']==patchhash and prior['current_historical_hash_rebuild']=='PASS' and prior['current_revision']==current['space']['revision']
report={'base_revision':current['space']['revision'],'memory_sha256':patchhash,'existing_notes':len(notes),'steps':[]}
def save_private(name,value):
 p=PRIVATE/name;p.write_text(json.dumps(value));p.chmod(0o600)
def checked_compile(base,plan,reviews,db,reason):
 payload,projection,prepared=compile_generation(base,plan,source_reviews=reviews,identity_links=[],topic_identity_links=[],reason=reason,_retain_projection=True,_base_projection=db)
 verified,_=verify_generation(base,payload,_projection=True,_base_projection=db);verified.close()
 assert len(json.dumps(payload,ensure_ascii=False,allow_nan=False).encode())<=3700000
 return payload,projection,prepared
try:
 sources={s['id']:s for s in current['sources']};events=copy.deepcopy(current['entries'])
 for e in events:
  if e['kind']=='source':e['source']=sources[e['source_version']]
 base=logical_entries(events);originalbase=copy.deepcopy(base)
 db=memory.connect(':memory:');filedb=sqlite3.connect('file:'+str((PRIVATE/'current-patched.sqlite').resolve())+'?mode=ro',uri=True);filedb.backup(db);filedb.close()
 assert db.execute('SELECT revision FROM projection_cursor').fetchone()[0]==current['space']['revision']
 originalhumans=[e for e in base if e['kind']=='human'];initialcounts={'sources':sum(e['kind']=='source' for e in base),'human':len(originalhumans)}
 print(json.dumps({'logical_base':'PASS',**initialcounts}),flush=True)
 jobs=sorted(old['jobs'],key=lambda j:j['expected_revision']);added=[]
 for step,job in enumerate(jobs):
  expected=current['space']['revision']+step;doc=job['document'];verify_document(doc)
  call=next(c for c in old['calls'] if c['job_id']==job['id'] and c['call_index']==0)
  assert hashlib.sha256(call['response_json'].encode()).hexdigest()==call['response_hash']
  summary=from_response(json.loads(call['response_json']),units(doc['body']),doc['title'],doc['body'])
  summaryjson=encode(summary);summaryhash=sha(summaryjson)
  note={'document_id':doc['id'],'origin':'source_summary','origin_id':job['id'],'note_json':summaryjson,'note_hash':summaryhash,'id':sha(':'.join([doc['id'],'source_summary',job['id'],summaryhash]))}
  verify_note(note);assert doc.get('redaction_id') is None
  existing=[n for n in notes if n['id']==note['id']]
  for n in existing:assert all(n[k]==value for k,value in note.items()) and n.get('redaction_id') is None
  proposal=json.loads((PRIVATE/(job['id'][:8]+'-proposal.json')).read_text())
  source={k:doc[k] for k in ('source_id','event_date','observed_at','title')};source.update(id=job['id'],content_hash=doc['body_hash'],transcript=doc['body'])
  pinned=memory.connect(':memory:');historic=sqlite3.connect('file:'+str((PRIVATE/(job['id'][:8]+'.sqlite')).resolve())+'?mode=ro',uri=True);historic.backup(pinned);historic.close()
  payload=prepare_source(pinned,source,proposal,pipeline=job['pipeline'],model='gpt-6.1-sol',provenance={'mode':'owner_reviewed_saved_result','context_revision':job['expected_revision'],'job_id':job['id'],'no_new_model_calls':True},usage={'durable_call_count':sum(c['job_id']==job['id'] for c in old['calls'])});pinned.close();payload['archive_note']=note
  reason='Gespeicherte vollständige Modellantworten nach Korrektur der blockierten Aufgabenaktion ohne neue Modellaufrufe übernehmen.'
  change={'source_id':source['source_id'],'action':'add','entry':{'kind':'source','source':source,'payload':payload},'reason':reason}
  plan,reviews=make_plan(base,[change],[],[]);generation,nextdb,prepared=checked_compile(base,plan,reviews,db,reason)
  assert generation['personal_decisions_preserved']==len(originalhumans)
  assert [e for e in prepared if e['kind']=='human']==originalhumans
  assert len(generation['new_sources'])==1 and generation['new_sources'][0]['id']==job['id']
  assert next(e for e in prepared if e['kind']=='source' and e['source']['id']==job['id'])['payload']['archive_note']==note
  review_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'dashboard-repair:'+patchhash+':'+str(expected)+':'+job['id']))
  command_id=str(uuid.uuid5(uuid.NAMESPACE_URL,review_id+':accept'))
  artifact={'expected_job_updated_at':job['updated_at'],'note_put':note,'stage_request':{'review_id':review_id,'expected_revision':expected,'label':'Gespeichertes Ergebnis '+job['id'][:8],'changes':[change],'identity_links':[],'topic_links':[],'reason':reason,'job_id':job['id']},'decide_request':{'review_id':review_id,'command_id':command_id,'expected_revision':expected,'review_sha256':generation['review_sha256'],'action':'accept','reason':reason},'verified_payload':generation}
  save_private('sequential-'+job['id'][:8]+'.json',artifact)
  result={'job':job['id'][:8],'expected_revision':expected,'expected_next_revision':expected+1,'review_sha256':generation['review_sha256'],'new_sources':1,'personal_decisions_preserved':generation['personal_decisions_preserved'],'summary_paragraphs':len(summary['summary_evidence']),'note_id':note['id'],'summary_verified':'PASS','compile':'PASS','verify':'PASS'}
  report['steps'].append(result);print(json.dumps(result),flush=True)
  added.append(source['source_id']);db.close();db=nextdb;base=prepared
 reason='Vorbereiteter Rückweg: ausschließlich die zwei neu übernommenen Quellen entfernen, bestehenden Stand und persönliche Entscheidungen erhalten.'
 reverse,reviews=make_plan(base,[{'source_id':key,'action':'remove','entry':None,'reason':reason} for key in added],[],[])
 reversal,reversedb,reversedentries=checked_compile(base,reverse,reviews,db,reason)
 assert reversedentries==originalbase
 assert reversal['personal_decisions_preserved']==len(originalhumans)
 save_private('rollback-generation.json',reversal);reversedb.close();db.close()
 report['rollback']={'compile':'PASS','verify':'PASS','original_logical_entries_restored':True,'personal_decisions_preserved':len(originalhumans),'review_sha256':reversal['review_sha256']}
 report['status']='PASS'
except Exception as error:
 report.update(status='FAIL',error_type=type(error).__name__,error=str(error),frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)[-6:]])
(ROOT/'sequential-preview-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
assert report['status']=='PASS' and len(report['steps'])==2
