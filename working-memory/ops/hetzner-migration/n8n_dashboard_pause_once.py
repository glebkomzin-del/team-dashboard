"""Prepared only: targeted supported n8n API pause/resume, gated and immutable."""
import argparse,json,os,subprocess,urllib.request
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
ROOT=Path('/opt/dashboard-supabase-20261003')
VERSIONS={'nzyaKxs5Om9wuPEc':'d7211499-a941-4614-89e6-be6fb13f1f86','dashboardDriveMove':'74b389a7-0b56-4cfe-a7c1-720c5867d031','dashboardDriveWatch':'d0475768-b276-43b7-b5a2-67b7ceb13dce'}
def durable(run, name, value):
 fd=os.open(run/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as stream:
  json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
 fd=os.open(run,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)

def sequence(run, action, api):
 durable(run,'n8n-'+action+'-attempt.marker',{'single_sequence':True})
 receipt={'action':action,'status':'FAILED','changed':[],'attempted':[],'scope_key_unchanged':True}
 try:
  before={w:api(w) for w in VERSIONS}
  durable(run,'n8n-'+action+'-before-private.json',before)
  selected=list(VERSIONS)
  if action in ('resume-partial','inspect-partial'):
   selected=[w for w in VERSIONS if (run/('n8n-pause-'+w+'-attempt.json')).exists()]
  if action in ('resume-partial','inspect-partial'):
   for w in selected:
    assert json.loads((run/('n8n-pause-'+w+'-attempt.json')).read_text())=={'workflow':w,'version':VERSIONS[w],'before_active':True}
  for w,v in VERSIONS.items():
   actual=before[w]
   if action=='pause':assert actual['active'] and actual['activeVersionId']==v
   elif action=='resume':assert not actual['active']
   else:
    # An inactive original still carries its saved versionId; never activate a foreign edit.
    assert actual.get('versionId',actual.get('activeVersionId'))==v
    if actual['active']:assert actual['activeVersionId']==v
    elif w not in selected:raise RuntimeError('Unowned inactive workflow')
  for w in ([] if action=='inspect-partial' else selected):
   v=VERSIONS[w]
   if action in ('resume-partial','inspect-partial'):
    attempt=json.loads((run/('n8n-pause-'+w+'-attempt.json')).read_text())
    assert attempt=={'workflow':w,'version':v,'before_active':True}
    if before[w]['active']:continue
   durable(run,'n8n-'+action+'-'+w+'-attempt.json',{'workflow':w,'version':v,'before_active':before[w]['active']})
   receipt['attempted'].append(w)
   result=api(w,'/deactivate' if action=='pause' else '/activate',{} if action=='pause' else {'versionId':v})
   receipt['changed'].append(w)
   durable(run,w+'-'+action+'-private.json',result)
   actual=api(w)
   durable(run,'n8n-'+action+'-'+w+'-readback.json',actual)
   assert actual['active']==(action!='pause')
   if action!='pause':assert actual['activeVersionId']==v
  receipt['status']='PASSED'
 except Exception as err:receipt['failure']=private_error('n8n-sequence',err)
 finally:durable(run,'n8n-'+action+'-receipt.json',receipt)
 return receipt

def main():
 p=argparse.ArgumentParser();p.add_argument('--action',choices=['pause','resume','resume-partial','inspect-partial'],required=True);p.add_argument('--run-dir',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args();os.umask(0o077)
 run=Path(a.run_dir).resolve();global PRIVATE_ERRORS;PRIVATE_ERRORS=run/'private-errors';assert run.parent==ROOT and run.name.startswith('final-export-')
 gate=json.loads(Path(a.gate_receipt).read_text());assert gate['problem_id']=='HZ-MIGRATION-20261003-FINAL-CUTOVER' and gate['decision']=='CONTINUE_BOUNDED' and gate['run_dir']==str(run)
 key=json.loads((ROOT/'n8n-pause-access-1/existing-api-key-private.json').read_text())['apiKey']
 def api(w,op='',data=None):
  req=urllib.request.Request('http://127.0.0.1:5678/api/v1/workflows/'+w+op,headers={'X-N8N-API-KEY':key,'Content-Type':'application/json'},data=None if data is None else json.dumps(data).encode())
  body,_,_=http_read(req,operation='n8n-workflow-api',preserve_success=True);return json.loads(body)
 receipt=sequence(run,a.action,api)
 print(json.dumps(receipt))
 if receipt['status']!='PASSED':raise SystemExit(1)
if __name__=='__main__':main()
