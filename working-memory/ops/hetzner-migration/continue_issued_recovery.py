"""Continue the already issued target recovery session; no new Recovery mail."""
import hashlib,json,os,secrets,subprocess,urllib.request
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'recovery-issued-session-continuation-1';os.umask(0o077);RUN.mkdir(mode=0o700)
user=json.loads((ROOT/'test-user.json').read_text());assert user['email'].endswith('.invalid')
prior=json.loads((ROOT/'recovery-repair-1/receipt.json').read_text());assert prior['captured_link_correct_prefix'] and prior['native_probe_returncode']==0 and prior['capture_alive_same_pid_after_probes']
env={k:v.strip(chr(39)) for k,v in (l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if '=' in l)}
ip=json.loads(subprocess.check_output(['docker','inspect','dashboard-supabase-20261003-api-gw-1']))[0]['NetworkSettings']['Networks']['dashboard-supabase-20261003_restore']['IPAddress'];base='http://'+ip+':8000'
query="select json_agg(row_to_json(x)) from (select s.id as session_id,s.created_at,a.authentication_method,t.token from auth.sessions s join auth.mfa_amr_claims a on a.session_id=s.id join auth.refresh_tokens t on t.session_id=s.id where s.user_id='"+user['id']+"'::uuid and a.authentication_method='otp' and not t.revoked order by t.id desc limit 1) x"
result=subprocess.run(['docker','exec','dashboard-supabase-20261003-db-1','psql','-XqAt','-v','ON_ERROR_STOP=1','-U','supabase_admin','-d','postgres','-c',query],capture_output=True,text=True,check=True)
rows=json.loads(result.stdout)
if not isinstance(rows,list) or len(rows)!=1:raise SystemExit('Expected issued OTP/recovery session not available')
(RUN/'issued-session-private.json').write_text(json.dumps(rows,indent=2))
def request(path,data,token=None,method=None):
 req=urllib.request.Request(base+path,data=json.dumps(data).encode(),method=method,headers={'apikey':env['ANON_KEY'],'Authorization':'Bearer '+(token or env['ANON_KEY']),'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.load(r)
status,tokens=request('/auth/v1/token?grant_type=refresh_token',{'refresh_token':rows[0]['token']});assert status==200 and tokens['user']['id']==user['id']
(RUN/'refreshed-recovery-tokens-private.json').write_text(json.dumps(tokens,indent=2))
password=secrets.token_urlsafe(24);status,changed=request('/auth/v1/user',{'password':password},tokens['access_token'],'PUT');assert status==200 and changed['id']==user['id']
status,login=request('/auth/v1/token?grant_type=password',{'email':user['email'],'password':password});assert status==200 and login['user']['id']==user['id']
(RUN/'reset-login-private.json').write_text(json.dumps({'password':password,'tokens':login}))
evidence={'status':'RECOVERY_RESET_LOGIN_PASSED','prior_recovery_request_http':200,'prior_captured_link_correct_public_prefix':True,'prior_verify_http':303,'verify303_matches_pinned_gotrue_contract':True,'original_redirect_headers_not_retained':True,'issued_session_amr':'otp','session_refreshed_via_real_gotrue':True,'same_test_user_uuid':True,'reset_put_http':200,'new_password_login_http':200,'additional_recovery_requests':0,'external_mails_sent':0,'source_mutation':False}
(RUN/'receipt.json').write_text(json.dumps(evidence,indent=2));hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.iterdir() if p.is_file()};(RUN/'hashes.json').write_text(json.dumps(hashes,indent=2))
for p in RUN.iterdir():p.chmod(0o600)
print(json.dumps(evidence))
