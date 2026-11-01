"""Reconstruct complete saved proposal against pinned historical projection."""
import copy,json,os,sqlite3,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PRIVATE=ROOT/'private'
sys.path.insert(0,str(PRIVATE/'runtime'));sys.dont_write_bytecode=True
CANDIDATE='--candidate' in sys.argv
if CANDIDATE:sys.path.insert(0,str(ROOT/'overlay'))
for key in list(os.environ):
 if key.startswith(('OPENAI_','ANTHROPIC_','DASHBOARD_','MEMORY_','SUPABASE_')):os.environ.pop(key)
def audit(event,args):
 if event.startswith('socket.') or event in ('subprocess.Popen','os.system'):raise RuntimeError('Offline replay forbids network and subprocesses')
sys.addaudithook(audit)
import memory,reconcile,hybrid_pipeline as hp
from retrieval_context import unpack_catalog
from temporal_guard import guard
v=json.loads((PRIVATE/'inputs.json').read_text())
def section(prompt,label):return json.JSONDecoder().raw_decode(prompt.split('\n'+label+':\n',1)[1])[0]
def response(call):return hp.decoded(json.loads(call['response_json']))
reports=[]
for job in v['jobs']:
 r={'job':job['id'][:8],'revision':job['expected_revision']};reports.append(r)
 try:
  db=memory.connect(':memory:');source=sqlite3.connect('file:'+str((PRIVATE/(r['job']+'.sqlite')).resolve())+'?mode=ro',uri=True);source.backup(db);source.close()
  assert db.execute('SELECT revision FROM projection_cursor').fetchone()[0]==job['expected_revision']
  calls=[c for c in v['calls'] if c['job_id']==job['id']]
  for call in calls:
   import hashlib
   assert hashlib.sha256(call['request_json'].encode()).hexdigest()==call['request_hash']
   assert hashlib.sha256(call['response_json'].encode()).hexdigest()==call['response_hash']
  extract,compact,gate=calls[0],calls[-2],calls[-1]
  compact_prompt=json.loads(compact['request_json'])['prompt'];gate_prompt=json.loads(gate['request_json'])['prompt']
  originals=section(compact_prompt,'Vollständiges Original');packed=unpack_catalog(section(compact_prompt,'Kandidaten'))
  actual_gate=section(gate_prompt,'Kandidaten');raw=response(compact)
  document=job['document'];meeting={'id':job['id'],'source_id':job['source_id'],'title':document['title'],'meeting_date':job['event_date'],'raw_transcript':document['body'],'observed_at':document['observed_at']}
  known=memory.known_work_ids(db,job['event_date'])
  allwork=reconcile.candidates(db,meeting,{'observations':[]},prior_days_only=False)
  aliases={};matters={};work=[]
  for item in packed['work']:
   fields=[k for k in item if k not in ('id','parent_matter_alias','work_index')]
   matches=[w for w in allwork if all(w.get(k)==item[k] for k in fields)]
   if len(matches)!=1:raise ValueError('Historical work alias is not unique: '+item['id']+' matches='+str(len(matches)))
   w=matches[0];aliases[item['id']]=w['id'];work.append(w)
   if item['parent_matter_alias'] is not None:
    key=item['parent_matter_alias'];mid=w['parent_matter_id']
    assert key not in matters or matters[key]==mid
    matters[key]=mid
  for item in actual_gate:
   if 'source_index' not in item:continue
   old=next((o for o in raw['observations'] if o['source_index']==item['source_index']),None)
   if old and old.get('matter_id') is not None and item.get('matter_id') is not None:
    alias=old['matter_id'];assert alias not in matters or matters[alias]==item['matter_id'];matters[alias]=item['matter_id']
  decoded=copy.deepcopy(raw)
  for item in decoded['observations']:
   if item.get('matter_id') is not None:item['matter_id']=matters[item['matter_id']]
   if item.get('update_target') is not None:item['update_target']=aliases[item['update_target']]
  decoded['observations'].sort(key=lambda o:o['source_index'])
  proposal=hp.resolve_v10(decoded,originals)
  from processor import validate_semantics,apply_work_gate
  validate_semantics(proposal);memory.validate(proposal,meeting['raw_transcript'],known)
  results=hp.lifecycle_results({'results':raw['work_results']},work)
  additions=reconcile.observations(work,results,originals)
  for item in additions:
   life=item['lifecycle_review'];item.update(assignment_score=life['assignment_score'],change_score=life['change_score'],confidence_reason=life['reason'])
   item['source_spans']=[{'start':originals[i]['start'],'end':originals[i]['end'],'quote':originals[i]['text']} for i in life['evidence_ids']]
  proposal['observations'].extend(additions);hp.confidence(proposal);memory.validate(proposal,meeting['raw_transcript'],known)
  candidates=[{'index':i,**o} for i,o in enumerate(proposal['observations']) if o['kind']=='commitment' or o.get('update')!='none']
  assert candidates==actual_gate,'Reconstructed gate candidates differ from immutable request'
  r['complete_pre_gate_proposal']='PASS';r['observations']=len(proposal['observations'])
  proposal=hp.guard_gate_escalation(proposal,apply_work_gate(copy.deepcopy(proposal),response(gate)['verdicts'],originals))
  for item in proposal['observations']:
   existing={(s['start'],s['end']) for s in item['source_spans']}
   for eid in item.get('work_gate',{}).get('evidence_ids',[]):
    unit=originals[eid]
    if (unit['start'],unit['end']) not in existing:item['source_spans'].append({'start':unit['start'],'end':unit['end'],'quote':unit['text']})
   for quote in item['quotes']:
    if not any(s['quote']==quote for s in item['source_spans']):
     for unit in originals.values():
      if unit['text']==quote:item['source_spans'].append({'start':unit['start'],'end':unit['end'],'quote':quote});break
  hp.confidence(proposal);memory.validate(proposal,meeting['raw_transcript'],known);r['complete_gate']='PASS'
  proposal=guard(db,meeting,proposal);r['temporal_guard']='PASS'
  localjob=memory.register(db,source_id=meeting['source_id'],event_date=meeting['meeting_date'],title=meeting['title'],transcript=meeting['raw_transcript'],pipeline=job['pipeline'])
  token=memory.claim(db,localjob,seconds=600)
  stage='apply'
  result=memory.apply(db,localjob,token,proposal,model='saved-offline')
  rejected=[i for i,o in enumerate(proposal['observations']) if o.get('update_target') and o.get('work_gate',{}).get('verdict')=='unsupported']
  for i in rejected:
   oid=memory.fingerprint(localjob+':observation:'+str(i))
   assert db.execute('SELECT count(*) FROM work_events WHERE observation_id=?',(oid,)).fetchone()[0]==0
   row=db.execute('SELECT matter_id FROM observations WHERE id=?',(oid,)).fetchone()
   assert row and row[0]==proposal['observations'][i]['matter_id']
  r['rejected_candidates_without_work_event']=len(rejected)
  r['apply']='PASS';r['applied_observations']=len(result)
 except Exception as error:
  r.update(error_type=type(error).__name__,error=str(error),frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)[-6:]])
  if 'proposal' in locals():(PRIVATE/(r['job']+'-proposal.json')).write_text(json.dumps(proposal));(PRIVATE/(r['job']+'-proposal.json')).chmod(0o600)
(ROOT/('candidate-results.json' if CANDIDATE else 'saved-results.json')).write_text(json.dumps(reports,indent=2)+'\n');print(json.dumps(reports))
assert len(reports)==2
if CANDIDATE:assert all(r.get('apply')=='PASS' for r in reports)
else:assert all(r.get('error')=='Work update belongs to a different matter' and r.get('complete_gate')=='PASS' for r in reports)
