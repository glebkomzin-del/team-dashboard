"""Hash-bound installation/rollback; preserves unrelated manifest entries and env."""
import argparse, fcntl, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path('/opt/dashboard-memory-canonical-draft')
BASELINE='0ce536a2fb4980ab27ad72b621b5d3819491aa61b0150db9d544e5c4ea90a95b'
CANDIDATE='58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9'
ROLLBACK=ROOT/'.local/backup-adapter-rollback-HZ20261003'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def replace(path,body):
    info=path.stat();fd,name=tempfile.mkstemp(prefix='.adapter-install-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
        os.chown(name,info.st_uid,info.st_gid);os.chmod(name,info.st_mode&0o777);os.replace(name,path)
    finally:
        if Path(name).exists():Path(name).unlink()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--patch');parser.add_argument('--rollback',action='store_true');args=parser.parse_args()
    if args.rollback==bool(args.patch):raise SystemExit('Choose --patch or --rollback')
    os.umask(0o077)
    with open('/run/lock/dashboard-job-backup.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if subprocess.check_output(['systemctl','show','dashboard-job-backup.service','-p','MainPID','--value']).strip()!=b'0':raise SystemExit('Backup service is active')
        script=ROOT/'scheduled_backup.py';manifest_path=ROOT/'build-manifest.json';manifest=json.loads(manifest_path.read_text())
        expected=CANDIDATE if args.rollback else BASELINE
        if digest(script)!=expected or manifest.get('scheduled_backup.py')!=expected:raise SystemExit('Live script or manifest differs; no replacement')
        if args.rollback:
            marker=ROOT/'.local/selfhost-backup.json'
            cfg=dict(line.split('=',1) for line in (ROOT/'.local/service.env').read_text().splitlines() if line and not line.startswith('#'))
            if (marker.exists() and json.loads(marker.read_text()).get('enabled')) or not (urlparse(cfg.get('SUPABASE_URL','')).hostname or '').endswith('.supabase.co'):
                raise SystemExit('Script-only rollback requires Hosted origin and inactive selfhost marker')
            source=ROLLBACK/'scheduled_backup.py'
            if digest(source)!=BASELINE:raise SystemExit('Rollback script hash mismatch')
            body=source.read_bytes();destination_hash=BASELINE
        else:
            with tempfile.TemporaryDirectory(dir='/var/backups/dashboard-job') as directory:
                staged=Path(directory)/'scheduled_backup.py';shutil.copy2(script,staged)
                subprocess.run(['patch','--batch','-s','-p2','-d',directory,'-i',str(Path(args.patch).resolve())],check=True)
                if digest(staged)!=CANDIDATE:raise SystemExit('Patched script hash mismatch')
                body=staged.read_bytes()
            ROLLBACK.mkdir(mode=0o700)
            for source in (script,manifest_path):
                target=ROLLBACK/source.name;shutil.copy2(source,target);target.chmod(0o600)
            destination_hash=CANDIDATE
        # Preserve every foreign manifest entry; rollback also changes only this
        # script's entry, rather than restoring a stale whole-manifest snapshot.
        manifest['scheduled_backup.py']=destination_hash
        replace(script,body)
        replace(manifest_path,(json.dumps(manifest,indent=2)+'\n').encode())
        print(json.dumps({'script_sha256':digest(script),'manifest_sha256':digest(manifest_path),
                         'scheduled_manifest_entry':manifest['scheduled_backup.py'],'rollback':args.rollback,
                         'activation_marker_changed':False,'environment_changed':False}))

if __name__=='__main__':main()
