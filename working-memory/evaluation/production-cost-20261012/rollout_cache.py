import pathlib,json,hashlib,subprocess,os,time,urllib.request,fcntl,datetime,shutil
ROOT=pathlib.Path('/opt/dashboard-memory-canonical-draft');OUT=ROOT/'.local/recovery/production-cost-20261012/cache-rollout';STAGE=ROOT/'.local/recovery/production-cost-20261012/cache-candidate'
SPACE='96a2dc44-9b9e-4644-b236-c5c1956cd39d';OLD='v11:compact1:gate1:gpt-6.1-sol:887ca68d3c013fe8:canonical1:42317499c5d8a62a';NEW='v11:compact1:gate1:gpt-6.1-sol:753caadf3fb8fea4:canonical1:023a8c7cae48980c';IMAGE='sha256:9f3d69222e0602327d73fe1665e47da05661938575b6a8204ab4cd5d468f85c2';OLD_IMAGE='sha256:c1e9956d5562bdc475b95f0654877bbb5a21bdd885229dbe1682ade8b37ab76e'
NAME='dashboard-memory-canonical-draft-canonical-draft-1'
def run(args,**kwargs):
 r=subprocess.run(args,capture_output=True,timeout=90,**kwargs)
 if r.returncode:raise RuntimeError('Command failed:'+args[0]+':exit'+str(r.returncode))
 return r.stdout

