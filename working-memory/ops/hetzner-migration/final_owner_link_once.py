"""Hetzner-only official admin magiclink for existing owner; no mail or password update."""
import argparse,hashlib,json,os,re,subprocess,urllib.parse,urllib.request
from pathlib import Path

# Failure captures are private and append-only; outward messages contain no payloads.
import base64 as _b64, uuid as _uuid
import urllib.request
PRIVATE_ERRORS = Path('/private/tmp/hz-final-protocol-private-errors')
def private_error(operation, error=None, *, directory=None, stdout=None, stderr=None, body=None, status=None, headers=None, method=None):
    directory = Path(directory) if directory is not None else PRIVATE_ERRORS
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise RuntimeError('Unsafe private diagnostic directory') from None
    def encoded(value):
        if value is None: return None
        return _b64.b64encode(value.encode() if isinstance(value, str) else value).decode('ascii')
    record = {'operation': operation, 'exception_type': type(error).__name__ if error else None,
              'exception_text': str(error) if error else None, 'stdout_b64': encoded(stdout),
              'stderr_b64': encoded(stderr), 'body_b64': encoded(body), 'status': status,
              'headers': list(headers.items()) if headers is not None else None, 'method': method}
    path = directory / (_uuid.uuid4().hex + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(record, stream); stream.flush(); os.fsync(stream.fileno())
    return {'kind': type(error).__name__ if error else 'ProcessFailure', 'private_path': str(path), 'operation': operation}
def safe_failure(receipt):
    return RuntimeError(json.dumps(receipt))
def run_process(args, *, operation, private_errors=None, **kw):
    try:
        result = subprocess.run(args, capture_output=True, **kw)
    except Exception as error:
        receipt = private_error(operation, error, directory=private_errors,
                                stdout=getattr(error, 'stdout', None), stderr=getattr(error, 'stderr', None))
        raise safe_failure(receipt) from None
    if result.returncode:
        receipt = private_error(operation, directory=private_errors, stdout=result.stdout,
                                stderr=result.stderr, status=result.returncode)
        raise safe_failure(receipt) from None
    return result.stdout

def http_read(request, *, operation, private_errors=None, timeout=30, preserve_success=False):
    method = request.get_method() if hasattr(request, 'get_method') else 'GET'
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(); status = response.status; headers = response.headers
            if preserve_success:
                private_error(operation, directory=private_errors, body=body, status=status, headers=headers, method=method)
            return body, status, headers
    except Exception as error:
        body = None
        if hasattr(error, 'read'):
            try: body = error.read()
            except Exception as read_error:
                private_error(operation, read_error, directory=private_errors)
        receipt = private_error(operation, error, directory=private_errors, body=body,
                                status=getattr(error, 'code', None), headers=getattr(error, 'headers', None), method=method)
        raise safe_failure(receipt) from None
CLOSED_FLAGS={'MEMORY_READ_ONLY':'1','MEMORY_INTAKE_ENABLED':'0','MEMORY_AUTOMATIC_ENABLED':'0','MEMORY_QA_ENABLED':'0','MEMORY_ORIGINAL_DELETION_ENABLED':'0'}
ROOT=Path('/opt/dashboard-supabase-20261003');LIVE=Path('/opt/dashboard-memory-canonical-draft');TARGET='https://178-105-167-26.nip.io/supabase';REDIRECT='https://team-dashboard-rho.vercel.app/memory-next'
def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--production-owner-go',required=True);a=p.parse_args();os.umask(0o077)
    run=Path(a.run_dir).resolve();global PRIVATE_ERRORS;PRIVATE_ERRORS=run/'private-errors';assert run.parent==ROOT and re.fullmatch(r'final-export-[0-9TZ-]+',run.name)
    assert a.production_owner_go=='HZ-MIGRATION-20261003-FINAL-FRONTEND'
    assert json.loads((run/'target-runtime-receipt.json').read_text())['status']=='TARGET_READONLY_RUNTIME_ACTIVE'
    cfg=dict(l.split('=',1) for l in (LIVE/'.local/service.env').read_text().splitlines() if l and not l.startswith('#'))
    assert all(cfg.get(k)==v for k,v in CLOSED_FLAGS.items())
    allowed=cfg['MEMORY_ALLOWED_USERS'].split(',');assert len(allowed)==1
    q="SELECT row_to_json(x) FROM (SELECT id,email,encrypted_password FROM auth.users WHERE id='"+allowed[0]+"'::uuid) x;"
    assert re.fullmatch('[0-9a-f-]{36}',allowed[0])
    r=run_process(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-XqAt','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],input=q,text=True,operation='owner-sql')
    owner=json.loads(r);assert owner['id']==allowed[0] and owner['email'] and owner['encrypted_password']
    (run/'owner-magiclink-attempt.marker').open('x').write('one existing owner official GoTrue admin link')
    private=dict(l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if l and not l.startswith('#'));key=private['SERVICE_ROLE_KEY'].strip("'")
    req=urllib.request.Request(TARGET+'/auth/v1/admin/generate_link',data=json.dumps({'type':'magiclink','email':owner['email'],'redirect_to':REDIRECT}).encode(),headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    body,status,_=http_read(req,operation='owner-generate-link');result=json.loads(body)
    (run/'owner-generate-link-private.json').write_bytes(body)
    assert status==200 and result['id']==owner['id'] and result['verification_type']=='magiclink' and result['redirect_to']==REDIRECT
    url=urllib.parse.urlsplit(result['action_link']);params=urllib.parse.parse_qs(url.query)
    assert url.scheme=='https' and url.netloc=='178-105-167-26.nip.io' and url.path=='/supabase/auth/v1/verify' and not url.fragment
    assert params['type']==['magiclink'] and params['redirect_to']==[REDIRECT] and params.get('token')
    actual=run_process(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-XqAt','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],input=q,text=True,operation='owner-sql')
    assert json.loads(actual)['encrypted_password']==owner['encrypted_password']
    (run/'owner-original-action-link-private.txt').write_text(result['action_link']);(run/'owner-original-action-link-private.txt').chmod(0o600)
    receipt={'http':200,'official_admin_existing_owner':True,'redirect':REDIRECT,'owner_password_hash_unchanged':True,'action_link_original_sha256':hashlib.sha256(result['action_link'].encode()).hexdigest(),'generated_links':1,'mail_requests':0,'source_auth_changes':0,'production_browser_proof_pending':True}
    (run/'owner-link-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()
