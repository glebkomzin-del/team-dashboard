"""Pull verified Dashboard Job archives to the owner's Mac; no model or DB writes."""
from datetime import datetime,timezone
import fcntl,hashlib,json,os,re,subprocess,tarfile,tempfile
from pathlib import Path
from deletion_ledger import read as read_deletion_ledger,write as write_deletion_ledger

HOST='root@178.105.167.26'
REMOTE='/var/backups/dashboard-job/'
ROOT=Path('/Users/glebkomzin/Library/Application Support/Dashboard Job Backup')
COPIES=ROOT/'archives'
BARRIER=ROOT/'restore-barrier'/'deletions.json'
REMOTE_BARRIER='/opt/dashboard-memory-canonical-draft/.local/cache/restore-barrier/deletions.json'
NAME=re.compile(r'dashboard-\d{8}T\d{6}Z\.tar\.gz\Z')
REMOTE_LIST=r'''import hashlib,json,re
from pathlib import Path
p=Path('/var/backups/dashboard-job')
a=sorted((f for f in p.iterdir() if re.fullmatch(r'dashboard-\d{8}T\d{6}Z\.tar\.gz',f.name) and f.is_file() and not f.is_symlink()),reverse=True)
if not a:raise SystemExit('No verified archive available')
f=a[0];h=hashlib.sha256()
with f.open('rb') as s:
 for b in iter(lambda:s.read(1048576),b''):h.update(b)
print(json.dumps({'archive':f.name,'bytes':f.stat().st_size,'sha256':h.hexdigest()}))
'''
REMOTE_RECEIPT=r'''import json,os,re,tempfile
from datetime import datetime
from pathlib import Path
x=json.load(__import__('sys').stdin)
if set(x)!={'state','last_success_at','last_backup_at','archive','sha256','bytes','target'} or x['state']!='ok' or x['target']!='owner_mac':raise SystemExit('Invalid receipt')
if not re.fullmatch(r'dashboard-\d{8}T\d{6}Z\.tar\.gz',x['archive']) or not re.fullmatch('[0-9a-f]{64}',x['sha256']) or type(x['bytes']) is not int or x['bytes']<=0:raise SystemExit('Invalid archive receipt')
if any(not datetime.fromisoformat(x[k]).tzinfo for k in ('last_success_at','last_backup_at')):raise SystemExit('Invalid receipt time')
p=Path('/opt/dashboard-memory-canonical-draft/.local/cache/offserver-backup-status.json')
f,n=tempfile.mkstemp(prefix='.offserver-',dir=p.parent)
with os.fdopen(f,'w') as s:json.dump(x,s);s.flush();os.fsync(s.fileno())
os.chmod(n,0o600);os.chown(n,10001,10001);os.replace(n,p)
'''


def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(1048576),b''):h.update(block)
 return h.hexdigest()


def verify_bundle(path):
 with tarfile.open(path,'r:gz') as tar:
  members=tar.getmembers();names=[m.name for m in members]
  if len(names)!=len(set(names)) or any(not m.isfile() for m in members):raise ValueError('Invalid archive entries')
  if any(Path(name).is_absolute() or '..' in Path(name).parts for name in names):raise ValueError('Invalid archive path')
  info=tar.getmember('bundle-manifest.json')
  if info.size>4_000_000:raise ValueError('Oversized archive manifest')
  with tar.extractfile(info) as stream:manifest=json.load(stream)
  if manifest.get('format')!='dashboard-full-backup-v1' or set(names)!=set(manifest['files'])|{'bundle-manifest.json'}:raise ValueError('Incomplete archive')
  for name,proof in manifest['files'].items():
   info=tar.getmember(name)
   if info.size!=proof['bytes']:raise ValueError('Archive entry size changed')
   h=hashlib.sha256()
   with tar.extractfile(info) as stream:
    for block in iter(lambda:stream.read(1048576),b''):h.update(block)
   if h.hexdigest()!=proof['sha256']:raise ValueError('Archive entry checksum changed')
 return {'files_verified':len(manifest['files'])}


def run(args,*,input=None,timeout=180):
 result=subprocess.run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if result.returncode:raise RuntimeError('Secure backup transfer unavailable (exit '+str(result.returncode)+')')
 return result.stdout


