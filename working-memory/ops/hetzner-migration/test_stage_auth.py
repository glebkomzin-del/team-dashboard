"""Stage-only integration; no source Auth mutations or mail delivery."""
import hashlib,json,os,secrets,socket,subprocess,urllib.request,urllib.error,smtplib,ssl
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');os.umask(0o077)
def envparse(path):return {k:v.strip(chr(39)) for k,v in (line.split('=',1) for line in path.read_text().splitlines() if '=' in line and not line.startswith('#'))}
env=envparse(ROOT/'.private.env')
def sql(q):return subprocess.check_output(['docker','exec','dashboard-supabase-20261003-db-1','psql','-XqAt','-v','ON_ERROR_STOP=1','-U','supabase_admin','-d','postgres','-c',q],text=True).strip()
ip=json.loads(subprocess.check_output(['docker','inspect','dashboard-supabase-20261003-api-gw-1']))[0]['NetworkSettings']['Networks']['dashboard-supabase-20261003_restore']['IPAddress']
base='http://'+ip+':8000'
def request(path,data=None,key=None,bearer=None):
 req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'apikey':key or env['ANON_KEY'],'Authorization':'Bearer '+(bearer or key or env['ANON_KEY']),'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=35) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:
  value=e.read();(ROOT/'auth-test-last-private-error.json').write_bytes(value);return e.code,{}
owner=sql('select id from auth.users limit 1')
refresh=sql('select token from auth.refresh_tokens where not revoked order by id desc limit 1')
status,value=request('/auth/v1/token?grant_type=refresh_token',{'refresh_token':refresh})
evidence={'migrated_refresh_http':status,'migrated_owner_same':value.get('user',{}).get('id')==owner}
if status!=200 or not evidence['migrated_owner_same']:raise SystemExit('Migrated session refresh failed; private details retained')
(ROOT/'migrated-stage-tokens.json').write_text(json.dumps(value))
password=secrets.token_urlsafe(24);email='migration-test-'+secrets.token_hex(5)+'@migration.invalid'
status,testuser=request('/auth/v1/admin/users',{'email':email,'password':password,'email_confirm':True},key=env['SERVICE_ROLE_KEY'])
if status not in (200,201):raise SystemExit('Stage-only admin test-user creation failed')
status,testlogin=request('/auth/v1/token?grant_type=password',{'email':email,'password':password})
if status!=200:raise SystemExit('Stage-only test login failed')
(ROOT/'test-user.json').write_text(json.dumps({'id':testuser['id'],'email':email,'password':password,'tokens':testlogin}))
status,rows=request('/rest/v1/wm_spaces?select=id',bearer=testlogin['access_token'])
evidence.update(synthetic_password_login=True,wrong_owner_rls_http=status,wrong_owner_rows=len(rows) if isinstance(rows,list) else None)
assert status==200 and rows==[]
# Actual backend Auth helper, only DNS mapped to this isolated target.
import access
original=socket.getaddrinfo
socket.getaddrinfo=lambda host,*a,**k:original(ip if host=='api-gw' else host,*a,**k)
assert access.authenticate('Bearer '+value['access_token'],service_token='',supabase_url='http://api-gw:8000',publishable_key=env['ANON_KEY'],allowed_users=(owner,))=={'role':'owner','id':owner}
assert access.authenticate('Bearer '+testlogin['access_token'],service_token='',supabase_url='http://api-gw:8000',publishable_key=env['ANON_KEY'],allowed_users=(owner,)) is None
evidence.update(backend_owner_allowed=True,backend_wrong_owner_denied=True)
socket.getaddrinfo=original
# Journal exact scoped server token; read-only space operation only.
prod=json.loads(subprocess.check_output(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]['Config']['Env'];prod=dict(x.split('=',1) for x in prod)
req=urllib.request.Request(base+'/functions/v1/working-memory-journal',data=json.dumps({'op':'space','space_id':prod['MEMORY_SPACE_ID']}).encode(),headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+env['ANON_KEY'],'X-Memory-Token':prod['MEMORY_JOURNAL_TOKEN'],'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=40) as r:space=json.load(r);assert r.status==200
evidence['edge_scoped_space_read']=space.get('id',space.get('space_id'))==prod['MEMORY_SPACE_ID']
# TLS authentication only, never MAIL/RCPT/DATA.
with smtplib.SMTP('smtp.gmail.com',587,timeout=20) as smtp:
 smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo();smtp.login(env['SMTP_USER'],env['SMTP_PASS']);code,_=smtp.noop();assert code==250
evidence['smtp_tls_auth_noop']=True;evidence['smtp_emails_sent']=0
(ROOT/'auth-integration-evidence.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))
