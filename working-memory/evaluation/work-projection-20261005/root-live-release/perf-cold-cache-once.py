from pathlib import Path
import json,hashlib,sqlite3,shutil,os,datetime,subprocess
base=Path('/opt/dashboard-memory-canonical-draft/.local/cache/projections-rc1-20260919')
p=base/'96a2dc44-9b9e-4644-b236-c5c1956cd39d-226.sqlite'
d=Path('/root/dashboard-perf-cold-226-20261005')
image=subprocess.check_output(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1','--format','{{.Image}} {{.State.Health.Status}}'],text=True).strip()
assert image=='sha256:5d5986089ce0824b53d530fd35ffe329eada90eb075c5b217f21e3966456bb52 healthy'
assert p.is_file() and not p.is_symlink() and not d.exists()
assert not any(Path(str(p)+x).exists() for x in ['-wal','-shm','-journal'])
con=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
assert con.execute('pragma integrity_check').fetchone()[0]=='ok'
assert con.execute('pragma journal_mode').fetchone()[0]=='delete'
tables=[r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]
assert len(tables)==12
counts={name:con.execute('select count(*) from "'+name+'"').fetchone()[0] for name in tables};con.close()
h=lambda q:hashlib.sha256(q.read_bytes()).hexdigest();old_sha=h(p)
d.mkdir(mode=0o700);copy=d/'before-226.sqlite';shutil.copy2(p,copy);copy.chmod(0o600);assert h(copy)==old_sha
assert os.stat(p.parent).st_dev==os.stat(d).st_dev
assert h(p)==old_sha and not any(Path(str(p)+x).exists() for x in ['-wal','-shm','-journal'])
proof={'image':image,'before_sha256':old_sha,'before_bytes':p.stat().st_size,'table_counts':counts,'nginx_access_start_offset':Path('/var/log/nginx/access.log').stat().st_size,'renamed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_path':str(p),'copy_path':str(copy),'original_data_changed':False}
os.rename(p,d/'original-derived-226.sqlite')
proof['rename_completed_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();proof['cache_absent_immediately_after_rename']=not p.exists()
(d/'cold-start.json').write_text(json.dumps(proof,sort_keys=True,indent=2)+'\n');(d/'cold-start.json').chmod(0o600)
print(json.dumps(proof,sort_keys=True))
