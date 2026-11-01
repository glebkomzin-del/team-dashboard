"""Root-owned Dashboard Job backups. Shared n8n is read, never restarted.

Every successful archive includes the canonical journal/originals/queue,
configuration, n8n database and data, and an isolated n8n restore receipt.
"""
import argparse
from datetime import datetime,timezone,timedelta
import fcntl,hashlib,json,os,re
from pathlib import Path
import secrets,shutil,subprocess,tarfile,tempfile,time
from urllib.parse import urlparse

from canonical_backup import export,checksum,private_json,verify
from canonical_restore import generate as generate_restore
from deletion_backup import persist_restore_barrier
from gateway_journal import GatewayJournal,TransientGateway

ROOT=Path('/opt/dashboard-memory-canonical-draft')
BACKUPS=Path('/var/backups/dashboard-job')
STATUS=ROOT/'.local/cache/backup-status.json'
BACKUP_LOCK=Path('/run/lock/dashboard-job-backup.lock')
RESTORE_BARRIER=Path('/app/.local/restore-barrier/deletions.json')
DEFAULT_QUESTION_OUTBOX=Path('/app/.local/question-outbox')
APP_UID=10001
APP_GID=10001


SELFHOST_ROOT=Path('/opt/dashboard-supabase-20261003')
SELFHOST_CONTAINER='dashboard-supabase-20261003-db-1'
SELFHOST_FINGERPRINT_SQL="""
SELECT json_build_object(
 'tables', (SELECT json_object_agg(format('%I.%I',n.nspname,c.relname),
   (xpath('/row/n/text()',query_to_xml(format('select count(*) as n from %I.%I',n.nspname,c.relname),false,true,'')))[1]::text::bigint)
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relkind IN ('r','p') AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
   AND NOT EXISTS (SELECT 1 FROM pg_depend d JOIN pg_extension e ON e.oid=d.refobjid
     WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e'
       AND NOT c.oid=ANY(coalesce(e.extconfig,ARRAY[]::oid[])))),
 'auth_users', (SELECT md5(coalesce(string_agg(md5(to_jsonb(u)::text),'' ORDER BY id),'')) FROM auth.users u),
 'vault', (SELECT md5(coalesce(string_agg(id::text||md5(decrypted_secret),'' ORDER BY id),'')) FROM vault.decrypted_secrets),
 'roles', (SELECT json_object_agg(rolname,json_build_array(rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls,md5(rolpassword)))
   FROM pg_authid WHERE rolname NOT LIKE 'pg_%'));
"""


def selfhost_enabled(cfg):
    marker=ROOT/'.local/selfhost-backup.json'
    if marker.exists():
        value=json.loads(marker.read_text())
        if not isinstance(value,dict) or type(value.get('enabled')) is not bool:
            raise RuntimeError('Invalid selfhost backup activation marker')
        if value['enabled']:return True
    # A switched gateway must never receive a hosted-only successful backup.
    host=urlparse(cfg.get('SUPABASE_URL','')).hostname or ''
    if not host.endswith('.supabase.co'):
        raise RuntimeError('Selfhost origin requires an enabled full backup adapter')
    return False


def restore_roles_sql(body,existing):
    # pg_dumpall emits one CREATE ROLE per line. Preserve ALTER (passwords,
    # attributes) and memberships; skip only bootstrap roles already present.
    return b''.join(line for line in body.splitlines(keepends=True)
                    if line.rstrip().decode() not in {'CREATE ROLE '+name+';' for name in existing})


def selfhost_psql(pg,sql,database='postgres'):
    return run(['docker','exec',pg,'psql','-X','-qAt','-U','supabase_admin','-d',database,
                '-v','ON_ERROR_STOP=1','-c',sql],timeout=600)


