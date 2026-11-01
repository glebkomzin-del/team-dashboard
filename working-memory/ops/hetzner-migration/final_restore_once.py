"""Prepared only: fresh gated final archive into exact disposable Stage, then COPY compare.
No source access, API resume, Vault rewrite, ACL grants or writer opening.
"""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path

# Failure captures are private and append-only; outward messages contain no payloads.
import base64 as _b64, uuid as _uuid
import urllib.request
PRIVATE_ERRORS = Path('/private/tmp/hz-final-protocol-private-errors')
def private_error(operation, error=None, *, directory=None, stdout=None, stderr=None, body=None, status=None, headers=None, method=None):
    directory = Path(directory) if directory is not None else PRIVATE_ERRORS
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise RuntimeError('Unsafe private diagnostic directory') from None
    def encoded(value):
        if value is None: return None
        return _b64.b64encode(value.encode() if isinstance(value, str) else value).decode('ascii')
    record = {'operation': operation, 'exception_type': type(error).__name__ if error else None,
              'exception_text': str(error) if error else None, 'stdout_b64': encoded(stdout),
              'stderr_b64': encoded(stderr), 'body_b64': encoded(body), 'status': status,
              'headers': list(headers.items()) if headers is not None else None, 'method': method}
    path = directory / (_uuid.uuid4().hex + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(record, stream); stream.flush(); os.fsync(stream.fileno())
    return {'kind': type(error).__name__ if error else 'ProcessFailure', 'private_path': str(path), 'operation': operation}
def safe_failure(receipt):
    return RuntimeError(json.dumps(receipt))
def run_process(args, *, operation, private_errors=None, **kw):
    try:
        result = subprocess.run(args, capture_output=True, **kw)
    except Exception as error:
        receipt = private_error(operation, error, directory=private_errors,
                                stdout=getattr(error, 'stdout', None), stderr=getattr(error, 'stderr', None))
        raise safe_failure(receipt) from None
    if result.returncode:
        receipt = private_error(operation, directory=private_errors, stdout=result.stdout,
                                stderr=result.stderr, status=result.returncode)
        raise safe_failure(receipt) from None
    return result.stdout

def http_read(request, *, operation, private_errors=None, timeout=30, preserve_success=False):
    method = request.get_method() if hasattr(request, 'get_method') else 'GET'
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(); status = response.status; headers = response.headers
            if preserve_success:
                private_error(operation, directory=private_errors, body=body, status=status, headers=headers, method=method)
            return body, status, headers
    except Exception as error:
        body = None
        if hasattr(error, 'read'):
            try: body = error.read()
            except Exception as read_error:
                private_error(operation, read_error, directory=private_errors)
        receipt = private_error(operation, error, directory=private_errors, body=body,
                                status=getattr(error, 'code', None), headers=getattr(error, 'headers', None), method=method)
        raise safe_failure(receipt) from None
ROOT=Path('/opt/dashboard-supabase-20261003');DB='dashboard-supabase-20261003-db-1'
def start_process(args, **kw):
 try:return subprocess.Popen(args, **kw)
 except Exception as error:
  raise safe_failure(private_error('restore-fingerprint-start',error)) from None
def fp(proc, private_errors=None):
 # Drain both pipes concurrently, preserving the exact stream without keeping a dump in memory.
 import tempfile, threading
 tables={};table=None
 with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
  def drain():
   for chunk in iter(lambda:proc.stderr.read(65536),b''):errors.write(chunk)
  thread=threading.Thread(target=drain);thread.start()
  try:
   for line in proc.stdout:
    output.write(line)
    if line.startswith(b'COPY ') and line.rstrip().endswith(b'FROM stdin;'):table=line.decode().split(' (',1)[0][5:];tables[table]=[]
    elif table is not None:
     if line.rstrip()==b'\\.':table=None
     else:tables[table].append(hashlib.sha256(line).digest())
   status=proc.wait();thread.join()
  except Exception as error:
   thread.join();output.seek(0);errors.seek(0)
   raise safe_failure(private_error('restore-fingerprint',error,directory=private_errors,stdout=output.read(),stderr=errors.read())) from None
  if status:
   output.seek(0);errors.seek(0)
   raise safe_failure(private_error('restore-fingerprint',directory=private_errors,stdout=output.read(),stderr=errors.read(),status=status)) from None
 return {k:{'rows':len(v),'sha256':hashlib.sha256(b''.join(sorted(v))).hexdigest()} for k,v in tables.items()}
def main():
 a=argparse.ArgumentParser();a.add_argument('--run-dir',required=True);a.add_argument('--dump-sha256',required=True);a.add_argument('--gate-receipt',required=True);v=a.parse_args();os.umask(0o077)
 run=Path(v.run_dir).resolve();global PRIVATE_ERRORS;PRIVATE_ERRORS=run/'private-errors';assert run.parent==ROOT and re.fullmatch(r'final-export-[0-9TZ-]+',run.name);assert re.fullmatch('[a-f0-9]{64}',v.dump_sha256)
 gate=json.loads(Path(v.gate_receipt).read_text());assert gate['problem_id']=='HZ-MIGRATION-20261003-FINAL-CUTOVER' and gate['decision']=='CONTINUE_BOUNDED' and gate['run_dir']==str(run) and gate['dump_sha256']==v.dump_sha256
 dump=run/'full.dump';h=hashlib.sha256()
 with dump.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 assert h.hexdigest()==v.dump_sha256
 marker=run/'final-restore-attempt.json';assert not marker.exists()
 db=json.loads(run_process(['docker','inspect',DB],operation='restore-container-inspect'))[0];assert db['Config']['Labels']['com.docker.compose.project']=='dashboard-supabase-20261003';assert not any(db['NetworkSettings']['Ports'].values());assert list(db['NetworkSettings']['Networks'])==['dashboard-supabase-20261003_restore']
 def call(args,**kw):return run_process(args,operation='restore-process',**kw)
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
  left=fp(start_process(['docker','exec','-i',DB,'pg_restore','--data-only','--file=-'],stdin=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE),private_errors=run/'private-errors')
 right=fp(start_process(['docker','exec',DB,'pg_dump','-U','supabase_admin','-d','postgres','--data-only'],stdout=subprocess.PIPE,stderr=subprocess.PIPE),private_errors=run/'private-errors')
 diffs={k:{'source':x,'target':right.get(k)} for k,x in left.items() if x!=right.get(k)}
 result={'source_sha256':v.dump_sha256,'source_tables':len(left),'source_rows':sum(x['rows'] for x in left.values()),'mismatches':diffs,'source':left,'target':right,'comparison_before_auth_vault_acl':True}
 (run/'final-snapshot-comparison.json').write_text(json.dumps(result,indent=2));assert not diffs
 marker.write_text(json.dumps({'phase':'final','attempt':1,'source_sha256':v.dump_sha256,'status':'COPY_COMPARE_PASSED_SERVICES_STOPPED'}));print(json.dumps({'source_tables':len(left),'source_rows':result['source_rows'],'equal':True,'services_resumed':False}))
if __name__=='__main__':main()
