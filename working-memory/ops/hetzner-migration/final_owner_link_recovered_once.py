"""Existing official Owner flow, gated on genuine RecoveredRuntime provenance.

No Runtime PASS synthesis, browser automation, email, reset or user creation.
The original helper remains the sole Auth implementation and writes its real receipt.
Root separately owns one loopback303/SDK flow and overview/archive/summary/original
production read-only acceptance; those criteria remain pending here.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import final_owner_link_once as original

spec=importlib.util.spec_from_file_location('frontend_final_control',Path(__file__).with_name('frontend-final-promote-control-once.py'))
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

def _owner_run(value):
    # Inspect the lexical path first: resolve() must never hide a symlink.
    run=Path(value)
    control.require(run.is_absolute() and not any(p.is_symlink() for p in (run,*run.parents)),
                    'Unsafe actual Owner run')
    control.require(run.is_dir() and run.stat().st_mode&0o777==0o700 and
                    run.parent==original.ROOT and run==run.resolve(),'Unsafe actual Owner run')
    return run

def _save_owner_attempt(run,value):
    run=_owner_run(run)
    directory_fd=os.open(run,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        opened=os.fstat(directory_fd);expected=run.stat()
        control.require((opened.st_dev,opened.st_ino)==(expected.st_dev,expected.st_ino) and
                        opened.st_mode&0o777==0o700,'Unsafe actual Owner run')
        fd=os.open('owner-recovered-control-attempt.marker',
                   os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory_fd)
        with os.fdopen(fd,'wb') as stream:
            stream.write(json.dumps(value,sort_keys=True).encode()+b'\n')
            stream.flush();os.fsync(stream.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

def execute(run,gate_path,now=None):
    run=_owner_run(run);gate,values,data,_=control.load(gate_path,'OWNER',now)
    control.require(str(run)==gate['run_dir'] and run.parent==original.ROOT and not run.is_symlink() and
                    run.is_dir() and run.stat().st_mode&0o077==0,'Unsafe actual Owner run')
    control.require(control.raw(run/'target-runtime-receipt.json')==values['runtime_projection'] and
                    control.raw(run/'target-runtime-permissions-receipt.json')==values['runtime_recovery'],
                    'Actual operational files differ from bound recovery')
    cfg=dict(l.split('=',1) for l in (original.LIVE/'.local/service.env').read_text().splitlines() if l and not l.startswith('#'))
    control.require(all(cfg.get(k)==v for k,v in original.CLOSED_FLAGS.items()) and
                    cfg['MEMORY_ALLOWED_USERS'].split(',')==data['live']['allowed_users'],'Live original requirements not met')
    control.require(not any((run/n).exists() or (run/n).is_symlink() for n in ('writer-open-attempt.marker','owner-magiclink-attempt.marker','owner-link-receipt.json',
                    'owner-recovered-control-attempt.marker')),'Owner/writer already attempted')
    directory=control.private_dir(run/'owner-recovered-control-private')
    try:
        _save_owner_attempt(run,{'problem_id':control.PROBLEM,'owner_links':1,'automatic_retries':0,
                 'gate_sha256':control.digest(gate_path),'runtime_recovery_sha256':control.sha(values['runtime_recovery']),
                 'runtime_projection_sha256':control.sha(values['runtime_projection']),'original_runtime_attempt_status':'FAILED',
                 'original_error_sha256':control.sha(values['runtime_error'])})
    except Exception as error:
        control.save(directory/('marker-error-'+uuid.uuid4().hex+'.json'),
                     {'type':type(error).__name__,'cause':str(error),'auth_started':False})
        raise
    # Capture raw SQL/process success as well as failures before original JSON checks.
    def captured_process(args,*,operation,private_errors=None,**kw):
        record={'operation':operation,'exit_code':None,'stdout_b64':None,'stderr_b64':None,'timeout':False}
        try:
            result=subprocess.run(args,capture_output=True,**kw)
            record.update(exit_code=result.returncode,stdout_b64=control.enc(result.stdout),stderr_b64=control.enc(result.stderr))
        except Exception as error:
            record.update(error_type=type(error).__name__,cause=str(error),timeout=isinstance(error,subprocess.TimeoutExpired),
                          stdout_b64=control.enc(getattr(error,'stdout',None)),stderr_b64=control.enc(getattr(error,'stderr',None)))
            control.save(directory/('process-'+uuid.uuid4().hex+'.json'),record)
            raise RuntimeError('Owner process ambiguous; primary retained') from None
        control.save(directory/('process-'+uuid.uuid4().hex+'.json'),record)
        control.require(result.returncode==0,'Owner process failed; primary retained');return result.stdout
    old_process,old_http,old_errors=original.run_process,original.http_read,original.PRIVATE_ERRORS
    def captured_http(request,**kw):
        kw.update(private_errors=directory,preserve_success=True)
        return old_http(request,**kw)
    stdout,stderr=io.StringIO(),io.StringIO();old_args=sys.argv
    try:
        original.run_process=captured_process;original.http_read=captured_http;original.PRIVATE_ERRORS=directory
        sys.argv=[str(Path(original.__file__)),'--run-dir',str(run),'--production-owner-go','HZ-MIGRATION-20261003-FINAL-FRONTEND']
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):original.main()
        # No reconstructed future receipt: read only the original helper's actual result.
        actual=control.raw(run/'owner-link-receipt.json');receipt=json.loads(actual)
        control.require(receipt['http']==200 and receipt['official_admin_existing_owner'] is True and
                        receipt['owner_password_hash_unchanged'] is True and receipt['redirect']==original.REDIRECT and
                        receipt['generated_links']==1 and receipt['mail_requests']==0 and receipt['source_auth_changes']==0 and
                        receipt['production_browser_proof_pending'] is True and
                        control.sha(control.raw(run/'owner-original-action-link-private.txt'))==receipt['action_link_original_sha256'],
                        'Actual official Owner receipt differs')
        control.require(control.raw(run/'target-runtime-receipt.json')==values['runtime_projection'] and
                        control.raw(run/'target-runtime-permissions-receipt.json')==values['runtime_recovery'],'Runtime changed during link flow')
        control.save(directory/'actual-owner-link-binding.json',{'actual_owner_receipt_sha256':control.sha(actual),
                     'runtime_recovery_sha256':control.sha(values['runtime_recovery']),
                     'runtime_projection_sha256':control.sha(values['runtime_projection']),
                     'original_runtime_attempt_status':'FAILED','original_error_sha256':control.sha(values['runtime_error']),
                     'gate_sha256':control.digest(gate_path),'production_browser_proof_pending':True})
        return receipt
    except Exception as error:
        control.save(directory/'primary-error.json',{'type':type(error).__name__,'cause':str(error)})
        raise RuntimeError('Owner stopped; original intent and private primaries retained; no retry') from None
    finally:
        control.save(directory/'original-output.json',{'stdout_b64':control.enc(stdout.getvalue()),'stderr_b64':control.enc(stderr.getvalue())})
        original.run_process,original.http_read,original.PRIVATE_ERRORS=old_process,old_http,old_errors;sys.argv=old_args

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args()
    os.umask(0o077);result=execute(a.run_dir,a.gate_receipt)
    print(json.dumps({'generated_links':result['generated_links'],'production_browser_proof_pending':True}))
if __name__=='__main__':main()
