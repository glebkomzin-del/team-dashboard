"""Prepared only: fresh gated final archive into exact disposable Stage, then COPY compare.
No source access, API resume, Vault rewrite, ACL grants or writer opening.
"""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');DB='dashboard-supabase-20261003-db-1'
def fp(proc):
 tables={};table=None
 for line in proc.stdout:
  if line.startswith(b'COPY ') and line.rstrip().endswith(b'FROM stdin;'):table=line.decode().split(' (',1)[0][5:];tables[table]=[]
  elif table is not None:
   if line.rstrip()==b'\\.':table=None
   else:tables[table].append(hashlib.sha256(line).digest())
 err=proc.stderr.read()
 if proc.wait():raise RuntimeError('Fingerprint failed; private diagnostic: '+err.decode()[:0])
 return {k:{'rows':len(v),'sha256':hashlib.sha256(b''.join(sorted(v))).hexdigest()} for k,v in tables.items()}
def main():
 a=argparse.ArgumentParser();a.add_argument('--run-dir',required=True);a.add_argument('--dump-sha256',required=True);a.add_argument('--gate-receipt',required=True);v=a.parse_args();os.umask(0o077)
 run=Path(v.run_dir).resolve();assert run.parent==ROOT and re.fullmatch(r'final-export-[0-9TZ-]+',run.name);assert re.fullmatch('[a-f0-9]{64}',v.dump_sha256)
 gate=json.loads(Path(v.gate_receipt).read_text());assert gate['problem_id']=='HZ-MIGRATION-20261003-FINAL-CUTOVER' and gate['decision']=='CONTINUE_BOUNDED' and gate['run_dir']==str(run) and gate['dump_sha256']==v.dump_sha256
 dump=run/'full.dump';h=hashlib.sha256()
 with dump.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 assert h.hexdigest()==v.dump_sha256
 marker=run/'final-restore-attempt.json';assert not marker.exists()
 db=json.loads(subprocess.check_output(['docker','inspect',DB]))[0];assert db['Config']['Labels']['com.docker.compose.project']=='dashboard-supabase-20261003';assert not any(db['NetworkSettings']['Ports'].values());assert list(db['NetworkSettings']['Networks'])==['dashboard-supabase-20261003_restore']
 def call(args,**kw):
  x=subprocess.run(args,capture_output=True,**kw)
  if x.returncode:(run/'restore-private.stderr').write_bytes(x.stderr);raise RuntimeError('Final restore operation failed '+args[0])
  return x.stdout
 marker.write_text(json.dumps({'phase':'final','attempt':1,'source_sha256':v.dump_sha256,'status':'running'}))
 call(['docker','compose','--env-file','.private.env','stop','auth','rest','api-gw','functions'],cwd=ROOT)
 def sql(q,db='postgres'):return call(['docker','exec','-i',DB,'psql','-U','supabase_admin','-d',db,'-XqAt','-v','ON_ERROR_STOP=1'],input=q.encode()).decode()
 existing=set(sql('SELECT rolname FROM pg_roles;').splitlines());roles=[]
 for line in (run/'roles.sql').read_text().splitlines():
  if 'cli_login_' in line:continue
  assert not re.search(r'\bPASSWORD\s+',line,re.I),'No infrastructure password overwrite'
  m=re.fullmatch(r'CREATE ROLE ([a-z_]+);',line)
  if m and m.group(1) in existing:continue
  roles.append(line)
 sql('\n'.join(roles));sql('DROP DATABASE postgres WITH (FORCE);\nCREATE DATABASE postgres OWNER postgres TEMPLATE template0;','template1')
 with dump.open('rb') as source:call(['docker','exec','-i',DB,'pg_restore','-U','supabase_admin','-d','postgres','--exit-on-error','--verbose'],stdin=source,timeout=900)
 with dump.open('rb') as source:
  left=fp(subprocess.Popen(['docker','exec','-i',DB,'pg_restore','--data-only','--file=-'],stdin=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE))
 right=fp(subprocess.Popen(['docker','exec',DB,'pg_dump','-U','supabase_admin','-d','postgres','--data-only'],stdout=subprocess.PIPE,stderr=subprocess.PIPE))
 diffs={k:{'source':x,'target':right.get(k)} for k,x in left.items() if x!=right.get(k)}
 result={'source_sha256':v.dump_sha256,'source_tables':len(left),'source_rows':sum(x['rows'] for x in left.values()),'mismatches':diffs,'source':left,'target':right,'comparison_before_auth_vault_acl':True}
 (run/'final-snapshot-comparison.json').write_text(json.dumps(result,indent=2));assert not diffs
 marker.write_text(json.dumps({'phase':'final','attempt':1,'source_sha256':v.dump_sha256,'status':'COPY_COMPARE_PASSED_SERVICES_STOPPED'}));print(json.dumps({'source_tables':len(left),'source_rows':result['source_rows'],'equal':True,'services_resumed':False}))
if __name__=='__main__':main()
