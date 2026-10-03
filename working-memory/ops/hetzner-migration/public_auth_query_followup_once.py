"""New user-authorized bounded recovery cycle; historical attempts retained."""
import email,hashlib,html,json,os,re,secrets,subprocess,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'public-auth-query-1';os.umask(0o077)
RUN.mkdir(mode=0o700) # Immutable attempt boundary; refuse any repeat.
env={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if '=' in l)}
user=json.loads((ROOT/'test-user.json').read_text());assert user['email'].endswith('.invalid')
network='dashboard-supabase-20261003_restore';name='dashboard-migration-mailcapture-public-auth-query-1'
image=json.loads(subprocess.check_output(['docker','inspect','n8n']))[0]['Image']
ip=json.loads(subprocess.check_output(['docker','inspect','dashboard-supabase-20261003-api-gw-1']))[0]['NetworkSettings']['Networks'][network]['IPAddress'];base='https://178-105-167-26.nip.io/supabase'
capture=r'''const net=require('net'),fs=require('fs');let messages=0;net.createServer(s=>{let buf='',data=false,body=[];s.on('error',e=>fs.appendFileSync('/capture/socket-errors.log',String(e.code)+'\n'));s.write('220 local-capture ESMTP\r\n');s.on('data',chunk=>{buf+=chunk;while(buf.includes('\n')){let i=buf.indexOf('\n'),line=buf.slice(0,i+1);buf=buf.slice(i+1);if(data){if(line==='\.\r\n'){data=false;fs.writeFileSync('/capture/message.eml',body.join(''));messages++;s.write('250 stored locally\r\n');}else body.push(line);continue;}let cmd=line.trim().toUpperCase();fs.appendFileSync('/capture/protocol-verbs.log',cmd.split(' ')[0]+'\n');if(cmd.startsWith('EHLO')||cmd.startsWith('HELO'))s.write('250-local-capture\r\n250 8BITMIME\r\n');else if(cmd.startsWith('RCPT')&&!cmd.includes('.INVALID'))s.write('550 Only invalid domains\r\n');else if(cmd==='DATA'){body=[];data=true;s.write('354 End with dot\r\n');}else if(cmd==='QUIT'){s.end('221 Bye\r\n');}else s.write('250 OK\r\n');}});}).listen(1025,'0.0.0.0');'''
(RUN/'capture.js').write_text(capture)
override=RUN/'smtp.override.yaml';override.write_text('services:\n  auth:\n    environment:\n      GOTRUE_SMTP_HOST: '+name+'\n      GOTRUE_SMTP_PORT: 1025\n      GOTRUE_SMTP_USER: ""\n      GOTRUE_SMTP_PASS: ""\n      GOTRUE_SMTP_ADMIN_EMAIL: migration@migration.invalid\n      GOTRUE_URI_ALLOW_LIST: http://localhost:8943/?recovery=1\n')
def compose(test=False):
 args=['docker','compose','--env-file','.private.env','-f','compose.yaml']
 if test:args+=['-f',str(override)]
 result=subprocess.run(args+['up','-d','--force-recreate','--no-deps','--wait','--wait-timeout','60','auth'],cwd=ROOT,capture_output=True)
 if result.returncode:raise RuntimeError('Auth configuration switch failed')
