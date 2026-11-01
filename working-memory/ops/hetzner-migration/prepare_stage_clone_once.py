"""One private readonly clone from the actual live image, only origin changes."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path('/opt/dashboard-memory-stage-read-20261003');LIVE='dashboard-memory-canonical-draft-canonical-draft-1';os.umask(0o077);resume='--resume-origin-contract' in sys.argv
if not resume:ROOT.mkdir(mode=0o700)
def run(args):
 r=subprocess.run(args,capture_output=True)
 if r.returncode:
  (ROOT/'failure-private.stderr').write_bytes(r.stderr);raise RuntimeError('Clone operation failed '+args[0])
 return r.stdout
live=json.loads(run(['docker','inspect',LIVE]))[0];baseline=live['Image'];assert baseline=='sha256:15a6a820f9d887fac5f0bcd3e2dd29c477d4d5f6a7e82db41bb83cd899f43a2f'
(ROOT/'live-before-private.json').write_text(json.dumps(live,indent=2));build=ROOT/'build'
if not resume:build.mkdir(mode=0o700)
extract='dashboard-memory-stage-extract-20261003'
if not resume:run(['docker','create','--name',extract,baseline])
try:
 if not resume:
  for name in ['access.py','gateway_journal.py']:run(['docker','cp',extract+':/app/'+name,str(build/name)])
finally:
 if not resume:run(['docker','rm',extract])
changes={}
for name in ['access.py','gateway_journal.py']:
 p=build/name;before=p.read_text();(build/(name+'.before')).write_text(before)
 if name=='access.py':
  old="parsed.scheme != 'https' or parsed.hostname != 'lghwikeotbkmojyyjglz.supabase.co' or parsed.path not in ('', '/')"
  new="supabase_url not in ('https://lghwikeotbkmojyyjglz.supabase.co','https://lghwikeotbkmojyyjglz.supabase.co/','https://178-105-167-26.nip.io/supabase','https://178-105-167-26.nip.io/supabase/','http://api-gw:8000')"
 else:
  old="if not re.fullmatch(r'https://[a-z0-9]+\\.supabase\\.co',url) or not re.fullmatch('[0-9a-f]{64}',token):"
  new="if (not re.fullmatch(r'https://[a-z0-9]+\\.supabase\\.co',url) and url not in ('https://178-105-167-26.nip.io/supabase','http://api-gw:8000')) or not re.fullmatch('[0-9a-f]{64}',token):"
 if before.count(old)!=1:raise SystemExit('Actual immutable image origin contract differs: '+name)
 p.write_text(before.replace(old,new));p.chmod(0o644);changes[name]={'before_sha256':hashlib.sha256(before.encode()).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
run(['docker','tag',baseline,'dashboard-canonical-baseline:hz20261003'])
(build/'Dockerfile').write_text('FROM dashboard-canonical-baseline:hz20261003\nCOPY access.py gateway_journal.py /app/\n')
image='dashboard-memory-stage-read:20261003';run(['docker','build','--pull=false','-t',image,str(build)])
baseenv=dict(x.split('=',1) for x in live['Config']['Env']);target={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in Path('/opt/dashboard-supabase-20261003/.private.env').read_text().splitlines() if '=' in l)}
values={k:v for k,v in baseenv.items() if k.startswith('MEMORY_') or k in ['SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY']}
values.update(SUPABASE_URL='http://api-gw:8000',SUPABASE_PUBLISHABLE_KEY=target['ANON_KEY'],MEMORY_READ_ONLY='1',MEMORY_INTAKE_ENABLED='0',MEMORY_AUTOMATIC_ENABLED='0',MEMORY_QA_ENABLED='0',MEMORY_ORIGINAL_DELETION_ENABLED='0',MEMORY_DB='/app/.local/stage-cache.db',MEMORY_CACHE_DIR='/app/.local/cache',MEMORY_QA_OUTBOX='/app/.local/outbox',MEMORY_PROJECTION_CACHE_DIRS='/app/.local/cache',MEMORY_RESTORE_DELETION_LEDGER='',MEMORY_BIND='0.0.0.0')
for k in list(values):
 if any(part in k for part in ['OPENAI','GEMINI','ANTHROPIC','PROVIDER']):del values[k]
with (ROOT/'private.env').open('x') as f:
 for k,v in values.items():
  if '\n' in v or '\r' in v:raise SystemExit('Invalid private environment format')
  f.write(k+'='+v+'\n')
gw=json.loads(run(['docker','inspect','dashboard-supabase-20261003-api-gw-1']))[0]['NetworkSettings']['Networks']['dashboard-supabase-20261003_restore']['IPAddress']
name='dashboard-memory-stage-read-20261003';run(['docker','create','--name',name,'--network','dashboard-supabase-20261003_api-ingress','--ip','172.28.81.3','--add-host','api-gw:'+gw,'--env-file',str(ROOT/'private.env'),'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp','--memory','512m','--cpus','1','--mount','type=volume,source=dashboard-memory-stage-read-20261003-cache,target=/app/.local','-p','127.0.0.1:8799:8791',image])
run(['docker','network','connect','dashboard-supabase-20261003_restore',name]);run(['docker','start',name])
after=json.loads(run(['docker','inspect',LIVE]))[0];assert after['Id']==live['Id'] and after['Image']==baseline
manifest={'base_live_image':baseline,'live_container_id_unchanged':True,'clone_image':json.loads(run(['docker','inspect',name]))[0]['Image'],'origin_only_changes':changes,'clone_url':'http://127.0.0.1:8799','private_target_backend_url':'http://api-gw:8000','future_production_and_host_backup_url':'https://178-105-167-26.nip.io/supabase','intake':False,'automatic':False,'qa':False,'read_only':True,'provider_secrets_forwarded':False,'verification_pending':True}
(ROOT/'build-manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest))