def selfhost_restore(folder,pg,expected):
    isolated=folder/'isolated-restore';isolated.mkdir(mode=0o700)
    pgdata=isolated/'pgdata';pgdata.mkdir(mode=0o700)
    pgconfig=isolated/'pg-config';shutil.copytree(folder/'configuration/pg-config',pgconfig)
    # docker cp may map source ownership to root. Private modes stay intact;
    # only this disposable copy belongs to the actual image's postgres account.
    owner=json.loads((folder/'runtime-image.json').read_text())['postgres_account']
    for path in [pgconfig,*pgconfig.rglob('*')]:os.chown(path,owner['uid'],owner['gid'])
    name='dashboard-selfhost-restore-'+secrets.token_hex(6)
    environment=isolated/'postgres.env'
    environment.write_text('POSTGRES_PASSWORD='+secrets.token_hex(32)+'\nPGPORT=5432\nPOSTGRES_PORT=5432\nPOSTGRES_DB=postgres\n')
    environment.chmod(0o600)
    try:
        run(['docker','run','-d','--pull=never','--name',name,'--network','none','--memory=1g','--cpus=1',
             '--env-file',str(environment),'--mount','type=bind,source='+str(pgdata)+',target=/var/lib/postgresql/data',
             '--mount','type=bind,source='+str(pgconfig)+',target=/etc/postgresql-custom',pg['Image'],
             *pg['Config']['Cmd'],'-c','cron.launch_active_jobs=off'])
        for attempt in range(180):
            ready=subprocess.run(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','supabase_admin','-d','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if ready.returncode==0:break
            time.sleep(.5)
        else:raise RuntimeError('Isolated selfhost restore database not ready')
        existing=selfhost_psql(name,'SELECT quote_ident(rolname) FROM pg_roles').decode().splitlines()
        roles=restore_roles_sql((folder/'roles.sql').read_bytes(),existing)
        # Role statements contain passwords: never log SQL or stderr, including
        # failed ALTER statements. The private backup is the recovery authority.
        result=subprocess.run(['docker','exec','-i',name,'psql','-X','-q','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],input=roles,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=180)
        if result.returncode:raise RuntimeError('Isolated selfhost role restore failed')
        # Use an empty database rather than --clean: bootstrap-only objects
        # can otherwise survive outside the dump and alter the recovered schema.
        selfhost_psql(name,'DROP DATABASE postgres WITH (FORCE)','template1')
        selfhost_psql(name,'CREATE DATABASE postgres TEMPLATE template0 OWNER postgres','template1')
        with (folder/'postgres.dump').open('rb') as stream:
            result=subprocess.run(['docker','exec','-i',name,'pg_restore','-U','supabase_admin','-d','postgres','--exit-on-error'],stdin=stream,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=900)
        if result.returncode:raise RuntimeError('Isolated selfhost database restore failed')
        actual=json.loads(selfhost_psql(name,SELFHOST_FINGERPRINT_SQL))
        if actual!=expected:raise RuntimeError('Isolated selfhost tables, Auth, Vault or role fingerprint mismatch')
        config=folder/'configuration'
        return {'tables':actual['tables'],'auth_users_verified':True,'vault_decryption_verified':True,
                'roles_verified':True,'external_network':False,'services_started':['postgres'],
                'dump_sha256':checksum(folder/'postgres.dump'),'roles_sha256':checksum(folder/'roles.sql'),
                'configuration_sha256':{str(p.relative_to(config)):checksum(p) for p in sorted(config.rglob('*')) if p.is_file()}}
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        shutil.rmtree(isolated,ignore_errors=True)


def backup_selfhost(folder,cfg):
    if not selfhost_enabled(cfg):return {'enabled':False}
    pg=container(SELFHOST_CONTAINER)
    if not pg.get('State',{}).get('Running') or not pg['Config']['Image'].startswith('supabase/postgres:17.'):
        raise RuntimeError('Selfhost PG17 target is unavailable')
    target=folder/'selfhost';target.mkdir(mode=0o700)
    config=target/'configuration';config.mkdir(mode=0o700)
    for name in ('.private.env','compose.yaml','upstream-manifest.json','upstream','functions'):
        source=SELFHOST_ROOT/name
        if source.is_symlink() or not source.exists():raise RuntimeError('Selfhost recovery configuration missing')
        if source.is_dir():
            if any(p.is_symlink() for p in source.rglob('*')):raise RuntimeError('Selfhost configuration contains unsupported symlink')
            shutil.copytree(source,config/name)
        else:shutil.copy2(source,config/name)
    # Includes pgsodium_root.key: DB dumps alone cannot decrypt Vault secrets.
    run(['docker','cp','-a',pg['Id']+':/etc/postgresql-custom',str(config/'pg-config')])
    for path in config.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):raise RuntimeError('Selfhost configuration contains unsupported file')
        path.chmod(0o700 if path.is_dir() else 0o600)
    values=env_file(config/'.private.env')
    if not all(values.get(k,'').strip("'\"") for k in ('POSTGRES_PASSWORD','JWT_SECRET','ANON_KEY','SERVICE_ROLE_KEY','SMTP_USER','SMTP_PASS')):
        raise RuntimeError('Selfhost private configuration incomplete')
    if not (config/'pg-config/pgsodium_root.key').is_file():raise RuntimeError('Selfhost Vault recovery key missing')
    database_bytes=int(selfhost_psql(pg['Id'],'SELECT pg_database_size(current_database())').strip())
    if shutil.disk_usage(folder).free < max(3_000_000_000,database_bytes*4):
        raise RuntimeError('Insufficient disk space for selfhost backup and isolated restore')
    owner={'uid':int(run(['docker','exec',pg['Id'],'id','-u','postgres']).strip()),
           'gid':int(run(['docker','exec',pg['Id'],'id','-g','postgres']).strip())}
    private_json(target/'runtime-image.json',{'image_id':pg['Image'],'configured_image':pg['Config']['Image'],
                                            'command':pg['Config']['Cmd'],'postgres_account':owner})
    session=subprocess.Popen(['docker','exec','-i',pg['Id'],'psql','-X','-qAt','-U','supabase_admin','-d','postgres','-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        session.stdin.write(b'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n');session.stdin.flush()
        snapshot=session.stdout.readline().decode().strip()
        if not snapshot or not all(c in '0123456789ABCDEFabcdef-' for c in snapshot):raise RuntimeError('Selfhost backup snapshot unavailable')
        session.stdin.write(SELFHOST_FINGERPRINT_SQL.encode()+b'\n');session.stdin.flush()
        expected=json.loads(session.stdout.readline())
        with (target/'postgres.dump').open('xb') as stream:
            run(['docker','exec',pg['Id'],'pg_dump','-U','supabase_admin','-d','postgres','--format=custom','--snapshot='+snapshot],stdout=stream,timeout=900)
            stream.flush();os.fsync(stream.fileno())
    finally:
        if session.poll() is None:
            session.stdin.close();session.wait(timeout=30)
    with (target/'roles.sql').open('xb') as stream:
        run(['docker','exec',pg['Id'],'pg_dumpall','-U','supabase_admin','--roles-only'],stdout=stream,timeout=180)
        stream.flush();os.fsync(stream.fileno())
    private_json(target/'source-fingerprint.json',expected)
    receipt=selfhost_restore(target,pg,expected)
    private_json(target/'restore-check.json',receipt)
    return {'enabled':True,'tables_verified':len(receipt['tables']),
            'dump_sha256':receipt['dump_sha256'],'restore_verified':True}


def host_cache_path(container_path):
    container_path=Path(container_path)
    if not container_path.is_absolute() or '..' in container_path.parts or not container_path.is_relative_to('/app/.local'):
        raise RuntimeError('Unsupported cache mount for backup')
    return ROOT/'.local/cache'/container_path.relative_to('/app/.local')


def configured_outboxes(cfg):
    """Return the two durable receipt directories on the host cache mount."""
    cache=Path(cfg.get('MEMORY_CACHE_DIR','/app/.local/projections'))
    question=Path(cfg.get('MEMORY_QA_OUTBOX',str(DEFAULT_QUESTION_OUTBOX)))
    if not question.is_absolute():
        question=Path('/app')/question
    return {'response-outbox':host_cache_path(cache)/'response-outbox',
            'question-outbox':host_cache_path(question)}


def return_restore_barrier_to_service(target):
    # This root-owned backup process atomically replaces the ledger.  Keep the
    # containing private directory and its two operational files writable by
    # the service account, which subsequently attests source deletions itself.
    lock=target.with_name('.'+target.name+'.lock')
    for path,mode,kind in ((target,0o600,'file'),(lock,0o600,'file'),(target.parent,0o700,'directory')):
        if path.is_symlink() or (not path.is_file() if kind=='file' else not path.is_dir()):
            raise RuntimeError('Restore barrier permissions target is invalid')
        os.chown(path,APP_UID,APP_GID)
        os.chmod(path,mode)


def persist_current_restore_barrier(store):
    space=store.space();owner=space.get('owner_id')
    if not isinstance(owner,str) or not owner:raise RuntimeError('Restore barrier owner is unavailable')
    target=host_cache_path(RESTORE_BARRIER)
    receipt=persist_restore_barrier(store,{'role':'owner','id':owner},target)
    return_restore_barrier_to_service(target)
    return receipt


def run(args,*,stdout=None,input=None,timeout=180):
    result=subprocess.run(args,input=input,stdout=stdout if stdout is not None else subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if result.returncode:
        private_json(ROOT/'.local'/('backup-command-error-'+secrets.token_hex(4)+'.json'),
                     {'command':args[:2],'returncode':result.returncode,'stderr':result.stderr.decode(errors='replace'),
                      'stdout':result.stdout.decode(errors='replace') if isinstance(result.stdout,bytes) else None})
        raise RuntimeError('Backup subprocess failed: '+Path(args[0]).name+' '+str(args[1])+' (exit '+str(result.returncode)+')')
    return result.stdout


def status(data):
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.backup-status-',dir=STATUS.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o600);os.chown(name,10001,10001);os.replace(name,STATUS)
    finally:
        try:os.unlink(name)
        except FileNotFoundError:pass


def env_file(path):
    result={}
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            key,value=line.split('=',1);result[key]=value
    return result


def container(name):return json.loads(run(['docker','inspect',name]))[0]


def restore_n8n(dump, n8n, postgres, directory):
    """No external network, no production volume, no workflow execution."""
    identifier='dashboard-restore-'+secrets.token_hex(6)
    network=identifier;pg=identifier+'-pg';cli=identifier+'-cli'
    password=secrets.token_hex(32);restored=Path(directory);restored.mkdir(mode=0o700)
    environment=dict(value.split('=',1) for value in n8n['Config']['Env'] if '=' in value)
    key=environment.get('N8N_ENCRYPTION_KEY')
    if not key:raise RuntimeError('n8n encryption key not available for restore check')
    pg_env=restored/'pg.env';pg_env.write_text('POSTGRES_USER=backup_owner\nPOSTGRES_DB=n8n\nPOSTGRES_PASSWORD='+password+'\n');pg_env.chmod(0o600)
    cli_env=restored/'n8n.env';cli_env.write_text('\n'.join([
      'N8N_USER_FOLDER=/home/node','DB_TYPE=postgresdb','DB_POSTGRESDB_HOST='+pg,'DB_POSTGRESDB_DATABASE=n8n','DB_POSTGRESDB_USER=backup_owner',
      'DB_POSTGRESDB_PASSWORD='+password,'N8N_ENCRYPTION_KEY='+key,'N8N_DIAGNOSTICS_ENABLED=false',
      'N8N_VERSION_NOTIFICATIONS_ENABLED=false','N8N_TEMPLATES_ENABLED=false','N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true'])+'\n');cli_env.chmod(0o600)
    (restored/'exports').mkdir(mode=0o700)
    # The shared n8n database outgrew the old 192 MiB tmpfs. Restore to a
    # private disposable disk directory, never a production Docker volume.
    # A compressed dump is not a useful upper bound for its restored size.
    database_bytes=int(run(['docker','exec',postgres['Id'],'psql','-U','n8n','-d','n8n','-Atc',
                            'select pg_database_size(current_database())']).strip())
    if shutil.disk_usage(restored).free < max(2_000_000_000,database_bytes*3):
        raise RuntimeError('Insufficient disk space for isolated n8n restore')
    pgdata=restored/'pgdata';pgdata.mkdir(mode=0o700)
    try:
        run(['docker','network','create','--internal',network])
        run(['docker','run','-d','--pull=never','--name',pg,'--network',network,'--memory=384m','--cpus=0.5',
             '--env-file',str(pg_env),'--mount','type=bind,source='+str(pgdata)+',target=/var/lib/postgresql/data',postgres['Image']])
        # The Docker entrypoint first starts a temporary socket-only server,
        # then stops it. Wait for TCP on the final server, otherwise restore can
        # connect during initialization and be disconnected by that restart.
        for attempt in range(120):
            result=subprocess.run(['docker','exec',pg,'pg_isready','-h','127.0.0.1','-U','backup_owner','-d','n8n'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if result.returncode==0:break
            time.sleep(.5)
        else:raise RuntimeError('Isolated restore database not ready')
        with Path(dump).open('rb') as stream:
            result=subprocess.run(['docker','exec','-i',pg,'pg_restore','-U','backup_owner','-d','n8n','--no-owner','--no-privileges','--exit-on-error'],stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600)
        if result.returncode:
            private_json(ROOT/'.local'/('backup-command-error-'+secrets.token_hex(4)+'.json'),{'command':['pg_restore'],'returncode':result.returncode,'stderr':result.stderr.decode(errors='replace')})
            raise RuntimeError('Isolated n8n restore failed')
        # Restored copy only. CLI export does not start triggers, and removing
        # published versions adds an independent guard against activation.
        run(['docker','exec',pg,'psql','-U','backup_owner','-d','n8n','-v','ON_ERROR_STOP=1','-c',
             'UPDATE workflow_entity SET active=false,"activeVersionId"=NULL; DELETE FROM workflow_published_version;'])
        counts=json.loads(run(['docker','exec',pg,'psql','-U','backup_owner','-d','n8n','-Atc',
            "select json_build_object('workflows',(select count(*) from workflow_entity),'credentials',(select count(*) from credentials_entity),'active',(select count(*) from workflow_entity where active),'published',(select count(*) from workflow_published_version))"]))
        run(['docker','run','--rm','--pull=never','--name',cli,'--network',network,'--memory=512m','--cpus=0.5','--user','0:0',
             '--read-only','--tmpfs','/tmp:rw,size=64m','--tmpfs','/home/node/.n8n:rw,size=32m','--env-file',str(cli_env),
             '--mount','type=bind,source='+str(restored/'exports')+',target=/exports',n8n['Image'],
             'export:credentials','--all','--decrypted','--output=/exports/credentials.json'],timeout=180)
        values=json.loads((restored/'exports/credentials.json').read_text())
        if len(values)!=counts['credentials'] or counts['active'] or counts['published']:raise RuntimeError('Isolated credential or activation check failed')
        google=next((v for v in values if v['id']=='a993APea0CMGhIL1'),None)
        if not google or not google.get('data',{}).get('oauthTokenData',{}).get('refresh_token'):raise RuntimeError('Drive refresh token missing in restored credentials')
        return {**counts,'credential_decryption_verified':True,'google_refresh_token_preserved':True,'external_network':False,'model_calls':0}
    finally:
        for name in (cli,pg):subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['docker','network','rm',network],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        shutil.rmtree(restored,ignore_errors=True)


def copy_outbox(source,destination):
    destination.mkdir(mode=0o700,exist_ok=True)
    if not source.exists():return
    for path in source.glob('*.json'):
        if path.is_symlink():raise RuntimeError('Unexpected outbox symlink')
        try:body=path.read_bytes()
        except FileNotFoundError:continue  # A settled response remains in Supabase.
        target=destination/path.name
        if target.exists() and target.read_bytes()!=body:raise RuntimeError('Outbox identity changed')
        if not target.exists():target.write_bytes(body);target.chmod(0o600)


def receipt_manifest(folder):
    outboxes={}
    for name in ('response-outbox','question-outbox'):
        directory=folder/name
        outboxes[name]=[{'name':path.name,'bytes':path.stat().st_size,'sha256':checksum(path)}
                        for path in sorted(directory.glob('*.json'))]
    private_json(folder/'receipt-manifest.json',{'format':'working-memory-receipts-v1','outboxes':outboxes})


def prune(now):
    # Keep 14 daily archives and the newest archive of each of eight weeks.
    files=sorted(BACKUPS.glob('dashboard-*.tar.gz'),reverse=True);keep=set(files[:14]);weeks=set()
    for path in files:
        stamp=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc);week=stamp.isocalendar()[:2]
        if week not in weeks and len(weeks)<8:keep.add(path);weeks.add(week)
    for path in files:
        if path not in keep and now-datetime.fromtimestamp(path.stat().st_mtime,timezone.utc)>timedelta(days=14):path.unlink()


def backup():
    os.umask(0o077);BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700);BACKUPS.chmod(0o700)
    started=datetime.now(timezone.utc);stamp=started.strftime('%Y%m%dT%H%M%SZ')
    previous=json.loads(STATUS.read_text()) if STATUS.exists() else {}
    report={'state':'running','started_at':started.isoformat(),'last_success_at':previous.get('last_success_at')}
    invocation=os.environ.get('INVOCATION_ID')
    if invocation is not None:
        if not re.fullmatch('[0-9a-f]{32}',invocation):raise RuntimeError('Invalid backup service invocation')
        report['invocation_id']=invocation
    status(report)
    folder=Path(tempfile.mkdtemp(prefix='.building-',dir=BACKUPS))
    artifact=BACKUPS/('dashboard-'+stamp+'.tar.gz');temporary=artifact.with_suffix('.partial')
    try:
        report['phase']='canonical_export'
        status(report)
        cfg=env_file(ROOT/'.local/service.env')
        report['phase']='selfhost_dump_restore'
        status(report)
        selfhost=backup_selfhost(folder,cfg)
        store=GatewayJournal(cfg['SUPABASE_URL'],cfg['SUPABASE_PUBLISHABLE_KEY'],cfg['MEMORY_JOURNAL_TOKEN'],cfg['MEMORY_SPACE_ID'])
        if previous.get('snapshot_cleanup_id'):
            store.call('backup_release',snapshot_id=previous['snapshot_cleanup_id'])
        outboxes=configured_outboxes(cfg)
        barrier={**persist_current_restore_barrier(store),'last_attested_at':datetime.now(timezone.utc).isoformat()}
        for name,path in outboxes.items():copy_outbox(path,folder/name)
        canonical=export(store,folder/'canonical')
        generate_restore(folder/'canonical',folder/'restore-paused.sql',restore_ledger=host_cache_path(RESTORE_BARRIER))
        for name,path in outboxes.items():copy_outbox(path,folder/name)
        receipt_manifest(folder)
        report['phase']='n8n_dump'
        status(report)
        n8n=container('n8n');pg=container('n8n_postgres')
        with (folder/'n8n.dump').open('xb') as stream:
            run(['docker','exec',pg['Id'],'pg_dump','-U','n8n','-d','n8n','--format=custom'],stdout=stream,timeout=180)
            stream.flush();os.fsync(stream.fileno())
        report['phase']='n8n_restore'
        status(report)
        n8n_restore=restore_n8n(folder/'n8n.dump',n8n,pg,folder/'isolated-restore')
        private_json(folder/'n8n-restore-check.json',n8n_restore)
        report['phase']='package'
        status(report)
        config=folder/'configuration';config.mkdir(mode=0o700)
        for source,name in [(ROOT/'.local/service.env','memory.env'),(ROOT/'compose.yaml','memory-compose.yaml'),
                            (Path('/opt/n8n/.env'),'n8n.env'),(Path('/opt/n8n/docker-compose.yml'),'n8n-compose.yaml')]:
            shutil.copy2(source,config/name);(config/name).chmod(0o600)
        code=folder/'runtime';code.mkdir(mode=0o700)
        manifest=json.loads((ROOT/'build-manifest.json').read_text())
        for name,h in manifest.items():
            path=ROOT/name
            if '..' in Path(name).parts or path.is_symlink() or checksum(path)!=h:raise RuntimeError('Deployed runtime manifest mismatch')
            target=code/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copy2(path,target)
        private_json(code/'build-manifest.json',manifest)
        for name in ('canonical_backup.py','canonical_restore.py','restore_outboxes.py','scheduled_backup.py','deletion_backup.py','deletion_ledger.py'):
            shutil.copy2(ROOT/name,code/name)
        schema=ROOT/'schema'
        if not schema.is_dir() or not list(schema.glob('*working_memory*.sql')):
            raise RuntimeError('Canonical restore schema not installed')
        for path in schema.glob('*.sql'):
            if path.is_symlink():raise RuntimeError('Unexpected schema symlink')
            target=folder/'schema'/path.name;target.parent.mkdir(mode=0o700,exist_ok=True);shutil.copy2(path,target)
        memory=container('dashboard-memory-canonical-draft-canonical-draft-1')
        private_json(folder/'runtime-images.json',{name:{'image_id':value['Image'],'configured_image':value['Config']['Image']} for name,value in [('n8n',n8n),('postgres',pg),('memory',memory)]})
        # The memory image is locally built. Its ID alone cannot restore a lost host.
        run(['docker','save','--output',str(folder/'memory-image.tar'),memory['Image']],timeout=600)
        mount=next(m['Source'] for m in n8n['Mounts'] if m['Destination']=='/home/node/.n8n')
        with tarfile.open(folder/'n8n-data.tar.gz','w:gz') as tar:tar.add(mount,arcname='n8n-data',filter=lambda info:None if info.name.endswith(('.log','.log.1')) else info)
        files={str(p.relative_to(folder)):{'bytes':p.stat().st_size,'sha256':checksum(p)} for p in folder.rglob('*') if p.is_file()}
        private_json(folder/'bundle-manifest.json',{'format':'dashboard-full-backup-v1','started_at':started.isoformat(),'files':files})
        with tarfile.open(temporary,'w:gz') as tar:
            for name in [*files,'bundle-manifest.json']:tar.add(folder/name,arcname=name)
        # Independently read the compressed bytes before advertising success.
        with tarfile.open(temporary) as tar:
            if set(tar.getnames())!=set(files)|{'bundle-manifest.json'}:raise RuntimeError('Backup package incomplete')
            for name,proof in files.items():
                h=hashlib.sha256();size=0
                with tar.extractfile(name) as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):h.update(block);size+=len(block)
                if size!=proof['bytes'] or h.hexdigest()!=proof['sha256']:raise RuntimeError('Backup package checksum mismatch')
        with temporary.open('rb') as stream:os.fsync(stream.fileno())
        os.replace(temporary,artifact)
        fd=os.open(BACKUPS,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        report.update(state='ok',finished_at=datetime.now(timezone.utc).isoformat(),last_success_at=datetime.now(timezone.utc).isoformat(),
                      archive=artifact.name,bytes=artifact.stat().st_size,sha256=checksum(artifact),canonical=canonical,n8n=n8n_restore,restore_barrier=barrier,selfhost=selfhost)
        status(report);prune(datetime.now(timezone.utc));return report
    except Exception as error:
        report.update(state='failed',finished_at=datetime.now(timezone.utc).isoformat(),error_type=type(error).__name__)
        if type(error) is RuntimeError:report['diagnostic']=str(error)[:300]
        if isinstance(error,TransientGateway):report['diagnostic']=str(error)[:300]
        request=folder/'canonical/request.json'
        if request.exists():
            snapshot_id=json.loads(request.read_text())['snapshot_id']
            try:store.call('backup_release',snapshot_id=snapshot_id)
            except Exception:report['snapshot_cleanup_id']=snapshot_id
        status(report);raise RuntimeError('Dashboard backup failed; prior verified archives retained') from None
    finally:
        shutil.rmtree(folder,ignore_errors=True)
        if temporary.exists():temporary.unlink()


def record_service_exit():
    """ExecStopPost only: record native failure for the same backup invocation."""
    result=os.environ.get('SERVICE_RESULT')
    if result=='success':return {'state':'unchanged','service_result':result}
    if result not in ('timeout','signal','oom-kill','exit-code','core-dump','watchdog','resources','protocol','start-limit-hit','exec-condition'):
        raise RuntimeError('Unknown backup service result')
    invocation=os.environ.get('INVOCATION_ID');code=os.environ.get('EXIT_CODE');exit_status=os.environ.get('EXIT_STATUS')
    if not isinstance(invocation,str) or not re.fullmatch('[0-9a-f]{32}',invocation):
        raise RuntimeError('Missing backup service invocation')
    if code not in ('exited','killed','dumped') or not isinstance(exit_status,str) or not re.fullmatch('[A-Za-z0-9]+',exit_status):
        raise RuntimeError('Missing backup service exit evidence')
    if code=='exited' and (not exit_status.isdigit() or not 0<=int(exit_status)<=255 or (result=='exit-code' and int(exit_status)==0)):
        raise RuntimeError('Invalid native failure exit status')
    with open(BACKUP_LOCK,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if STATUS.stat().st_size>16000:raise RuntimeError('Oversized backup status')
        report=json.loads(STATUS.read_text())
        if report.get('invocation_id')!=invocation or report.get('state') not in ('running','ok','failed'):
            raise RuntimeError('Backup service/status invocation mismatch')
        report.update(state='failed',finished_at=report.get('finished_at') or datetime.now(timezone.utc).isoformat(),
                      service_result=result,service_exit_code=code,service_exit_status=exit_status)
        report.setdefault('error_type','ServiceTermination')
        report.setdefault('diagnostic','Backup service ended without successful completion: '+result)
        status(report)
    return {'state':'failed','service_result':result,'invocation_id':invocation}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--service-exit-status',action='store_true');args=parser.parse_args()
    if args.service_exit_status:print(json.dumps(record_service_exit()))
    else:
        with open(BACKUP_LOCK,'w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=backup();print(json.dumps({k:v for k,v in result.items() if k in ('state','archive','bytes','sha256','canonical','n8n')}))
