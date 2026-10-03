"""One public Journal/RPC write/replay cycle, only a new disposable draft space."""
import hashlib,json,os,secrets,subprocess,urllib.request,urllib.error,uuid
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'stage-write-replay-1';os.umask(0o077);RUN.mkdir(mode=0o700)
env={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if '=' in l)}
owner=json.loads((ROOT/'network-prepare-1/owner-refreshed-tokens-private.json').read_text())['user']['id'];wrong=json.loads((ROOT/'test-user.json').read_text())['id']
space=str(uuid.uuid4());command=str(uuid.uuid4());entity=str(uuid.uuid4());token=secrets.token_hex(32);digest=hashlib.sha256(token.encode()).hexdigest()
(RUN/'fixture-private.json').write_text(json.dumps({'space':space,'command':command,'entity':entity,'token':token}))
def sql(q):
 x=subprocess.run(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-U','supabase_admin','-d','postgres','-XAt','-v','ON_ERROR_STOP=1'],input=q.encode(),capture_output=True)
 if x.returncode:(RUN/'sql-private.stderr').write_bytes(x.stderr);raise RuntimeError('Stage SQL failed')
 return x.stdout.decode().strip()
def aggregate():return json.loads(sql("SELECT jsonb_build_object('spaces',(SELECT jsonb_agg(jsonb_build_object('id',id,'revision',revision,'archive_revision',archive_revision) ORDER BY id) FROM public.wm_spaces WHERE id<>'"+space+"'),'jobs',(SELECT jsonb_agg(x ORDER BY x->>'state') FROM (SELECT jsonb_build_object('state',state,'count',count(*)) x FROM public.wm_jobs WHERE space_id<>'"+space+"' GROUP BY state) j))"))
def request(path,data=None,bearer=None,journal=False,name='case'):
 headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+(bearer or env['ANON_KEY']),'Content-Type':'application/json'}
 if journal:headers['X-Memory-Token']=token
 req=urllib.request.Request('https://178-105-167-26.nip.io/supabase'+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=30) as r:status=r.status;body=r.read()
 except urllib.error.HTTPError as r:status=r.code;body=r.read()
 (RUN/(name+'-private.json')).write_bytes(body);evidence['cases'][name]={'http':status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()};return status,json.loads(body)
evidence={'problem_id':'HZ-MIGRATION-20261003-STAGE-WRITE-REPLAY','cycle':1,'question':'Does public scoped Journal/RPC preserve revision/idempotency and owner boundaries on a new disposable space?','cases':{},'provider_calls':0,'source_mutation':False,'existing_target_business_mutation':False,'status':'FAILED'}
before=aggregate();(RUN/'existing-before-private.json').write_text(json.dumps(before))
try:
 assert sql("SELECT count(*) FROM public.wm_spaces WHERE id='"+space+"'")=='0'
 sql("BEGIN;INSERT INTO public.wm_spaces(id,owner_id,label,state) VALUES('"+space+"','"+owner+"','HZ-MIGRATION disposable write test','draft');INSERT INTO memory_private.service_tokens(token_hash,space_id,label,expires_at) VALUES('"+digest+"','"+space+"','HZ-MIGRATION disposable scoped token',now()+interval '1 hour');COMMIT;")
 body={'op':'append','space_id':space,'expected_revision':0,'command_id':command,'kind':'human','actor_id':owner,'payload':{'action':'migration_test','target_id':entity,'reason':'Disposable isolated migration contract'}}
 status,res=request('/functions/v1/working-memory-journal',body,journal=True,name='append');assert status==200 and res=={'revision':1,'repeated':False}
 status,res=request('/functions/v1/working-memory-journal',body,journal=True,name='exact_replay');assert status==200 and res=={'revision':1,'repeated':True}
 changed={**body,'payload':{**body['payload'],'reason':'Different disposable content'}};assert request('/functions/v1/working-memory-journal',changed,journal=True,name='changed_replay')[0]==409
 stale={**body,'command_id':str(uuid.uuid4())};assert request('/functions/v1/working-memory-journal',stale,journal=True,name='stale_revision')[0]==409
 badactor={**body,'actor_id':wrong,'command_id':str(uuid.uuid4()),'expected_revision':1};assert request('/functions/v1/working-memory-journal',badactor,journal=True,name='wrong_actor')[0]==403
 badscope={**body,'space_id':str(uuid.uuid4())};assert request('/functions/v1/working-memory-journal',badscope,journal=True,name='wrong_scope')[0]==403
 credentials=json.loads((ROOT/'public-auth-query-1/synthetic-login-private.json').read_text());status,auth=request('/auth/v1/token?grant_type=password',credentials,name='real_wrong_user_login');assert status==200 and auth['user']['id']==wrong
 status,rows=request('/rest/v1/wm_spaces?id=eq.'+space+'&select=id',bearer=auth['access_token'],name='wrong_owner_rls');assert status==200 and rows==[]
 rpc={'p_space_id':space,'p_expected_revision':1,'p_command_id':str(uuid.uuid4()),'p_kind':'human','p_payload':body['payload'],'p_actor_id':wrong};assert request('/rest/v1/rpc/wm_append',rpc,bearer=auth['access_token'],name='browser_direct_rpc_denied')[0]==403
 status,rows=request('/functions/v1/working-memory-journal',{'op':'entries','space_id':space,'after':0,'through':1},journal=True,name='journal_readback');assert status==200 and len(rows)==1 and rows[0]['payload']['target_id']==entity
 assert sql("SELECT revision::text||':'||(SELECT count(*) FROM public.wm_journal WHERE space_id='"+space+"')::text FROM public.wm_spaces WHERE id='"+space+"'")=='1:1'
 after=aggregate();(RUN/'existing-after-private.json').write_text(json.dumps(after));assert before==after
 evidence.update(status='STAGE_WRITE_REPLAY_PASSED',disposable_space_final_revision=1,disposable_journal_rows=1,original_target_revisions_jobs_unchanged=True,exact_replay_no_extra_row=True)
except Exception as err:evidence.update(failure_type=type(err).__name__,failure_message=str(err) if not isinstance(err,urllib.error.HTTPError) else 'HTTP '+str(err.code))
finally:
 sql("UPDATE memory_private.service_tokens SET enabled=false WHERE token_hash='"+digest+"' AND space_id='"+space+"';")
 evidence['disposable_token_disabled']=True;evidence['test_data_retained_until_final_source_restore']=True
 (RUN/'receipt.json').write_text(json.dumps(evidence,indent=2));(RUN/'hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.iterdir() if p.is_file()},indent=2));print(json.dumps(evidence))
if evidence['status']=='FAILED':raise SystemExit(1)
