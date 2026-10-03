"""One complete network verification; no provider jobs or outgoing mail."""
import hashlib,json,os,socket,subprocess,urllib.request,urllib.error
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'network-prepare-1';os.umask(0o077)
if (RUN/'verification.json').exists():raise SystemExit('Network verification already attempted; no automatic retry')
(RUN/'verification.json').write_text(json.dumps({'status':'running','attempt':1}))
env={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if '=' in l)}
def request(path,data=None,bearer=None):
 req=urllib.request.Request('http://127.0.0.1:8800'+path,data=None if data is None else json.dumps(data).encode(),headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+(bearer or env['ANON_KEY']),'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.status,json.load(r)
def save_result(name,result):
 (RUN/(name+'.stdout')).write_bytes(result.stdout);(RUN/(name+'.stderr')).write_bytes(result.stderr);(RUN/(name+'.result.json')).write_text(json.dumps({'returncode':result.returncode},indent=2))
evidence={'verification_attempt':1,'source_mutation':False,'external_emails_sent':0,'public_nginx_changed':False}
try:
 ids=subprocess.check_output(['docker','compose','--env-file','.private.env','ps','-q'],cwd=ROOT,text=True).split()
 containers=json.loads(subprocess.check_output(['docker','inspect',*ids]))
 evidence['healthy_services']=sum(c['State'].get('Health',{}).get('Status')=='healthy' for c in containers);assert evidence['healthy_services']==5
 mapping={c['Config']['Labels']['com.docker.compose.service']:c for c in containers}
 for service in ['db','auth','rest','functions']:
  assert not any(mapping[service]['NetworkSettings']['Ports'].values())
 evidence['db_auth_rest_functions_no_published_ports']=True
 ports=mapping['api-gw']['NetworkSettings']['Ports']['8000/tcp'];assert ports==[{'HostIp':'127.0.0.1','HostPort':'8800'}]
 status,_=request('/auth/v1/health');assert status==200;evidence['actual_loopback_gateway_http']=200
 original=json.loads((ROOT/'migrated-stage-tokens.json').read_text())
 status,tokens=request('/auth/v1/token?grant_type=refresh_token',{'refresh_token':original['refresh_token']});assert status==200 and tokens['user']['id']==original['user']['id']
 (RUN/'owner-refreshed-tokens-private.json').write_text(json.dumps(tokens))
 status,owner=request('/auth/v1/user',bearer=tokens['access_token']);assert status==200 and owner['id']==original['user']['id']
 status,spaces=request('/rest/v1/wm_spaces?select=id',bearer=tokens['access_token']);assert status==200 and len(spaces)>0
 wrong=json.loads((ROOT/'recovery-issued-session-continuation-1/reset-login-private.json').read_text())['tokens']
 status,rows=request('/rest/v1/wm_spaces?select=id',bearer=wrong['access_token']);assert status==200 and rows==[]
 evidence.update(owner_auth_passed=True,owner_spaces_read=len(spaces),wrong_owner_rls_empty=True)
 import access
 resolver=socket.getaddrinfo;socket.getaddrinfo=lambda host,*args,**kw:resolver('127.0.0.1' if host=='api-gw' else host,*args,**kw)
 # The public contract is preserved; host test maps only the private DNS alias/port.
 original_urlopen=access.urllib.request.urlopen
 def stageopen(req,**kwargs):
  req.full_url=req.full_url.replace('http://api-gw:8000','http://127.0.0.1:8800');return original_urlopen(req,**kwargs)
 access.urllib.request.urlopen=stageopen
 assert access.authenticate('Bearer '+tokens['access_token'],service_token='',supabase_url='http://api-gw:8000',publishable_key=env['ANON_KEY'],allowed_users=(owner['id'],))=={'role':'owner','id':owner['id']}
 assert access.authenticate('Bearer '+wrong['access_token'],service_token='',supabase_url='http://api-gw:8000',publishable_key=env['ANON_KEY'],allowed_users=(owner['id'],)) is None
 access.urllib.request.urlopen=original_urlopen;socket.getaddrinfo=resolver;evidence['backend_owner_allow_wrong_owner_deny']=True
 prod=dict(x.split('=',1) for x in json.loads(subprocess.check_output(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]['Config']['Env'])
 req=urllib.request.Request('http://127.0.0.1:8800/functions/v1/working-memory-journal',data=json.dumps({'op':'space','space_id':prod['MEMORY_SPACE_ID']}).encode(),headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+env['ANON_KEY'],'X-Memory-Token':prod['MEMORY_JOURNAL_TOKEN'],'Content-Type':'application/json'})
 with original_urlopen(req,timeout=30) as r:space=json.load(r);assert r.status==200 and space.get('id',space.get('space_id'))==prod['MEMORY_SPACE_ID']
 evidence['scoped_journal_read']=True
 # Actual new Auth network namespace resolver, then verified TLS SMTP AUTH/NOOP.
 image=json.loads(subprocess.check_output(['docker','inspect','n8n']))[0]['Image']
 dns=subprocess.run(['docker','run','--rm','--network','container:dashboard-supabase-20261003-auth-1','--read-only','--entrypoint','node',image,'-e',"require('dns').lookup('smtp.gmail.com',{family:4},(e,a)=>{if(e){console.error(e.code);process.exitCode=1}else console.log(a)})"],capture_output=True,timeout=20);save_result('actual-auth-dns',dns);assert dns.returncode==0
 ip=dns.stdout.decode().strip();__import__('ipaddress').ip_address(ip)
 (RUN/'smtp-connect-ip.json').write_text(json.dumps({'ip':ip}))
 smtpcode="""import json,smtplib,ssl
from pathlib import Path
r=Path('/opt/dashboard-supabase-20261003');e={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (r/'.private.env').read_text().splitlines() if '=' in l)}
ip=json.loads((r/'network-prepare-1/smtp-connect-ip.json').read_text())['ip']
with smtplib.SMTP(timeout=15,local_hostname='dashboard-migration.invalid') as s:
 s.connect(ip,587);s._host='smtp.gmail.com';s.ehlo();s.starttls(context=ssl.create_default_context());s.ehlo();s.login(e['SMTP_USER'],e['SMTP_PASS']);assert s.noop()[0]==250
print('TLS_IDENTITY_AUTH_NOOP_QUIT_PASSED_NO_MAIL')
"""
 (RUN/'smtp-namespace-probe.py').write_text(smtpcode)
 authpid=mapping['auth']['State']['Pid']
 smtp=subprocess.run(['nsenter','-t',str(authpid),'-n','python3',str(RUN/'smtp-namespace-probe.py')],capture_output=True,timeout=50);save_result('actual-auth-smtp',smtp);assert smtp.returncode==0
 evidence.update(actual_auth_namespace_pid=authpid,actual_auth_dns_passed=True,actual_auth_gmail_tls_auth_noop=True)
 # Prove the scoped policy denies Auth HTTP egress, without sending HTTP/provider data.
 denied=subprocess.run(['nsenter','-t',str(authpid),'-n','python3','-c',"import socket; s=socket.socket();s.settimeout(2);r=s.connect_ex(('1.1.1.1',443));print(r);assert r!=0"],capture_output=True,timeout=5);save_result('actual-auth-http-denied',denied);assert denied.returncode==0
 evidence['auth_non_smtp_egress_denied']=True;evidence['status']='NETWORK_VERIFIED'
except Exception as error:
 evidence.update(status='NETWORK_FAILED',failure_type=type(error).__name__,failure_message=str(error) if not isinstance(error,urllib.error.HTTPError) else 'HTTP '+str(error.code))
finally:
 (RUN/'verification.json').write_text(json.dumps(evidence,indent=2));(RUN/'hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.iterdir() if p.is_file()},indent=2))
 for p in RUN.iterdir():p.chmod(0o600)
 print(json.dumps(evidence))
if evidence['status']!='NETWORK_VERIFIED':raise SystemExit(1)
