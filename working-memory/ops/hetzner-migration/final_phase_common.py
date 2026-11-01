"""Private final-phase transport; no operations run on import."""
import base64, hashlib, json, os, re, shlex, subprocess, urllib.request, urllib.error, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIVATE = HERE.parents[1] / '.local/hetzner-migration-20261003'
SERVER = '/opt/dashboard-supabase-20261003'
PROJECT = 'lghwikeotbkmojyyjglz'
CANONICAL = 'dashboard-memory-canonical-draft-canonical-draft-1'
ERROR_DIR = PRIVATE/'current-evidence/resume-source-transport-errors'
SSH = ['ssh', '-i', str(Path.home()/'.ssh/id_ed25519'), '-o', 'IdentitiesOnly=yes',
       '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=12', 'root@178.105.167.26']

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def save(path, value):
    with Path(path).open('x') as f: json.dump(value, f, indent=2)
    Path(path).chmod(0o600)

def private_failure(kind, **details):
    """Append an immutable private primary error; return only safe type/path."""
    ERROR_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    ERROR_DIR.chmod(0o700)
    path=ERROR_DIR/(kind+'-'+uuid.uuid4().hex+'.json')
    encoded={key: {'base64':base64.b64encode(value).decode()} if isinstance(value,bytes) else value
             for key,value in details.items()}
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump({'kind':kind,**encoded},stream,indent=2)
    return RuntimeError(kind+'; private primary error: '+str(path)+'; no automatic retry')

def source_token():
    try:
        result=subprocess.run(['/usr/bin/security','find-generic-password','-s','Supabase CLI',
                               '-a','supabase','-w'],capture_output=True,text=True,timeout=30)
    except subprocess.TimeoutExpired as error:
        raise private_failure('KEYCHAIN_TIMEOUT',stdout=error.stdout,stderr=error.stderr) from None
    if result.returncode:
        raise private_failure('KEYCHAIN_ERROR',returncode=result.returncode,stdout=result.stdout,stderr=result.stderr) from None
    token=result.stdout.strip()
    try:
        if token.startswith('go-keyring-base64:'):token=base64.b64decode(token.split(':',1)[1],validate=True).decode()
    except Exception as error:
        raise private_failure('KEYCHAIN_DECODE_ERROR',error_type=type(error).__name__,primary_error=str(error)) from None
    return token

def shell(command, data=None, timeout=60):
    try:r = subprocess.run(SSH+[command], input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise private_failure('SSH_TIMEOUT',stdout=error.stdout,stderr=error.stderr) from None
    if r.returncode: raise private_failure('SSH_ERROR',returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
    return r.stdout

def sql(query):
    token = source_token()
    req=urllib.request.Request('https://api.supabase.com/v1/projects/'+PROJECT+'/database/query',
        data=json.dumps({'query':query}).encode(), headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=45) as response: return json.load(response)
    except urllib.error.HTTPError as error:
        raise private_failure('SOURCE_HTTP_ERROR',status=error.code,body=error.read(),headers=str(error.headers)) from None
    except Exception as error:
        raise private_failure('SOURCE_REQUEST_ERROR',error_type=type(error).__name__,primary_error=str(error)) from None

def literal(value): return "'"+str(value).replace("'","''")+"'"

def paths(name):
    global ERROR_DIR
    assert re.fullmatch(r'final-export-[0-9TZ-]+',name)
    ERROR_DIR=PRIVATE/name/'transport-errors'
    return PRIVATE/name, SERVER+'/'+name

def gate_check(path, name):
    gate=json.loads(Path(path).read_text()); local, remote=paths(name)
    assert gate['problem_id']=='HZ-MIGRATION-20261003-FINAL-CUTOVER'
    assert gate['decision']=='CONTINUE_BOUNDED' and gate['run_dir']==remote
    for file, expected in gate['script_hashes'].items(): assert digest(HERE/file)==expected
    return gate

def upload(local, remote):
    shell('test ! -e '+shlex.quote(remote)+' && umask 077 && cat > '+shlex.quote(remote),Path(local).read_bytes())

def n8n_sql(query):
    return shell('docker exec -i n8n_postgres psql -U n8n -d n8n -XqAt -v ON_ERROR_STOP=1',query.encode()).decode()
