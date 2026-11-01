"""One owner read integration on immutable live-image clone; no app writes."""
import hashlib,json,os,subprocess,urllib.request,urllib.error
from pathlib import Path
ROOT=Path('/opt/dashboard-memory-stage-read-20261003');TARGET=Path('/opt/dashboard-supabase-20261003');os.umask(0o077)
p=ROOT/'read-verification.json'
if p.exists():raise SystemExit('Initial verification already attempted')
p.write_text('{"status":"running"}')
owner=json.loads((TARGET/'network-prepare-1/owner-refreshed-tokens-private.json').read_text())
wrong=json.loads((TARGET/'recovery-issued-session-continuation-1/reset-login-private.json').read_text())['tokens']
e={'question':'Does the real runtime clone read target journal/archive/review for owner and deny wrong owner without processing?','attempt':1,'provider_calls':0,'app_write_requests':0,'status':'FAILED'}
try:
 c=json.loads(subprocess.check_output(['docker','inspect','dashboard-memory-stage-read-20261003']))[0]
 env=dict(s.split('=',1) for s in c['Config']['Env'])
 for k,v in {'MEMORY_READ_ONLY':'1','MEMORY_INTAKE_ENABLED':'0','MEMORY_AUTOMATIC_ENABLED':'0','MEMORY_QA_ENABLED':'0'}.items():assert env[k]==v
 assert not any(k.startswith(('OPENAI','GEMINI','ANTHROPIC')) for k in env)
 assert c['NetworkSettings']['Ports']['8791/tcp']==[{'HostIp':'127.0.0.1','HostPort':'8799'}]
 e['cases']={}
 for path,token,expected,label in [('/health',None,200,'health'),('/archive',owner['access_token'],200,'owner_archive'),('/review',owner['access_token'],200,'owner_review'),('/overview',owner['access_token'],200,'owner_overview'),('/archive',wrong['access_token'],401,'wrong_owner_archive')]:
  req=urllib.request.Request('http://127.0.0.1:8799'+path,headers={} if token is None else {'Authorization':'Bearer '+token})
  try:
   with urllib.request.urlopen(req,timeout=100) as r:status=r.status;body=r.read()
  except urllib.error.HTTPError as r:status=r.code;body=r.read()
  (ROOT/(label+'-private.json')).write_bytes(body);e['cases'][label]={'http':status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()};assert status==expected
 after=json.loads(subprocess.check_output(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]
 before=json.loads((ROOT/'live-before-private.json').read_text());assert before['Id']==after['Id'] and before['Image']==after['Image']
 e.update(status='OWNER_READ_INTEGRATION_PASSED',live_container_image_unchanged=True,read_only=True,intake=False,automatic=False)
except Exception as err:e['failure_type']=type(err).__name__;e['failure_message']=str(err)
finally:p.write_text(json.dumps(e,indent=2));print(json.dumps(e))
if e['status']=='FAILED':raise SystemExit(1)
