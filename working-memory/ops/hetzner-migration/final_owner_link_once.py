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
    body,status,_=http_read(req,operation='owner-generate-link')
    (run/'owner-generate-link-private.json').write_bytes(body);(run/'owner-generate-link-private.json').chmod(0o600)
    result=json.loads(body)
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
