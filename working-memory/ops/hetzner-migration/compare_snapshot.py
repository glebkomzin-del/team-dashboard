"""Compare COPY rows without logging private values; source is immutable archive."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/'.local/hetzner-migration-20261003/source'

def fingerprint(command):
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    tables={}; table=None
    for line in proc.stdout:
        if line.startswith(b'COPY ') and line.rstrip().endswith(b'FROM stdin;'):
            table=line.decode().split(' (',1)[0][5:];tables[table]=[]
        elif table is not None:
            if line.rstrip()==b'\\.':table=None
            else:tables[table].append(hashlib.sha256(line).digest())
    err=proc.stderr.read();code=proc.wait()
    if code:raise RuntimeError('Private fingerprint subprocess failed')
    return {name:{'rows':len(rows),'sha256':hashlib.sha256(b''.join(sorted(rows))).hexdigest()} for name,rows in tables.items()}

def main():
    os.umask(0o077)
    source=fingerprint(['pg_restore','--data-only','--file=-',str(ROOT/'full.dump')])
    target=fingerprint(['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@178.105.167.26','docker exec dashboard-supabase-20261003-db-1 pg_dump -U supabase_admin -d postgres --data-only'])
    # Extension configuration tables follow the archive contract; target dump may
    # include independently generated extension housekeeping tables.
    diff={name:{'source':value,'target':target.get(name)} for name,value in source.items() if value!=target.get(name)}
    result={'source_tables':len(source),'source_rows':sum(v['rows'] for v in source.values()),'mismatches':diff,'source':source,'target':target,'source_archive_sha256':'4e3574cedb2858f3022f931202581cdea4f43f611e068d8ffecde1c7e1f1bea1'}
    out=ROOT/'snapshot-comparison.json';out.write_text(json.dumps(result,indent=2));out.chmod(0o600)
    print(json.dumps({'source_tables':len(source),'source_rows':result['source_rows'],'mismatched_tables':list(diff),'equal':not diff}))
    if diff:raise SystemExit(1)
if __name__=='__main__':main()
