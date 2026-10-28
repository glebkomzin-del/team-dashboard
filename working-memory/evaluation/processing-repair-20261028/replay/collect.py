"""Read-only export of code and bounded saved replay inputs; no credentials."""
import io,json,os,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'private';PRIVATE.mkdir(exist_ok=True,mode=0o700);os.chmod(PRIVATE,0o700)
SSH=['ssh','-i','/Users/glebkomzin/.ssh/id_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','root@178.105.167.26']
def remote(command,input=None):
 return subprocess.check_output(SSH+[command],input=input,timeout=120)
def query(sql):
 value=remote('docker exec -i dashboard-supabase-20261003-db-1 psql -U postgres -d postgres -XqAt -v ON_ERROR_STOP=1',('BEGIN READ ONLY;\n'+sql+'\nCOMMIT;').encode())
 return json.loads(value)
code="""import tarfile,sys,pathlib
p=pathlib.Path('/app')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for f in sorted(p.glob('*.py')):t.add(f,arcname=str(f.relative_to(p)))
 for d in ['schema','evaluation']:
  for f in sorted((p/d).rglob('*')):
   if f.is_file() and f.suffix in ('.sql','.json','.txt') and len(f.relative_to(p).parts)==2:t.add(f,arcname=str(f.relative_to(p)))
"""
raw=remote("docker exec -i dashboard-memory-canonical-draft-canonical-draft-1 python3 -",code.encode())
with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
 for member in archive.getmembers():
  assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
 archive.extractall(PRIVATE/'runtime',filter='data')
parts={
 'spaces':"SELECT coalesce(json_agg(t),'[]') FROM (SELECT * FROM wm_spaces) t;",
 'entries':"SELECT coalesce(json_agg(t ORDER BY revision),'[]') FROM (SELECT * FROM wm_journal WHERE revision<=314) t;",
 'sources':"SELECT coalesce(json_agg(t),'[]') FROM (SELECT * FROM wm_source_versions WHERE id IN (SELECT source_version FROM wm_journal WHERE revision<=314 AND source_version IS NOT NULL)) t;",
 'jobs':"SELECT coalesce(json_agg(t),'[]') FROM (SELECT j.*,row_to_json(d) document FROM wm_jobs j JOIN wm_archive_documents d ON d.id=j.document_id AND d.space_id=j.space_id WHERE j.id LIKE '7b4057c2%' OR j.id LIKE 'a77d73b4%') t;",
 'calls':"SELECT coalesce(json_agg(t ORDER BY job_id,call_index),'[]') FROM (SELECT * FROM wm_model_calls WHERE job_id LIKE '7b4057c2%' OR job_id LIKE 'a77d73b4%') t;",
}
result={k:query(v) for k,v in parts.items()}
path=PRIVATE/'inputs.json';path.write_text(json.dumps(result));path.chmod(0o600)
print(json.dumps({k:len(v) for k,v in result.items()}))
