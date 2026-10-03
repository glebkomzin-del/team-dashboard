"""Hetzner-only official admin magiclink for existing owner; no mail or password update."""
import argparse,hashlib,json,os,re,subprocess,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');TARGET='https://178-105-167-26.nip.io/supabase';REDIRECT='https://team-dashboard-rho.vercel.app/memory-next'
def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--production-owner-go',required=True);a=p.parse_args();os.umask(0o077)
    run=Path(a.run_dir).resolve();assert run.parent==ROOT and re.fullmatch(r'final-export-[0-9TZ-]+',run.name)
    assert a.production_owner_go=='HZ-MIGRATION-20261003-FINAL-FRONTEND'
    assert json.loads((run/'target-runtime-receipt.json').read_text())['status']=='TARGET_READONLY_RUNTIME_ACTIVE'
    cfg=dict(l.split('=',1) for l in Path('/opt/dashboard-memory-canonical-draft/.local/service.env').read_text().splitlines() if l and not l.startswith('#'))
    assert cfg['MEMORY_READ_ONLY']=='1' and cfg['MEMORY_INTAKE_ENABLED']=='0' and cfg['MEMORY_AUTOMATIC_ENABLED']=='0'
    allowed=cfg['MEMORY_ALLOWED_USERS'].split(',');assert len(allowed)==1
    q="SELECT row_to_json(x) FROM (SELECT id,email,encrypted_password FROM auth.users WHERE id='"+allowed[0]+"'::uuid) x;"
    assert re.fullmatch('[0-9a-f-]{36}',allowed[0])
    r=subprocess.run(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-XqAt','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],input=q,text=True,capture_output=True,check=True)
    owner=json.loads(r.stdout);assert owner['id']==allowed[0] and owner['email'] and owner['encrypted_password']
    (run/'owner-magiclink-attempt.marker').open('x').write('one existing owner official GoTrue admin link')
    private=dict(l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if l and not l.startswith('#'));key=private['SERVICE_ROLE_KEY'].strip("'")
    req=urllib.request.Request(TARGET+'/auth/v1/admin/generate_link',data=json.dumps({'type':'magiclink','email':owner['email'],'redirect_to':REDIRECT}).encode(),headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:body=response.read();result=json.loads(body);status=response.status
    except Exception as err:
        if hasattr(err,'read'):(run/'owner-link-error-private.txt').write_bytes(err.read())
        raise RuntimeError('Official owner link failed; no automatic retry') from None
    (run/'owner-generate-link-private.json').write_bytes(body)
    assert status==200 and result['id']==owner['id'] and result['verification_type']=='magiclink' and result['redirect_to']==REDIRECT
    url=urllib.parse.urlsplit(result['action_link']);params=urllib.parse.parse_qs(url.query)
    assert url.scheme=='https' and url.netloc=='178-105-167-26.nip.io' and url.path=='/supabase/auth/v1/verify' and not url.fragment
    assert params['type']==['magiclink'] and params['redirect_to']==[REDIRECT] and params.get('token')
    actual=subprocess.run(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-XqAt','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],input=q,text=True,capture_output=True,check=True)
    assert json.loads(actual.stdout)['encrypted_password']==owner['encrypted_password']
    (run/'owner-original-action-link-private.txt').write_text(result['action_link']);(run/'owner-original-action-link-private.txt').chmod(0o600)
    receipt={'http':200,'official_admin_existing_owner':True,'redirect':REDIRECT,'owner_password_hash_unchanged':True,'action_link_original_sha256':hashlib.sha256(result['action_link'].encode()).hexdigest(),'generated_links':1,'mail_requests':0,'source_auth_changes':0,'production_browser_proof_pending':True}
    (run/'owner-link-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()
