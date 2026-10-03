"""Private final-phase transport; no operations run on import."""
import base64, hashlib, json, os, re, shlex, subprocess, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIVATE = HERE.parents[1] / '.local/hetzner-migration-20261003'
SERVER = '/opt/dashboard-supabase-20261003'
PROJECT = 'lghwikeotbkmojyyjglz'
CANONICAL = 'dashboard-memory-canonical-draft-canonical-draft-1'
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

def shell(command, data=None, timeout=60):
    r = subprocess.run(SSH+[command], input=data, capture_output=True, timeout=timeout)
    if r.returncode: raise RuntimeError('Remote operation failed; no automatic retry')
    return r.stdout

def sql(query):
    token = subprocess.run(['/usr/bin/security','find-generic-password','-s','Supabase CLI',
                            '-a','supabase','-w'], capture_output=True, text=True, check=True).stdout.strip()
    if token.startswith('go-keyring-base64:'): token=base64.b64decode(token.split(':',1)[1]).decode()
    req=urllib.request.Request('https://api.supabase.com/v1/projects/'+PROJECT+'/database/query',
        data=json.dumps({'query':query}).encode(), headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=45) as response: return json.load(response)
    except Exception: raise RuntimeError('Source SQL unavailable; no retry/escalation') from None

def literal(value): return "'"+str(value).replace("'","''")+"'"

def paths(name):
    assert re.fullmatch(r'final-export-[0-9TZ-]+',name)
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