def sql(body):return run(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-U','postgres','-d','postgres','-X','-qAt','-v','ON_ERROR_STOP=1'],input=body.encode()).decode().strip()
def inspect():return json.loads(run(['docker','inspect',NAME]))[0]
def immutable(runtime):
 config=runtime['Config'].copy();config.pop('Image',None)
 env=config.get('Env')
 if not isinstance(env,list) or any(not isinstance(v,str) or '=' not in v or not v.split('=',1)[0] for v in env):raise RuntimeError('Unknown environment representation')
 names=[v.split('=',1)[0] for v in env]
 if len(set(names))!=len(names):raise RuntimeError('Duplicate environment names; effective values unknown')
 config['Env']=sorted(env)
 if config.get('Hostname')==runtime['Id'][:12]:config['Hostname']='<docker-generated-id>'
 labels=dict(config.get('Labels') or {})
 for key in ('com.docker.compose.config-hash','com.docker.compose.image'):labels.pop(key,None)
 config['Labels']=labels
 host=runtime['HostConfig'].copy()
 mounts=[{k:m[k] for k in ['Type','Source','Destination','Mode','RW','Propagation']} for m in runtime['Mounts']]
 return {'config':config,'host':host,'mounts':mounts,'networks':sorted(runtime['NetworkSettings']['Networks'])}
def pipeline():return run(['docker','exec',NAME,'python','-c','from canonical_worker import pipeline_version;from openai_provider import MODEL;print(pipeline_version(MODEL))']).decode().strip()
def data():
 return json.loads(sql("select jsonb_build_object('revision',(select revision from wm_spaces where id='"+SPACE+"'),'archive_revision',(select archive_revision from wm_spaces where id='"+SPACE+"'),'journal_rows',(select count(*) from wm_journal where space_id='"+SPACE+"'),'sources',(select count(*) from wm_source_versions where space_id='"+SPACE+"'),'documents',(select count(*) from wm_archive_documents where space_id='"+SPACE+"'),'calls',(select count(*) from wm_model_calls where space_id='"+SPACE+"'),'calls_digest',(select md5(string_agg(job_id||':'||call_index::text||':'||request_hash||':'||coalesce(response_hash,'')||':'||coalesce(actual_micro_usd::text,'NULL')||':'||reserved_micro_usd::text,'|' order by job_id,call_index)) from wm_model_calls where space_id='"+SPACE+"'));"))
OUT.mkdir(mode=0o700,parents=True,exist_ok=True)
with open('/run/lock/dashboard-job-backup.lock','a') as backup_lock:
 fcntl.flock(backup_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if subprocess.check_output(['systemctl','show','dashboard-job-backup.service','-p','ActiveState','--value'],text=True).strip() not in ('inactive','failed'):raise RuntimeError('Full backup is active; no code changes')
 backup=json.loads((ROOT/'.local/cache/backup-status.json').read_text())
 if backup.get('state')!='ok' or not backup.get('selfhost',{}).get('restore_verified') or not backup.get('n8n',{}).get('credential_decryption_verified'):raise RuntimeError('Fresh full restored backup required')
 if not backup.get('archive','').startswith('dashboard-20261012'):raise RuntimeError('Todays full backup required')
 before=inspect()
 if before['Image']!=OLD_IMAGE or pipeline()!=OLD:raise RuntimeError('Production version drift')
 candidate=json.loads(run(['docker','image','inspect','dashboard-memory:cache-explicit-20261012']))[0]
 if candidate['Id']!=IMAGE:raise RuntimeError('Candidate image drift')
 sources=json.loads((STAGE/'source-deltas.json').read_text())
 for name,delta in sources.items():
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=delta['before'] or hashlib.sha256((STAGE/name).read_bytes()).hexdigest()!=delta['after']:raise RuntimeError('Source drift:'+name)
 oldcompose=(ROOT/'compose.yaml').read_bytes();oldmanifest=(ROOT/'build-manifest.json').read_bytes()
 if oldcompose.count(b'image: dashboard-memory:combined-p4-cap-backup-20261007-61be51be')!=1:raise RuntimeError('Compose mismatch')
 (OUT/'runtime-before.private.json').write_text(json.dumps(before));(OUT/'runtime-before.private.json').chmod(0o600)
 (OUT/'compose.yaml.before').write_bytes(oldcompose);(OUT/'build-manifest.json.before').write_bytes(oldmanifest)
 for name in sources:shutil.copy2(ROOT/name,OUT/(name+'.before'))
 others={x['Name']:{'id':x['Id'],'image':x['Image'],'started':x['State']['StartedAt']} for x in json.loads(run(['docker','inspect',*run(['docker','ps','-q']).decode().split()])) if x['Name']!=before['Name']}
 (OUT/'other-containers-before.json').write_text(json.dumps(others))
 # Pause atomically only when all current request outcomes are received and no jobs pending.
 sql("begin; do $$begin if not exists(select 1 from wm_processing_config where space_id='"+SPACE+"' and enabled and pipeline='"+OLD+"') or exists(select 1 from wm_jobs where space_id='"+SPACE+"' and state not in ('applied','archived')) or exists(select 1 from wm_model_calls where space_id='"+SPACE+"' and received_at is null) or exists(select 1 from wm_question_calls where space_id='"+SPACE+"' and received_at is null) then raise exception 'Live pipeline not quiescent';end if;end$$;update wm_processing_config set enabled=false where space_id='"+SPACE+"' and pipeline='"+OLD+"';commit;")
 baseline=data();(OUT/'data-before.json').write_text(json.dumps(baseline))
 installed=False
 try:
  manifest=json.loads(oldmanifest)
  for name,delta in sources.items():
   tmp=ROOT/(name+'.cache-new');tmp.write_bytes((STAGE/name).read_bytes());os.chmod(tmp,(ROOT/name).stat().st_mode & 0o777);os.replace(tmp,ROOT/name);manifest[name]=delta['after']
  mp=ROOT/'build-manifest.json.cache-new';mp.write_text(json.dumps(manifest,indent=2));mp.chmod(0o600);os.replace(mp,ROOT/'build-manifest.json')
  newcompose=oldcompose.replace(b'image: dashboard-memory:combined-p4-cap-backup-20261007-61be51be',b'image: dashboard-memory:cache-explicit-20261012');cp=ROOT/'compose.yaml.cache-new';cp.write_bytes(newcompose);cp.chmod(0o600);os.replace(cp,ROOT/'compose.yaml')
  log=run(['docker','compose','-f',str(ROOT/'compose.yaml'),'up','-d','--no-deps','--no-build','--pull','never','canonical-draft'],cwd=ROOT);(OUT/'compose.stdout').write_bytes(log)
  for n in range(60):
   try:
    with urllib.request.urlopen('http://127.0.0.1:8798/health',timeout=3) as response:healthy=response.status==200
    if healthy:break
   except Exception:pass
   time.sleep(1)
  else:raise RuntimeError('Candidate health unavailable')
  after=inspect()
  if after['Image']!=IMAGE or pipeline()!=NEW or immutable(after)!=immutable(before):raise RuntimeError('Actual runtime configuration or pipeline changed unexpectedly')
  if data()!=baseline:raise RuntimeError('Data changed during backend switch')
  currentothers={x['Name']:{'id':x['Id'],'image':x['Image'],'started':x['State']['StartedAt']} for x in json.loads(run(['docker','inspect',*run(['docker','ps','-q']).decode().split()])) if x['Name']!=after['Name']}
  if currentothers!=others:raise RuntimeError('Other production containers changed')
  sql("begin;do $$begin if not exists(select 1 from wm_processing_config where space_id='"+SPACE+"' and not enabled and pipeline='"+OLD+"') then raise exception 'Config changed during rollout';end if;end$$;update wm_processing_config set pipeline='"+NEW+"',enabled=true where space_id='"+SPACE+"' and pipeline='"+OLD+"' and not enabled;commit;")
  installed=True;receipt={'installed':True,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'image':IMAGE,'pipeline':NEW,'original_runtime_settings_equal':True,'original_data_and_calls_equal':True,'other_production_containers_equal':True,'processing_enabled':True,'sources':sources,'backup_before':{'archive':backup['archive'],'sha256':backup['sha256']},'new_paid_test_calls':0,'rollback':str(OUT)}
  (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
 finally:
  if not installed:
   for name in sources:shutil.copy2(OUT/(name+'.before'),ROOT/name)
   (ROOT/'build-manifest.json').write_bytes(oldmanifest);(ROOT/'compose.yaml').write_bytes(oldcompose)
   run(['docker','compose','-f',str(ROOT/'compose.yaml'),'up','-d','--no-deps','--no-build','--pull','never','canonical-draft'],cwd=ROOT)
   for n in range(60):
    try:
     with urllib.request.urlopen('http://127.0.0.1:8798/health',timeout=3) as response:
      if response.status==200:break
    except Exception:pass
    time.sleep(1)
   if pipeline()!=OLD:raise RuntimeError('Rollback pipeline not confirmed; processing remains paused')
   sql("update wm_processing_config set pipeline='"+OLD+"',enabled=true where space_id='"+SPACE+"' and not enabled and pipeline in ('"+OLD+"','"+NEW+"');")
   (OUT/'rollback.json').write_text(json.dumps({'old_pipeline_restored':True,'processing_enabled':True,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
