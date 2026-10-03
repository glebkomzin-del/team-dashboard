"""Local mail capture and real target reset flow; never sends external mail."""
import email,html,json,os,re,secrets,socketserver,subprocess,threading,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');os.umask(0o077)
env={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if '=' in l)}
user=json.loads((ROOT/'test-user.json').read_text());assert user['email'].endswith('.invalid')
container=json.loads(subprocess.check_output(['docker','inspect','dashboard-supabase-20261003-api-gw-1']))[0]
ip=container['NetworkSettings']['Networks']['dashboard-supabase-20261003_restore']['IPAddress'];base='http://'+ip+':8000';messages=[]
class SMTP(socketserver.StreamRequestHandler):
 def handle(self):
  self.wfile.write(b'220 local-capture ESMTP\r\n')
  while line:=self.rfile.readline():
   command=line.decode().strip().upper()
   if command.startswith(('EHLO','HELO')):self.wfile.write(b'250-local-capture\r\n250 8BITMIME\r\n')
   elif command.startswith('DATA'):
    self.wfile.write(b'354 End with dot\r\n');body=[]
    while (line:=self.rfile.readline())!=b'.\r\n':body.append(line)
    messages.append(b''.join(body));self.wfile.write(b'250 accepted locally\r\n')
   elif command.startswith('QUIT'):self.wfile.write(b'221 Bye\r\n');break
   else:self.wfile.write(b'250 OK\r\n')
server=socketserver.ThreadingTCPServer(('172.22.0.1',1025),SMTP);threading.Thread(target=server.serve_forever,daemon=True).start()
override=ROOT/'recovery-test.override.yaml';override.write_text('services:\n  auth:\n    environment:\n      GOTRUE_SMTP_HOST: 172.22.0.1\n      GOTRUE_SMTP_PORT: 1025\n      GOTRUE_SMTP_USER: ""\n      GOTRUE_SMTP_PASS: ""\n      GOTRUE_SMTP_ADMIN_EMAIL: migration@migration.invalid\n')
def compose(test=False):
 args=['docker','compose','--env-file','.private.env','-f','compose.yaml']
 if test:args+=['-f',override.name]
 subprocess.run(args+['up','-d','--force-recreate','--no-deps','--wait','--wait-timeout','60','auth'],cwd=ROOT,check=True,capture_output=True)
def request(path,data,token=None,method=None):
 req=urllib.request.Request(base+path,data=json.dumps(data).encode(),method=method,headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+(token or env['ANON_KEY']),'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
try:
 compose(True)
 time.sleep(6)
 request('/auth/v1/recover',{'email':user['email'],'redirect_to':'https://team-dashboard-rho.vercel.app/'})
 for _ in range(20):
  if messages:break
  time.sleep(.25)
 if len(messages)!=1:raise RuntimeError('Expected one local recovery mail')
 message=email.message_from_bytes(messages[0]);texts=[]
 for part in message.walk():
  if part.get_content_maintype()=='text':texts.append(part.get_payload(decode=True).decode())
 text=html.unescape('\n'.join(texts));links=re.findall(r'https?://[^\s<>"\']+',text)
 link=next(x for x in links if 'token=' in x or 'token_hash=' in x)
 (ROOT/'recovery-captured-private.eml').write_bytes(messages[0])
 expected='https://178-105-167-26.nip.io/supabase/auth/v1/verify'
 if not link.startswith(expected+'?'):raise RuntimeError('Recovery link has wrong external URL contract')
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args):return None
 opener=urllib.request.build_opener(NoRedirect())
 try:opener.open(base+'/auth/v1/verify'+urllib.parse.urlsplit(link).query.join(['?','']),timeout=20);raise RuntimeError('Missing verification redirect')
 except urllib.error.HTTPError as response:
  if response.code!=302:raise RuntimeError('Recovery verification failed')
  location=response.headers['Location']
 fragment=urllib.parse.parse_qs(urllib.parse.urlsplit(location).fragment)
 access=fragment.get('access_token',[''])[0]
 if not access:raise RuntimeError('Recovery redirect lacks access token')
 newpassword=secrets.token_urlsafe(24)
 result=request('/auth/v1/user',{'password':newpassword},access,'PUT')
 assert result['id']==user['id']
 login=request('/auth/v1/token?grant_type=password',{'email':user['email'],'password':newpassword})
 assert login['user']['id']==user['id']
 evidence={'local_capture_messages':1,'external_messages_sent':0,'recovery_url':expected,'reset_password_passed':True,'new_password_login_passed':True,'source_auth_modified':False}
 (ROOT/'recovery-evidence.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))
except Exception:
 subprocess.run(['docker','logs','--since','2m','dashboard-supabase-20261003-auth-1'],stdout=(ROOT/'recovery-failure-private.log').open('w'),stderr=subprocess.STDOUT)
 print(json.dumps({'local_messages_captured':len(messages),'private_diagnostic':'recovery-failure-private.log'}))
 raise
finally:
 server.shutdown();server.server_close();compose(False);override.unlink(missing_ok=True)