def ssh_code(code,input=None):
 import shlex
 return run(['/usr/bin/ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST,'python3 -c '+shlex.quote(code)],input=input)


def save_status(value):
 fd,name=tempfile.mkstemp(prefix='.status-',dir=ROOT)
 try:
  with os.fdopen(fd,'w') as stream:json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
  os.chmod(name,0o600);os.replace(name,ROOT/'status.json')
 finally:
  if Path(name).exists():Path(name).unlink()


def persist_restore_barrier_copy(source,target=BARRIER):
 raw=json.loads(Path(source).read_text())
 if not isinstance(raw,dict) or not isinstance(raw.get('space_id'),str) or not raw['space_id']:
  raise ValueError('Invalid remote restore barrier')
 ledger=read_deletion_ledger(source,space_id=raw['space_id'])
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.parent.chmod(0o700)
 saved=write_deletion_ledger(target,space_id=ledger['space_id'],minimum_deletion_revision=ledger['minimum_deletion_revision'],
  deletions=ledger['deletions'],observed_at=ledger['observed_at'])
 return {'minimum_deletion_revision':saved['minimum_deletion_revision'],'ledger_observed_at':saved['observed_at'],
  'restore_ledger_persisted':True}


def pull_restore_barrier():
 ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd,name=tempfile.mkstemp(prefix='.restore-barrier-',dir=ROOT);os.close(fd);temporary=Path(name)
 try:
  run(['/usr/bin/scp','-q','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST+':'+REMOTE_BARRIER,str(temporary)],timeout=180)
  with temporary.open('rb') as stream:os.fsync(stream.fileno())
  return {**persist_restore_barrier_copy(temporary,BARRIER),'last_copied_at':datetime.now(timezone.utc).isoformat()}
 finally:
  if temporary.exists():temporary.unlink()


def pull():
 os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True,mode=0o700);ROOT.chmod(0o700);COPIES.mkdir(exist_ok=True,mode=0o700)
 with (ROOT/'lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  previous=json.loads((ROOT/'status.json').read_text()) if (ROOT/'status.json').exists() else {}
  report={'state':'running','started_at':datetime.now(timezone.utc).isoformat(),'last_success_at':previous.get('last_success_at')}
  save_status(report);temporary=None
  try:
   source=json.loads(ssh_code(REMOTE_LIST));name=source['archive']
   if set(source)!={'archive','bytes','sha256'} or not NAME.fullmatch(name) or type(source['bytes']) is not int or source['bytes']<=0 or not re.fullmatch('[0-9a-f]{64}',source['sha256']):raise ValueError('Invalid remote backup identity')
   target=COPIES/name
   if target.is_symlink():raise ValueError('Unexpected local backup symlink')
   if target.exists() and (target.stat().st_size!=source['bytes'] or digest(target)!=source['sha256']):raise ValueError('Existing local backup changed; previous copy retained for inspection')
   if not target.exists():
    fd,path=tempfile.mkstemp(prefix='.download-',dir=COPIES);os.close(fd);temporary=Path(path)
    run(['/usr/bin/scp','-q','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST+':'+REMOTE+name,str(temporary)],timeout=600)
    if temporary.stat().st_size!=source['bytes'] or digest(temporary)!=source['sha256']:raise ValueError('Downloaded backup checksum mismatch')
    proof=verify_bundle(temporary)
    with temporary.open('rb') as stream:os.fsync(stream.fileno())
    temporary.chmod(0o600);os.replace(temporary,target);temporary=None
    fd=os.open(COPIES,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
   else:proof=verify_bundle(target)
   barrier=pull_restore_barrier()
   now=datetime.now(timezone.utc).isoformat();receipt={'state':'ok','last_success_at':now,'last_backup_at':datetime.strptime(name,'dashboard-%Y%m%dT%H%M%SZ.tar.gz').replace(tzinfo=timezone.utc).isoformat(),**source,'target':'owner_mac'}
   # A small fixed-path receipt lets the application show the second-copy state;
   # no archive data, private local paths or credentials are sent back.
   ssh_code(REMOTE_RECEIPT,input=json.dumps(receipt).encode())
   report.update(receipt,**proof,restore_barrier=barrier,finished_at=now);save_status(report)
   return report
  except Exception as error:
   report.update(state='failed',finished_at=datetime.now(timezone.utc).isoformat(),error_type=type(error).__name__)
   save_status(report);raise
  finally:
   if temporary and temporary.exists():temporary.unlink()

if __name__=='__main__':
 try:
  result=pull();print(json.dumps({k:result[k] for k in ('state','archive','last_success_at','files_verified')}))
 except Exception as error:
  print(json.dumps({'state':'failed','error_type':type(error).__name__}));raise SystemExit(1)
