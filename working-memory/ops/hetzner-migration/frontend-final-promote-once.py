"""Bounded final promotion; run only with explicit target-restored-readonly GO."""
import argparse, base64, datetime, hashlib, json, os, subprocess, urllib.request
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
OPS = Path(__file__).resolve().parent
artifact = json.loads((OPS/'frontend-target-artifact.json').read_text())
BUILD = Path(artifact['build_path'])
PRIVATE = Path('/private/tmp/hz-frontend-cutover-private')
ALIASES = {'team-dashboard-rho.vercel.app', 'team-dashboard-glebkomzin-dels-projects.vercel.app'}
ROLLBACK = 'dpl_84v5UqEaCs5TnRsb6QzahSNxeNxL'
PREVIEW = 'dpl_DfSYKEA5xDAH6XKT9yV3djWfAWZC'
RECEIPT = OPS/'frontend-final-promotion-evidence.json'

def cli(args, value=None):
    return run_process(['vercel', *args],operation='frontend-cli',private_errors=PRIVATE/'private-errors',cwd=BUILD,input=value,text=True,timeout=240)

def inspect(alias):
    return json.loads(cli(['inspect', alias, '--format', 'json']))

def frozen_checks():
    output=BUILD/'.vercel/output'
    assert hashlib.sha256((output/'config.json').read_bytes()).hexdigest()==artifact['output_hashes']['config.json']
    for name, digest in artifact['current_static_hashes'].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest()==digest, name
    assert hashlib.sha256(Path(artifact['artifact_archive']['path']).read_bytes()).hexdigest()==artifact['artifact_archive']['sha256']
    link=json.loads((BUILD/'.vercel/project.json').read_text())
    assert link['projectId']=='prj_pWCB8TaGLQesLsT9me0jgT0FqcC5' and link['orgId']=='team_xbeBltwkXhOuVc8JUUR0CqoF'
    return output

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--target-restored-readonly-go', required=True)
    args=parser.parse_args(); assert args.target_restored_readonly_go=='HZ-MIGRATION-20261003-FINAL-FRONTEND'
    os.umask(0o077)
    output=frozen_checks(); PRIVATE.mkdir(mode=0o700, exist_ok=True)
    marker=PRIVATE/'frontend-final-promotion-started'
    fd=os.open(marker, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600); os.close(fd)
    evidence={'problem_id':'HZ-MIGRATION-20261003-FINAL-FRONTEND','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'promotion_attempts':0,'auth_calls':0,'source_builds':0,'status':'STARTED'}
    try:
        for alias in ALIASES:
            old=inspect(alias); assert old['id']==ROLLBACK and old['readyState']=='READY'
        backup=PRIVATE/'final-production-before-promotion.env'
        cli(['env','pull',str(backup),'--environment','production','--yes']); backup.chmod(0o600)
        assert not any(line.startswith(('VITE_SUPABASE_URL=', 'VITE_SUPABASE_ANON_KEY=')) for line in backup.read_text().splitlines())
        remote="python3 -c \"from pathlib import Path; d=dict(x.split('=',1) for x in Path('/opt/dashboard-supabase-20261003/.private.env').read_text().splitlines() if '=' in x and not x.startswith('#')); print(d['ANON_KEY'].strip(chr(39)))\""
        key=run_process(['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','StrictHostKeyChecking=yes','root@178.105.167.26',remote],operation='frontend-target-key',private_errors=PRIVATE/'private-errors',text=True,timeout=30).strip()
        assert hashlib.sha256(key.encode()).hexdigest()==artifact['target_key_sha256']
        payload=json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'===')); assert payload['role']=='anon'
        cli(['env','add','VITE_SUPABASE_URL','production','--yes'],artifact['target_url']+'\n'); evidence['url_env_added']=True
        cli(['env','add','VITE_SUPABASE_ANON_KEY','production','--yes','--sensitive'],key+'\n'); evidence['anon_env_added']=True
        evidence['promotion_attempts']=1
        RECEIPT.write_text(json.dumps(evidence,indent=2)+'\n')
        cli(['promote',PREVIEW,'--yes'])
        deployments=[inspect(alias) for alias in sorted(ALIASES)]
        assert len({x['id'] for x in deployments})==1
        prod=deployments[0]; assert prod['readyState']=='READY' and prod['target']=='production'
        assert ALIASES.issubset(set(prod['aliases']))
        evidence['production']={k:prod[k] for k in ('id','readyState','target','aliases','url')}
        headers_expected=json.loads((output/'config.json').read_text())['routes'][0]['headers']
        checks=[]
        for alias in sorted(ALIASES):
            for route in ['/', '/memory-next?recovery=1']:
                body,status,headers=http_read('https://'+alias+route,operation='frontend-index',private_errors=PRIVATE/'private-errors',timeout=45); assert status==200
                for name,value in headers_expected.items(): assert headers.get(name)==value,name
                assert body.strip()==(output/'static/index.html').read_bytes().strip()
                checks.append({'alias':alias,'route':route,'http':200,'exact_index':True,'exact_headers':True})
            for name,digest in artifact['current_static_hashes'].items():
                if not name.startswith('static/assets/'): continue
                body,status,_=http_read('https://'+alias+'/'+name.removeprefix('static/'),operation='frontend-asset',private_errors=PRIVATE/'private-errors',timeout=45)
                assert status==200 and hashlib.sha256(body).hexdigest()==digest,name
                checks.append({'alias':alias,'route':name.removeprefix('static'),'sha256':digest,'exact_asset':True})
        evidence.update(status='PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED',checks=checks)
    except Exception as error:
        failure=private_error('frontend-promotion',error,directory=PRIVATE/'private-errors')
        evidence.update(status='STOPPED_NO_RETRY',failure=failure)
        raise safe_failure(failure) from None
    finally:
        RECEIPT.write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps({k:evidence[k] for k in ('status','promotion_attempts','auth_calls','source_builds')}))
if __name__=='__main__': main()
