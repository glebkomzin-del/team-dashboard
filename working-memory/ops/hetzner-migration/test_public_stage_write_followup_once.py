"""Bounded REST16 followup on the SAME disposable space; no source writes."""
import hashlib,json,os,secrets,subprocess,urllib.request,urllib.error,uuid
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'stage-write-replay-followup-1';os.umask(0o077)
(RUN/'attempt.marker').open('x').write('one authorized followup')
env={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if '=' in l)}
fixture=json.loads((ROOT/'stage-write-replay-1/fixture-private.json').read_text());space=fixture['space'];entity=fixture['entity'];token=fixture['token'];digest=hashlib.sha256(token.encode()).hexdigest()
owner=json.loads((ROOT/'network-prepare-1/owner-refreshed-tokens-private.json').read_text())['user']['id'];wrong=json.loads((ROOT/'test-user.json').read_text())['id']
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

evidence={'problem_id':'HZ-MIGRATION-20261003-STAGE-WRITE-REPLAY','alias_of':'HZ-MIGRATION-20261003-STAGE-WRITE','original_failed_cycles':1,'followup_cycle':1,'cases':{},'status':'FOLLOWUP_FAILED','source_mutation':False,'provider_calls':0}
compose=ROOT/'compose.yaml';old=compose.read_bytes();assert hashlib.sha256(old).hexdigest()=='ca2c25855596b39629808f9756ffe152b846211363ba9e5dfae2d20c7c4645b1'
oldimage='postgrest/postgrest:v14.17@sha256:b48f6387a6cab5013eb19401361a316a3a9cf7f4c2893ea98f54f8a3effbe178';newimage='postgrest/postgrest:v16.4@sha256:c3638ac25258ede665db66a4052b6fd30db4f22789327dce84599409136da35f'
new=old.decode().replace(oldimage,newimage).replace('test: [CMD, postgrest, --ready]','test: [CMD, /bin/postgrest, --ready]');assert new!=old.decode()
(RUN/'compose-new.yaml').write_text(new)
(RUN/'rollback.sh').write_text('#!/bin/sh\nset -eu\ncd /opt/dashboard-supabase-20261003\nactual=$(sha256sum compose.yaml | cut -d \' \' -f1)\n[ \"$actual\" = \"'+hashlib.sha256(new.encode()).hexdigest()+'\" ]\ncp stage-write-replay-followup-1/compose-original.yaml compose.yaml\ndocker compose --env-file .private.env up -d --no-deps --force-recreate --wait --wait-timeout 60 rest\n')
def containers():
 x=subprocess.run(['docker','inspect']+['dashboard-supabase-20261003-'+n+'-1' for n in ['db','auth','api-gw','functions']],capture_output=True,check=True);return {d['Name']:(d['Id'],d['Image']) for d in json.loads(x.stdout)}
