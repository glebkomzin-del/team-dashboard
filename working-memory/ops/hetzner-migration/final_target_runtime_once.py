"""Run on Hetzner after exact final COPY comparison; resume only a readonly backend."""
import argparse,datetime,hashlib,json,os,re,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');LIVE=Path('/opt/dashboard-memory-canonical-draft');DB='dashboard-supabase-20261003-db-1'
BASE='sha256:15a6a820f9d887fac5f0bcd3e2dd29c477d4d5f6a7e82db41bb83cd899f43a2f'
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def call(args,**kw):
    x=subprocess.run(args,capture_output=True,**kw)
    if x.returncode:raise RuntimeError('Target operation failed: '+args[0])
    return x.stdout
def sql(q):return call(['docker','exec','-i',DB,'psql','-XqAt','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],input=q.encode()).decode()
def lit(v):return "'"+str(v).replace("'","''")+"'"
def atomic(p,body):
    fd,n=tempfile.mkstemp(dir=p.parent,prefix='.final-');os.fchmod(fd,p.stat().st_mode&0o777)
    with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
    os.replace(n,p)
def main():
    a=argparse.ArgumentParser();a.add_argument('--run-dir',required=True);a.add_argument('--gate-receipt',required=True);v=a.parse_args();os.umask(0o077)
    run=Path(v.run_dir).resolve();assert run.parent==ROOT and re.fullmatch('final-export-[0-9TZ-]+',run.name)
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
    stage=Path('/opt/dashboard-memory-stage-read-20261003/build');stage_manifest=json.loads((stage.parent/'build-manifest.json').read_text())
    build=run/'runtime-build';build.mkdir(mode=0o700)
    for name in ['access.py','gateway_journal.py']:
        change=stage_manifest['origin_only_changes'][name]
        assert h(stage/name)==change['after_sha256'] and h(LIVE/name)==change['before_sha256'] and manifest[name]==change['before_sha256']
        shutil.copyfile(stage/name,build/name)
    call(['docker','tag',BASE,'dashboard-canonical-baseline:hz20261003'])
    (build/'Dockerfile').write_text('FROM dashboard-canonical-baseline:hz20261003\nCOPY access.py gateway_journal.py /app/\n')
    image_name='dashboard-memory:hetzner-final-20261003';call(['docker','build','--pull=false','-t',image_name,str(build)],timeout=120)
    backup=run/'host-runtime-original';backup.mkdir(mode=0o700)
    for name in ['compose.yaml','build-manifest.json','access.py','gateway_journal.py']:shutil.copyfile(LIVE/name,backup/name)
    shutil.copyfile(LIVE/'.local/service.env',backup/'service.env')
    cfg=dict(l.split('=',1) for l in (LIVE/'.local/service.env').read_text().splitlines() if l and not l.startswith('#'))
    assert cfg['SUPABASE_URL'].rstrip('/')=='https://lghwikeotbkmojyyjglz.supabase.co'
    private=dict(l.split('=',1) for l in (ROOT/'.private.env').read_text().splitlines() if l and not l.startswith('#'))
    cfg.update(SUPABASE_URL='https://178-105-167-26.nip.io/supabase',SUPABASE_PUBLISHABLE_KEY=private['ANON_KEY'].strip("'"),MEMORY_READ_ONLY='1',MEMORY_INTAKE_ENABLED='0',MEMORY_AUTOMATIC_ENABLED='0')
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
    # Restore narrow backend ingress only after the actual readonly runtime health passes.
    import time,urllib.request
    deadline=time.monotonic()+90
    while True:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8798/health',timeout=5) as r:health=json.load(r)
            break
        except Exception:
            if time.monotonic()>deadline:raise RuntimeError('Readonly runtime not healthy; maintenance remains')
            time.sleep(2)
    nginx=Path('/etc/nginx/sites-available/alexa');expected=(run/'nginx-maintenance.conf').read_bytes()
    assert nginx.read_bytes()==expected
    atomic(nginx,(run/'nginx-original.conf').read_bytes());call(['nginx','-t']);call(['systemctl','reload','nginx'])
    result={'status':'TARGET_READONLY_RUNTIME_ACTIVE','vault_plaintext_equal':True,'vault_metadata_preserved':True,'original_acl_restored':True,'original_config_enabled_restored':True,'backend_origin':'https://178-105-167-26.nip.io/supabase','readonly':True,'automatic':False,'intake':False,'backup_marker':True,'base_image':BASE,'target_image':json.loads(call(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]['Image'],'health':health,'writers_opened':False}
    (run/'target-runtime-receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
