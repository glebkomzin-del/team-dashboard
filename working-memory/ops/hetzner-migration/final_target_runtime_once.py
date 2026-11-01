"""Run on Hetzner after exact final COPY comparison; resume only a readonly backend."""
import argparse,datetime,hashlib,json,os,re,shutil,subprocess,tempfile
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
import urllib.request
CLOSED_FLAGS={'MEMORY_READ_ONLY':'1','MEMORY_INTAKE_ENABLED':'0','MEMORY_AUTOMATIC_ENABLED':'0','MEMORY_QA_ENABLED':'0','MEMORY_ORIGINAL_DELETION_ENABLED':'0'}
SERVER_SHA='3cde7428a6100472a5c54fd80062a65ca2834ac4792c0c02f969474964df979f'
def closed_flags(cfg):
    assert all(cfg.get(k)==v for k,v in CLOSED_FLAGS.items())
def verify_container_flags(image):
    env=dict(item.split('=',1) for item in image['Config']['Env'] if '=' in item)
    closed_flags(env)

ROOT=Path('/opt/dashboard-supabase-20261003');LIVE=Path('/opt/dashboard-memory-canonical-draft');DB='dashboard-supabase-20261003-db-1'
BASE='sha256:15a6a820f9d887fac5f0bcd3e2dd29c477d4d5f6a7e82db41bb83cd899f43a2f'
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def call(args,**kw):
    return run_process(args, operation='target-runtime-process', **kw)
