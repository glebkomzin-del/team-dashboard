"""One final readonly lease/export after verified freeze; never overwrites initial evidence."""
import argparse, base64, importlib.util, json, os, shutil, subprocess, urllib.request
from final_phase_common import *
from vault_copy_codec import verify_vault_copy

def metadata():
    vault=sql("SELECT s.id,s.name,s.description,s.key_id,s.created_at,s.updated_at,encode(s.nonce,'hex') AS nonce_hex,encode(extensions.digest(s.secret,'sha256'),'hex') AS cipher_sha256,v.decrypted_secret FROM vault.secrets s JOIN vault.decrypted_secrets v USING(id) ORDER BY s.id")
    token=source_token()
    req=urllib.request.Request('https://api.supabase.com/v1/projects/'+PROJECT+'/functions',headers={'Authorization':'Bearer '+token})
    try:
        with urllib.request.urlopen(req,timeout=30) as r:edge=json.load(r)
    except urllib.error.HTTPError as error:
        raise private_failure('EDGE_HTTP_ERROR',status=error.code,body=error.read(),headers=str(error.headers)) from None
    except Exception as error:
        raise private_failure('EDGE_REQUEST_ERROR',error_type=type(error).__name__,primary_error=str(error)) from None
    edge=sorted(edge,key=lambda x:x['slug'])
    queue=sql('SELECT (SELECT count(*) FROM cron.job WHERE active) AS active_cron,(SELECT count(*) FROM net.http_request_queue) AS queued_http')
    assert len(vault)==1 and len(edge)==11 and queue[0]['active_cron']==0 and queue[0]['queued_http']==0
    return {'vault':vault,'edge':edge,'queues':queue}

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args();os.umask(0o077)
    local,remote=paths(a.name);gate=gate_check(a.gate_receipt,a.name)
    freeze=json.loads((local/'freeze-receipt.json').read_text());assert freeze['status']=='FROZEN' and freeze['run_dir']==remote
    assert shell('docker inspect -f '+__import__('shlex').quote('{{.State.Running}}')+' '+CANONICAL).strip()==b'false'
    save(local/'final-export-attempt.json',{'attempt':1,'lease_budget':1,'dump_budget':1})
    assert not (local/'login-role.json').exists() and not (local/'full.dump').exists()
    os.environ['PATH']='/opt/homebrew/bin:'+os.environ['PATH']
    assert '17.10' in subprocess.check_output(['pg_dump','--version']).decode()
    before=metadata();save(local/'metadata-before-private.json',before)
    shutil.copyfile(PRIVATE/'source/prod-ca-2021.crt',local/'prod-ca-2021.crt')
    spec=importlib.util.spec_from_file_location('verified_source_export',HERE/'export_source.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.ROOT=local;mod.main()
    assert json.loads((local/'dump-result.json').read_text())['returncode']==0
    assert json.loads((local/'roles-result.json').read_text())['returncode']==0
    role=json.loads((local/'role-validation.json').read_text())
    assert role['roles'][0]['bypassrls'] and role['read_only']=='on' and role['public_writable']==0
    with (local/'full.dump').open('rb') as archive: assert archive.read(5)==b'PGDMP'
    toc=subprocess.run(['pg_restore','--list',str(local/'full.dump')],capture_output=True,check=True).stdout
    (local/'toc.txt').write_bytes(toc)
    with (local/'archive-validation-private.stderr').open('xb') as err:
        result=subprocess.run(['pg_restore','--file=/dev/null',str(local/'full.dump')],stderr=err,timeout=600)
    assert result.returncode==0
    after=metadata();save(local/'metadata-after-private.json',after);assert before==after
    save(local/'vault-plaintext.json',after['vault'])
    # The sidecar must match the actual archive's original Vault cipher and nonce, not just wall-clock reads.
    vault_sql=subprocess.check_output(['pg_restore','--data-only','--schema=vault','--table=secrets','--file=-',str(local/'full.dump')])
    (local/'vault-copy-private.sql').write_bytes(vault_sql)
    verify_vault_copy(vault_sql.decode('utf-8'),after['vault'])
    h=digest(local/'full.dump');receipt={'status':'EXPORTED_AND_VALIDATED','run_dir':remote,'dump_sha256':h,'dump_bytes':(local/'full.dump').stat().st_size,'new_readonly_leases':1,'new_dump_attempts':1,'archive_valid':True,'vault_archive_bound':True,'edge_metadata_unchanged':True,'source_frozen':True,'roles_no_passwords':True,'dump_pg_version':'17.10'}
    save(local/'final-export-receipt.json',receipt)
    # Immutable independent Mac copy before target replacement; verify all copied private files.
    off=Path.home()/'Library/Application Support/Dashboard Job Backup/hetzner-migration-20261003'/a.name
    off.mkdir(mode=0o700)
    for src in sorted(local.iterdir()):
        if src.is_file():
            dst=off/src.name
            with src.open('rb') as s,dst.open('xb') as d:shutil.copyfileobj(s,d,1048576)
            dst.chmod(0o600);assert digest(dst)==digest(src)
    save(local/'offserver-receipt.json',{'all_files_equal':True,'dump_sha256':digest(off/'full.dump'),'file_count':len(list(off.iterdir()))})
    for filename in ['full.dump','roles.sql','vault-plaintext.json','toc.txt','final-export-receipt.json','offserver-receipt.json']:
        upload(local/filename,remote+'/'+filename)
    assert shell('sha256sum '+remote+'/full.dump').decode().split()[0]==h
    # Derived future-hash binding references the reviewed protocol; not a second fabricated review.
    bound={**gate,'dump_sha256':h,'derivation':'Reviewed final protocol + actual immutable export receipt; future SHA not independently pre-reviewed'}
    save(local/'restore-gate-bound.json',bound);upload(local/'restore-gate-bound.json',remote+'/restore-gate-bound.json')
    print(json.dumps({**receipt,'offserver_verified':True,'server_dump_verified':True}))

if __name__=='__main__':main()
