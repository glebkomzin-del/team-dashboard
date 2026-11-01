"""Only source-retired410 contracts and rejected Journal requests, never AI."""
import json,os,subprocess,urllib.request,urllib.error
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');os.umask(0o077)
env={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if '=' in l)}
ip=json.loads(subprocess.check_output(['docker','inspect','dashboard-supabase-20261003-api-gw-1']))[0]['NetworkSettings']['Networks']['dashboard-supabase-20261003_restore']['IPAddress'];base='http://'+ip+':8000'
manifest=json.loads((ROOT/'functions-export/manifest.json').read_text());result=[]
for item in manifest:
 slug=item['slug'];headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+env['ANON_KEY'],'Content-Type':'application/json'}
 if slug=='working-memory-journal':headers['X-Memory-Token']='0'*64
 req=urllib.request.Request(base+'/functions/v1/'+slug,headers=headers,data=b'{"op":"space"}')
 try:
  with urllib.request.urlopen(req,timeout=20) as response:code=response.status;body=response.read()
 except urllib.error.HTTPError as response:code=response.code;body=response.read()
 expected=401 if slug=='working-memory-journal' else 410
 if code!=expected:
  (ROOT/'edge-test-private-error').write_bytes(body);raise SystemExit('Edge contract failed '+slug+' status '+str(code))
 result.append({'slug':slug,'status':code,'expected':expected})
(ROOT/'edge-contract-test.json').write_text(json.dumps({'functions':result,'provider_calls':0},indent=2));print(json.dumps({'functions_checked':len(result),'all_expected_statuses':True,'provider_calls':0}))