baseline=containers();before=aggregate();(RUN/'existing-before-private.json').write_text(json.dumps(before))
try:
 assert sql('SELECT count(*) FROM pg_stat_activity WHERE pid=13116')=='0'
 assert sql("SELECT revision::text||':'||(SELECT count(*) FROM public.wm_journal WHERE space_id='"+space+"')::text FROM public.wm_spaces WHERE id='"+space+"'")=='1:1'
 compose.write_text(new)
 x=subprocess.run(['docker','compose','--env-file','.private.env','up','-d','--no-deps','--force-recreate','--wait','--wait-timeout','60','rest'],cwd=ROOT,capture_output=True);(RUN/'rest-recreate.stdout').write_bytes(x.stdout);(RUN/'rest-recreate.stderr').write_bytes(x.stderr);assert x.returncode==0
 assert containers()==baseline
 x=subprocess.run(['docker','inspect','dashboard-supabase-20261003-rest-1'],capture_output=True,check=True);(RUN/'rest-after-inspect-private.json').write_bytes(x.stdout);di=json.loads(x.stdout)[0];assert di['Image']=='sha256:c3638ac25258ede665db66a4052b6fd30db4f22789327dce84599409136da35f' and di['State']['Health']['Status']=='healthy'
 def refresh(uid,name):
  rt=sql("SELECT token FROM auth.refresh_tokens WHERE user_id='"+uid+"' AND NOT revoked ORDER BY id DESC LIMIT 1")
  assert rt
  status,auth=request('/auth/v1/token?grant_type=refresh_token',{'refresh_token':rt},name=name);assert status==200 and auth['user']['id']==uid;return auth['access_token']
 ownerjwt=refresh(owner,'owner_target_refresh');wrongjwt=refresh(wrong,'wrong_target_refresh')
 sql("UPDATE memory_private.service_tokens SET enabled=true,expires_at=now()+interval '10 minutes' WHERE token_hash='"+digest+"' AND space_id='"+space+"';")
 body={'op':'append','space_id':space,'expected_revision':1,'command_id':str(uuid.uuid4()),'kind':'human','actor_id':owner,'payload':{'action':'migration_test','target_id':entity,'reason':'Disposable REST16 executor regression'}}
 status,res=request('/functions/v1/working-memory-journal',body,journal=True,name='append');assert status==200 and res=={'revision':2,'repeated':False}
 status,res=request('/functions/v1/working-memory-journal',body,journal=True,name='exact_replay');assert status==200 and res=={'revision':2,'repeated':True}
 assert request('/functions/v1/working-memory-journal',{**body,'payload':{**body['payload'],'reason':'Changed disposable content'}},journal=True,name='changed_replay')[0]==409
 assert request('/functions/v1/working-memory-journal',{**body,'command_id':str(uuid.uuid4())},journal=True,name='stale_revision')[0]==409
 assert request('/functions/v1/working-memory-journal',{**body,'actor_id':wrong,'command_id':str(uuid.uuid4()),'expected_revision':2},journal=True,name='wrong_actor')[0]==403
 assert request('/functions/v1/working-memory-journal',{**body,'space_id':str(uuid.uuid4())},journal=True,name='wrong_scope')[0]==403
 status,rows=request('/rest/v1/wm_spaces?id=eq.'+space+'&select=id',bearer=wrongjwt,name='wrong_owner_rls');assert status==200 and rows==[]
 rpc={'p_space_id':space,'p_expected_revision':2,'p_command_id':str(uuid.uuid4()),'p_kind':'human','p_payload':body['payload'],'p_actor_id':wrong}
 assert request('/rest/v1/rpc/wm_append',rpc,bearer=wrongjwt,name='browser_direct_rpc_denied')[0]==403
 status,rows=request('/functions/v1/working-memory-journal',{'op':'entries','space_id':space,'after':0,'through':2},journal=True,name='journal_readback');assert status==200 and len(rows)==2
 status,rows=request('/rest/v1/wm_spaces?id=eq.'+space+'&select=id',bearer=ownerjwt,name='owner_rls');assert status==200 and len(rows)==1
 status,res=request('/auth/v1/health',name='health');assert status==200 and res['version']=='v2.196.0'
 assert sql("SELECT revision::text||':'||(SELECT count(*) FROM public.wm_journal WHERE space_id='"+space+"')::text FROM public.wm_spaces WHERE id='"+space+"'")=='2:2'
 after=aggregate();(RUN/'existing-after-private.json').write_text(json.dumps(after));assert before==after
 evidence.update(status='STAGE_WRITE_FOLLOWUP_PASSED',disposable_space_final_revision=2,disposable_journal_rows=2,other_container_identities_unchanged=True,existing_business_aggregates_unchanged=True)
except Exception as err:evidence.update(failure_type=type(err).__name__,failure_message=str(err))
finally:
 sql("UPDATE memory_private.service_tokens SET enabled=false WHERE token_hash='"+digest+"' AND space_id='"+space+"';")
 evidence['disposable_token_disabled']=True;evidence['compose_sha256']=hashlib.sha256(compose.read_bytes()).hexdigest()
 (RUN/'receipt.json').write_text(json.dumps(evidence,indent=2));(RUN/'hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.iterdir() if p.is_file()},indent=2));print(json.dumps(evidence))
if evidence['status']=='FOLLOWUP_FAILED':raise SystemExit(1)
