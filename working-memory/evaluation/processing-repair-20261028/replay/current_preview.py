"""Fully local generation preview; hashes all historical accepted entries."""
import copy,hashlib,json,os,sqlite3,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PRIVATE=ROOT/'private'
sys.path[:0]=[str(ROOT/'overlay'),str(PRIVATE/'runtime')];sys.dont_write_bytecode=True
for key in list(os.environ):
 if key.startswith(('OPENAI_','ANTHROPIC_','DASHBOARD_','MEMORY_','SUPABASE_')):os.environ.pop(key)
def audit(event,args):
 if event.startswith('socket.') or event in ('subprocess.Popen','os.system'):raise RuntimeError('Offline preview forbids network and subprocesses')
sys.addaudithook(audit)
import memory
from journal_projection import rebuild,prepare_source,digest
from generation_service import make_plan
from generation_review import compile_generation,verify_generation
old=json.loads((PRIVATE/'inputs.json').read_text());current=json.loads((PRIVATE/'current-inputs.json').read_text())
class Store:
 space_id=current['space']['id']
 def space(self):return current['space']
 def entries(self,*,through=None):return [e for e in current['entries'] if e['revision']<=through]
 def source(self,version_id):return next(s for s in current['sources'] if s['id']==version_id)
report={'current_revision':current['space']['revision'],'memory_file':str(Path(memory.__file__).relative_to(ROOT)),'memory_sha256':hashlib.sha256(Path(memory.__file__).read_bytes()).hexdigest()}
try:
 captured={}
 def profile(frame,event,arg):
  if event=='return' and frame.f_code.co_name=='rebuild' and Path(frame.f_code.co_filename).name=='journal_projection.py' and 'logical' in frame.f_locals:captured['base']=frame.f_locals['logical']
 sys.setprofile(profile)
 path=PRIVATE/'current-patched.sqlite';rebuild(Store(),path,through=current['space']['revision']);sys.setprofile(None)
 report['current_historical_hash_rebuild']='PASS';print(json.dumps(report),flush=True)
 base=captured['base'];db=memory.connect(path)
 report['logical_sources_before']=sum(e['kind']=='source' for e in base);report['human_decisions_before']=sum(e['kind']=='human' for e in base)
 changes=[]
 for job in old['jobs']:
  doc=job['document'];proposal=json.loads((PRIVATE/(job['id'][:8]+'-proposal.json')).read_text())
  source={k:doc[k] for k in ('source_id','event_date','observed_at','title')};source.update(id=job['id'],content_hash=doc['body_hash'],transcript=doc['body'])
  pinned=memory.connect(':memory:');historical=sqlite3.connect('file:'+str((PRIVATE/(job['id'][:8]+'.sqlite')).resolve())+'?mode=ro',uri=True);historical.backup(pinned);historical.close()
  payload=prepare_source(pinned,source,proposal,pipeline=job['pipeline'],model='gpt-6.1-sol',provenance={'mode':'owner_reviewed_saved_result','context_revision':job['expected_revision'],'job_id':job['id'],'no_new_model_calls':True},usage={'durable_call_count':sum(c['job_id']==job['id'] for c in old['calls'])});pinned.close()
  changes.append({'source_id':source['source_id'],'action':'add','entry':{'kind':'source','source':source,'payload':payload},'reason':'Vorhandene vollständige Modellantworten nach Korrektur der blockierten Aufgabenaktion; keine neuen Modellaufrufe.'})
 plan,reviews=make_plan(base,changes,[],[])
 payload,projection,prepared=compile_generation(base,plan,source_reviews=reviews,identity_links=[],topic_identity_links=[],reason='Zwei gespeicherte Ergebnisse chronologisch und ohne neue Modellaufrufe wiederherstellen.',_retain_projection=True,_base_projection=db)
 projection.close();report.update(generation_compile='PASS',personal_decisions_preserved=payload['personal_decisions_preserved'],new_sources=len(payload['new_sources']),review_sha256=payload['review_sha256'])
 verified,entries=verify_generation(base,payload,_projection=True,_base_projection=db);verified.close();report['generation_verify']='PASS'
 assert payload['personal_decisions_preserved']==report['human_decisions_before']
 target=PRIVATE/'generation-preview.json';target.write_text(json.dumps(payload));target.chmod(0o600)
 db.close()
except Exception as error:
 sys.setprofile(None);report.update(error_type=type(error).__name__,error=str(error),frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)[-6:]])
(ROOT/'current-preview-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
assert report.get('current_historical_hash_rebuild')=='PASS'
assert report.get('generation_compile')=='PASS' and report.get('generation_verify')=='PASS'
assert report.get('new_sources')==2
assert report.get('personal_decisions_preserved')==report.get('human_decisions_before')==11
assert report.get('memory_sha256')=='e822eb293d6d87cc74f0df5671e4d656c060c81ccce6502860b7c142803c2316'