def sql(q):return call(['docker','exec','-i',DB,'psql','-XqAt','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],input=q.encode()).decode()
def lit(v):return "'"+str(v).replace("'","''")+"'"
def atomic(p,body):
    fd,n=tempfile.mkstemp(dir=p.parent,prefix='.final-');os.fchmod(fd,p.stat().st_mode&0o777)
    with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
    os.replace(n,p)
def observe_runtime_health(url='http://127.0.0.1:8798/health', seconds=90):
    # GET readiness observations do not repeat starts, credentials or mutations.
    import time
    deadline=time.monotonic()+seconds
    while True:
        try:
            body,_,_=http_read(url,operation='target-runtime-health',timeout=5)
            return json.loads(body)
        except RuntimeError:
            if time.monotonic()>=deadline:raise
            time.sleep(2)

def main():
    a=argparse.ArgumentParser();a.add_argument('--run-dir',required=True);a.add_argument('--gate-receipt',required=True);v=a.parse_args();os.umask(0o077)
    run=Path(v.run_dir).resolve();global PRIVATE_ERRORS;PRIVATE_ERRORS=run/'private-errors';assert run.parent==ROOT and re.fullmatch('final-export-[0-9TZ-]+',run.name)
    gate=json.loads(Path(v.gate_receipt).read_text());assert gate['decision']=='CONTINUE_BOUNDED' and gate['run_dir']==str(run)
    comparison=json.loads((run/'final-snapshot-comparison.json').read_text());assert not comparison['mismatches'] and comparison['comparison_before_auth_vault_acl'] and comparison['source_sha256']==gate['dump_sha256']
    (run/'target-runtime-attempt.marker').open('x').write('single COPY-bound readonly activation')
    row=json.loads((run/'vault-plaintext.json').read_text())[0]
    before=json.loads(sql("SELECT row_to_json(s) FROM (SELECT id,name,description,created_at,updated_at,encode(nonce,'hex') AS nonce_hex FROM vault.secrets) s"))
    assert all(before[k]==row[k] for k in ['id','name','description','nonce_hex'])
    assert all(datetime.datetime.fromisoformat(before[k])==datetime.datetime.fromisoformat(row[k]) for k in ['created_at','updated_at'])
    sql("UPDATE vault.secrets s SET secret=encode(vault._crypto_aead_det_encrypt(message:=convert_to("+lit(row['decrypted_secret'])+",'utf8'),additional:=convert_to(s.id::text,'utf8'),key_id:=0,context:='pgsodium'::bytea,nonce:=s.nonce),'base64') WHERE id="+lit(row['id'])+"::uuid;")
    actual=sql("SELECT encode(extensions.digest(decrypted_secret,'sha256'),'hex') FROM vault.decrypted_secrets").strip()
    assert actual==hashlib.sha256(row['decrypted_secret'].encode()).hexdigest()
    after=json.loads(sql("SELECT row_to_json(s) FROM (SELECT id,name,description,created_at,updated_at,encode(nonce,'hex') AS nonce_hex FROM vault.secrets) s"))
    assert after==before
    acl=run/'freeze-business-restore-acl.sql';assert h(acl)=='26c34f43afa8408e933589b6ce705bf09bd3e36234904de81166b26dd1955f02';sql(acl.read_text())
    original=json.loads((run/'source-original-config-private.json').read_text());target=json.loads(sql('SELECT json_agg(c ORDER BY space_id) FROM public.wm_processing_config c'))
    assert [{**r,'enabled':False} for r in original]==target
    # Preserve the full original configuration contract; only the temporary enabled bit is reversed.
    for r in original:sql('UPDATE public.wm_processing_config SET enabled='+('true' if r['enabled'] else 'false')+' WHERE space_id='+lit(r['space_id'])+'::uuid;')
    assert json.loads(sql('SELECT json_agg(c ORDER BY space_id) FROM public.wm_processing_config c'))==original
    call(['docker','compose','--env-file','.private.env','up','-d','--no-build','auth','rest','api-gw','functions'],cwd=ROOT,timeout=120)
    manifest=json.loads((LIVE/'build-manifest.json').read_text());assert manifest['scheduled_backup.py']=='58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9' and h(LIVE/'scheduled_backup.py')==manifest['scheduled_backup.py']
    image=json.loads(call(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0];assert image['Image']==BASE and not image['State']['Running']
    assert hashlib.sha256(call(['docker','run','--rm','--network=none','--entrypoint','cat',BASE,'/app/server.py'])).hexdigest()==SERVER_SHA
    stage=Path('/opt/dashboard-memory-stage-read-20261003/build');stage_manifest=json.loads((stage.parent/'build-manifest.json').read_text())
    build=run/'runtime-build';build.mkdir(mode=0o700)
    for name in ['access.py','gateway_journal.py']:
        change=stage_manifest['origin_only_changes'][name]
        assert h(stage/name)==change['after_sha256'] and h(LIVE/name)==change['before_sha256'] and manifest[name]==change['before_sha256']
        assert hashlib.sha256(call(['docker','run','--rm','--network=none','--entrypoint','cat',BASE,'/app/'+name])).hexdigest()==change['before_sha256']
        shutil.copyfile(stage/name,build/name)
    call(['docker','tag',BASE,'dashboard-canonical-baseline:hz20261003'])
    (build/'Dockerfile').write_text('FROM dashboard-canonical-baseline:hz20261003\nCOPY access.py gateway_journal.py /app/\n')
    image_name='dashboard-memory:hetzner-final-20261003';call(['docker','build','--pull=false','-t',image_name,str(build)],timeout=120)
    base_meta=json.loads(call(['docker','image','inspect',BASE]))[0]
    built_meta=json.loads(call(['docker','image','inspect',image_name]))[0]
    assert built_meta['RootFS']['Layers'][:-1]==base_meta['RootFS']['Layers']
    assert len(built_meta['RootFS']['Layers'])==len(base_meta['RootFS']['Layers'])+1
    assert hashlib.sha256(call(['docker','run','--rm','--network=none','--entrypoint','cat',image_name,'/app/server.py'])).hexdigest()==SERVER_SHA
    for name in ['access.py','gateway_journal.py']:
        assert hashlib.sha256(call(['docker','run','--rm','--network=none','--entrypoint','cat',image_name,'/app/'+name])).hexdigest()==h(build/name)
    backup=run/'host-runtime-original';backup.mkdir(mode=0o700)
    for name in ['compose.yaml','build-manifest.json','access.py','gateway_journal.py']:shutil.copyfile(LIVE/name,backup/name)
    shutil.copyfile(LIVE/'.local/service.env',backup/'service.env');(backup/'service.env').chmod(0o600)
    cfg=dict(l.split('=',1) for l in (LIVE/'.local/service.env').read_text().splitlines() if l and not l.startswith('#'))
    assert cfg['SUPABASE_URL'].rstrip('/')=='https://lghwikeotbkmojyyjglz.supabase.co'
    private=dict(l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if l and not l.startswith('#'))
    source_env=dict(item.split('=',1) for item in image['Config']['Env'] if '=' in item)
    original_flags={k:source_env.get(k,'0') for k in CLOSED_FLAGS}
    assert original_flags=={k:cfg.get(k,'0') for k in CLOSED_FLAGS}
    assert all(v in ('0','1') for v in original_flags.values())
    with (run/'source-original-runtime-flags.json').open('x') as f:json.dump(original_flags,f)
    (run/'source-original-runtime-flags.json').chmod(0o600)
    cfg.update(CLOSED_FLAGS)
    cfg.update(SUPABASE_URL='https://178-105-167-26.nip.io/supabase',SUPABASE_PUBLISHABLE_KEY=private['ANON_KEY'].strip("'"),MEMORY_READ_ONLY='1',MEMORY_INTAKE_ENABLED='0',MEMORY_AUTOMATIC_ENABLED='0')
    closed_flags(cfg)
    assert all('\n' not in x and '\r' not in x for x in cfg.values())
    atomic(LIVE/'.local/service.env',''.join(k+'='+val+'\n' for k,val in cfg.items()).encode())
    compose=(LIVE/'compose.yaml').read_text();assert compose.count('image: dashboard-memory:memory-20260921-compact-guard-final')==1
    atomic(LIVE/'compose.yaml',compose.replace('image: dashboard-memory:memory-20260921-compact-guard-final','image: '+image_name).encode())
    for name in ['access.py','gateway_journal.py']:
        atomic(LIVE/name,(build/name).read_bytes());manifest[name]=h(build/name)
    atomic(LIVE/'build-manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
    # Activate the reviewed full backup mode with a private marker; no hosted-only success allowed.
    marker=LIVE/'.local/selfhost-backup.json';assert not marker.exists()
    with marker.open('x') as f:json.dump({'enabled':True,'migration_run':run.name},f)
    marker.chmod(0o600)
    call(['docker','compose','up','-d','--no-build','canonical-draft'],cwd=LIVE,timeout=120)
    host_cfg=dict(l.split('=',1) for l in (LIVE/'.local/service.env').read_text().splitlines() if l and not l.startswith('#'))
    closed_flags(host_cfg)
    active=json.loads(call(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]
    assert active['State']['Running'] and active['Image']==built_meta['Id'];verify_container_flags(active)
    assert hashlib.sha256(call(['docker','exec','dashboard-memory-canonical-draft-canonical-draft-1','cat','/app/server.py'])).hexdigest()==SERVER_SHA
    for name in ['access.py','gateway_journal.py']:
        assert hashlib.sha256(call(['docker','exec','dashboard-memory-canonical-draft-canonical-draft-1','cat','/app/'+name])).hexdigest()==h(build/name)
    # Restore narrow backend ingress only after the actual readonly runtime health passes.
    health=observe_runtime_health()
    nginx=Path('/etc/nginx/sites-available/alexa');expected=(run/'nginx-maintenance.conf').read_bytes()
    assert nginx.read_bytes()==expected
    atomic(nginx,(run/'nginx-original.conf').read_bytes());call(['nginx','-t']);call(['systemctl','reload','nginx'])
    result={'status':'TARGET_READONLY_RUNTIME_ACTIVE','vault_plaintext_equal':True,'vault_metadata_preserved':True,'original_acl_restored':True,'original_config_enabled_restored':True,'backend_origin':'https://178-105-167-26.nip.io/supabase','readonly':True,'automatic':False,'intake':False,'qa':False,'original_deletion':False,'closed_flags':CLOSED_FLAGS,'original_flags_receipt':str(run/'source-original-runtime-flags.json'),'server_py_sha256':SERVER_SHA,'backup_marker':True,'base_image':BASE,'target_image':json.loads(call(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]['Image'],'health':health,'writers_opened':False}
    (run/'target-runtime-receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