def request(path,data,token=None,method=None):
 req=urllib.request.Request(base+path,data=json.dumps(data).encode(),method=method,headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+(token or env['ANON_KEY']),'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
evidence={"problem_id":"HZ-MIGRATION-20261003-PUBLIC-AUTH","cycle":1,"prior_public_auth_failed":1,"review_authorized_query_followup":1,"smtp_external_messages":0,"source_mutation":False}
capture_started=False;auth_changed=False
try:
 subprocess.run(['docker','run','-d','--name',name,'--network',network,'--read-only','--user','0','--memory','128m','--cpus','.25','-v',str(RUN)+':/capture','--entrypoint','node',image,'/capture/capture.js'],check=True,capture_output=True);capture_started=True
 capture_ip=json.loads(subprocess.check_output(['docker','inspect',name]))[0]['NetworkSettings']['Networks'][network]['IPAddress']
 # Fixed private address addresses the observed Go resolver failure, without egress.
 override.write_text(override.read_text().replace(name,capture_ip))
 auth_changed=True;compose(True);time.sleep(6)
 evidence['probe_after_auth_recreation']=True
 # Actual new Auth network namespace: no host INPUT path, no new network access.
 probe="const net=require('net');let v='',stage=0,ok=false;const s=net.connect(1025,'"+capture_ip+"');s.setTimeout(5000,()=>{process.exitCode=2;s.destroy()});s.on('data',b=>{v+=b;while(v.includes('\\n')){const i=v.indexOf('\\n'),line=v.slice(0,i).trim();v=v.slice(i+1);if(stage===0&&line.startsWith('220 ')){stage=1;s.write('EHLO isolated-auth.invalid\\r\\n')}else if(stage===1&&line.startsWith('250 ')){stage=2;s.write('QUIT\\r\\n')}else if(stage===2&&line.startsWith('221 ')){ok=true;s.end()}}});s.on('error',()=>{process.exitCode=3;s.destroy()});s.on('close',()=>{if(!ok)process.exitCode=process.exitCode||4});"
 checked=subprocess.run(['docker','run','--rm','--network','container:dashboard-supabase-20261003-auth-1','--read-only','--memory','128m','--cpus','.25','--entrypoint','node',image,'-e',probe],capture_output=True,timeout=15)
 (RUN/'node-probe.stdout').write_bytes(checked.stdout);(RUN/'node-probe.stderr').write_bytes(checked.stderr)
 evidence['node_probe_returncode']=checked.returncode
 evidence['smtp_greeting_ehlo_from_auth_net']=checked.returncode==0
 evidence['capture_fixed_private_ip']=capture_ip
 if checked.returncode:raise RuntimeError('SMTP prerequisite failed')
 actual=json.loads(subprocess.check_output(['docker','inspect','dashboard-supabase-20261003-auth-1']))[0]
 actual_env=dict(x.split('=',1) for x in actual['Config']['Env'])
 assert actual_env.get('GOTRUE_URI_ALLOW_LIST')=='http://localhost:8943/?recovery=1'
 evidence['effective_allowlist_exact']=True
 evidence['actual_smtp_host_matches_capture']=actual_env.get('GOTRUE_SMTP_HOST')==capture_ip
 evidence['actual_smtp_port']=actual_env.get('GOTRUE_SMTP_PORT')
 assert evidence['actual_smtp_host_matches_capture'] and evidence['actual_smtp_port']=='1025'
 before=json.loads(subprocess.check_output(['docker','inspect',name]))[0]['State']
 (RUN/'capture-before-native.json').write_text(json.dumps(before,indent=2))
 assert before['Running'] and before['ExitCode']==0
 smtpcheck="import smtplib; c=smtplib.SMTP('"+capture_ip+"',1025,local_hostname='namespace.invalid',timeout=5);r=c.ehlo();print('EHLO_STATUS='+str(r[0]));assert r[0]==250;r=c.quit();print('QUIT_STATUS='+str(r[0]));assert r[0]==221"
 native=subprocess.run(['nsenter','-t',str(actual['State']['Pid']),'-n','python3','-c',smtpcheck],capture_output=True,timeout=15)
 (RUN/'native-probe.stdout').write_bytes(native.stdout);(RUN/'native-probe.stderr').write_bytes(native.stderr)
 evidence['native_probe_returncode']=native.returncode
 evidence['native_smtp_dialog_after_recreation']=native.returncode==0
 if native.returncode:raise RuntimeError('Native SMTP prerequisite failed')
 after=json.loads(subprocess.check_output(['docker','inspect',name]))[0]['State']
 (RUN/'capture-after-native.json').write_text(json.dumps(after,indent=2))
 evidence['capture_alive_same_pid_after_probes']=after['Running'] and after['Pid']==before['Pid'] and after['ExitCode']==0
 assert evidence['capture_alive_same_pid_after_probes']
 request('/auth/v1/recover?redirect_to='+urllib.parse.quote('http://localhost:8943/?recovery=1',safe=''),{'email':user['email']})
 evidence['recover_http']=200
 for _ in range(20):
  if (RUN/'message.eml').exists():break
  time.sleep(.25)
 if not (RUN/'message.eml').exists():raise RuntimeError('No captured recovery message')
 message=email.message_from_bytes((RUN/'message.eml').read_bytes());parts=[]
 for part in message.walk():
  if part.get_content_maintype()=='text':parts.append(part.get_payload(decode=True).decode())
 links=re.findall(r'https?://[^\s<>"\']+',html.unescape('\n'.join(parts)))
 link=next(x for x in links if 'token=' in x or 'token_hash=' in x)
 expected='https://178-105-167-26.nip.io/supabase/auth/v1/verify'
 evidence['captured_link_correct_prefix']=link.startswith(expected+'?')
 if not evidence['captured_link_correct_prefix']:raise RuntimeError('Incorrect recovery external URL contract')
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args):return None
 try:urllib.request.build_opener(NoRedirect()).open(link,timeout=25);raise RuntimeError('No redirect')
 except urllib.error.HTTPError as response:
  headers=dict(response.headers);(RUN/'verify-headers-private.json').write_text(json.dumps(headers,indent=2));assert response.code==303
  location=response.headers['Location'];(RUN/'callback-private.txt').write_text(location)
 assert location.startswith('http://localhost:8943/?recovery=1#')
 access=urllib.parse.parse_qs(urllib.parse.urlsplit(location).fragment).get('access_token',[''])[0];assert access
 (RUN/'access-private.txt').write_text(access)
 evidence.update(status='CALLBACK_READY',verify_http=303,location_headers_preserved=True)
except Exception as error:evidence.update(status='FAILED',failure_type=type(error).__name__,failure_message=str(error) if not isinstance(error,urllib.error.HTTPError) else 'HTTP '+str(error.code))
finally:
 (RUN/'part1-receipt.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))
if evidence['status']=='FAILED':
 compose(False);subprocess.run(['docker','rm','-f',name],capture_output=True);raise SystemExit(1)
