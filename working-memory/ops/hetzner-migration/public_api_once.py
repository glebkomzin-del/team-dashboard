"""One guarded public-stage route deployment and read verification."""
import base64,hashlib,json,os,subprocess,urllib.request,urllib.error
from pathlib import Path
BASE=Path(__file__).resolve().parents[2];R=BASE/'.local/hetzner-migration-20261003/public-api-1';R.mkdir(mode=0o700);os.umask(0o077)
SSH=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@178.105.167.26']
def remote(code):return subprocess.run(SSH+['python3 -'],input=code.encode(),capture_output=True,check=True).stdout
query="SELECT jsonb_build_object('spaces',(SELECT jsonb_agg(jsonb_build_object('id',id,'revision',revision,'archive_revision',archive_revision) ORDER BY id) FROM public.wm_spaces),'jobs',(SELECT jsonb_agg(x ORDER BY x->>'state') FROM (SELECT jsonb_build_object('state',COALESCE(to_jsonb(j)->>'state',to_jsonb(j)->>'status'),'count',count(*)) x FROM public.wm_jobs j GROUP BY COALESCE(to_jsonb(j)->>'state',to_jsonb(j)->>'status')) s)) AS aggregate"
token=subprocess.run(['/usr/bin/security','find-generic-password','-s','Supabase CLI','-a','supabase','-w'],capture_output=True,text=True,check=True).stdout.strip()
if token.startswith('go-keyring-base64:'):token=base64.b64decode(token.split(':',1)[1]).decode()
def source():
 req=urllib.request.Request('https://api.supabase.com/v1/projects/lghwikeotbkmojyyjglz/database/query',data=json.dumps({'query':query}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as s:return json.load(s)
def target():return json.loads(remote("import subprocess,json\nprint(subprocess.check_output(['docker','exec','dashboard-supabase-20261003-db-1','psql','-U','postgres','-d','postgres','-tAc',"+repr(query)+"],text=True))"))
before={'source':source(),'target':target()};(R/'before-private.json').write_text(json.dumps(before,indent=2))
original=subprocess.check_output(SSH+['cat','/etc/nginx/sites-available/alexa']);assert hashlib.sha256(original).hexdigest()=='bed7ff8f2bb5cb78ffddf4744c3eefb2fed28476a1d783b7b184bcae8e2ad497'
(R/'nginx-original.conf').write_bytes(original)
off=Path('/Users/glebkomzin/Library/Application Support/Dashboard Job Backup/hetzner-migration-20261003/public-api-1');off.mkdir(mode=0o700)
(off/'nginx-original.conf').write_bytes(original);(off/'nginx-original.conf').chmod(0o600)
snippet=(Path(__file__).parent/'nginx-location.conf').read_bytes();assert hashlib.sha256(snippet).hexdigest()=='13d29ef97ccd84ad8d31f850e8d28e250457b445192045fbefb91e529bea453d'
marker=b'    # Neuer Skill-Service';assert original.count(marker)==1 and b'location /supabase/' not in original
updated=original.replace(marker,b'    '+snippet.replace(b'\n',b'\n    ').rstrip()+b'\n\n'+marker)
(R/'nginx-updated.conf').write_bytes(updated)
code="""import hashlib,subprocess,os,json
from pathlib import Path
os.umask(0o077);r=Path('/opt/dashboard-supabase-20261003/public-api-1');r.mkdir(mode=0o700);p=Path('/etc/nginx/sites-available/alexa');old=p.read_bytes();assert hashlib.sha256(old).hexdigest()=='bed7ff8f2bb5cb78ffddf4744c3eefb2fed28476a1d783b7b184bcae8e2ad497';(r/'nginx-original.conf').write_bytes(old)
p.write_bytes(UPDATED)
t=subprocess.run(['nginx','-t'],capture_output=True);(r/'nginx-test.stdout').write_bytes(t.stdout);(r/'nginx-test.stderr').write_bytes(t.stderr)
if t.returncode:p.write_bytes(old);raise SystemExit('nginx-t failed; original restored')
s=subprocess.run(['systemctl','reload','nginx'],capture_output=True);(r/'nginx-reload.stderr').write_bytes(s.stderr)
print(json.dumps({'nginx_t':t.returncode,'reload':s.returncode,'updated_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
if s.returncode:raise SystemExit(1)
""".replace('UPDATED',repr(updated))
receipt={'question':'Public stage preserves auth/RLS/scoped journal/retired API and existing routes without writers','attempt':1,'deployment':json.loads(remote(code)),'app_write_requests':0,'provider_calls':0,'smtp_messages':0,'cases':{}}
try:
 private=json.loads(remote("import json\nfrom pathlib import Path\nr=Path('/opt/dashboard-supabase-20261003');e={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (r/'.private.env').read_text().splitlines() if '=' in l)};owner=json.loads((r/'network-prepare-1/owner-refreshed-tokens-private.json').read_text());wrong=json.loads((r/'recovery-issued-session-continuation-1/reset-login-private.json').read_text())['tokens'];live=json.loads(__import__('subprocess').check_output(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0];le=dict(x.split('=',1) for x in live['Config']['Env']);print(json.dumps({'anon':e['ANON_KEY'],'owner':owner,'wrong':wrong,'journal':le['MEMORY_JOURNAL_TOKEN'],'space':le['MEMORY_SPACE_ID'],'slugs':[x['slug'] for x in json.loads((r/'functions-export/manifest.json').read_text())]}))"))
 def get(path,expected,bearer=None,data=None,journal=False,label=None):
  h={'apikey':private['anon'],'Authorization':'Bearer '+(bearer or private['anon'])}
  if journal:h['X-Memory-Token']=private['journal'];h['Content-Type']='application/json'
  req=urllib.request.Request('https://178-105-167-26.nip.io'+path,headers=h,data=None if data is None else json.dumps(data).encode())
  try:
   with urllib.request.urlopen(req,timeout=50) as s:status=s.status;body=s.read();headers=dict(s.headers)
  except urllib.error.HTTPError as s:status=s.code;body=s.read();headers=dict(s.headers)
  name=label or path.replace('/','_').replace('?','_');(R/(name+'-body-private')).write_bytes(body);(R/(name+'-headers-private.json')).write_text(json.dumps(headers));receipt['cases'][name]={'http':status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()};assert status==expected,(name,status,expected);return body
 health=json.loads(get('/supabase/auth/v1/health',200,label='auth_health'));assert health.get('version');receipt['auth_version']=health['version']
 owner=json.loads(get('/supabase/auth/v1/user',200,bearer=private['owner']['access_token'],label='owner_auth'));assert owner['id']==private['owner']['user']['id']
 assert json.loads(get('/supabase/rest/v1/wm_spaces?select=id',200,bearer=private['owner']['access_token'],label='owner_rest'))
 assert json.loads(get('/supabase/rest/v1/wm_spaces?select=id',200,bearer=private['wrong']['access_token'],label='wrong_rls'))==[]
 get('/supabase/functions/v1/working-memory-journal',200,data={'op':'space','space_id':private['space']},journal=True,label='journal_read')
 for slug in private['slugs']:
  if slug!='working-memory-journal':get('/supabase/functions/v1/'+slug,410,label='retired_'+slug)
 for path,status,label in [('/healthz',200,'n8n'),('/dashboard-memory/health',200,'dashboard'),('/dashboard-memory-draft/health',200,'draft'),('/dashboard-memory-info/',200,'info')]:get(path,status,label=label)
 # Picnic health has no side effects; exact existing internal service route.
 receipt['picnic_health']=json.loads(remote("import urllib.request,json\nwith urllib.request.urlopen('http://127.0.0.1:3100/health',timeout=10) as s:print(json.dumps({'http':s.status}))"));assert receipt['picnic_health']['http']==200
 after={'source':source(),'target':target()};(R/'after-private.json').write_text(json.dumps(after,indent=2));receipt['source_aggregate_unchanged']=before['source']==after['source'];receipt['target_aggregate_unchanged']=before['target']==after['target'];assert receipt['source_aggregate_unchanged'] and receipt['target_aggregate_unchanged'];receipt['status']='PUBLIC_STAGE_API_VERIFIED'
except Exception as err:receipt.update(status='FAILED',failure_type=type(err).__name__,failure_message=str(err))
(R/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
for p in R.iterdir():p.chmod(0o600)
__import__('shutil').copytree(R,off,dirs_exist_ok=True)
if receipt['status']=='FAILED':raise SystemExit(1)
