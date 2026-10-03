"""Finalize only an existing archive after independent COPY-format judgment; zero Source access."""
import argparse,datetime,hashlib,json,os,re,shutil,subprocess
from final_phase_common import *

def copy_value(text):
    if text==r'\N':return None
    escapes={'n':'\n','r':'\r','t':'\t','b':'\b','f':'\f','v':'\v','\\':'\\'}
    return re.sub(r'\\(.)',lambda m:escapes[m[1]] if m[1] in escapes else (_ for _ in ()).throw(AssertionError('Unexpected COPY escape')),text)

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args();os.umask(0o077)
    original,remote=paths(a.name);gate=gate_check(a.gate_receipt,a.name)
    assert gate['offline_finalization']['decision']=='CONTINUE_BOUNDED' and gate['offline_finalization']['reviewer']=='/root/final_vault_copy_gate'
    local=original/'readonly-export-followup-1';save(local/'offline-finalization-attempt.json',{'attempt':1,'source_accesses':0,'new_leases':0,'new_dumps':0})
    assert json.loads((local/'dump-result.json').read_text())['returncode']==0 and json.loads((local/'roles-result.json').read_text())['returncode']==0
    assert not re.search(r'\bPASSWORD\s+',(local/'roles.sql').read_text(),re.I)
    role=json.loads((local/'role-validation.json').read_text());assert role['read_only']=='on' and role['current_user']=='supabase_read_only_user' and role['roles'][0]['bypassrls'] and not role['public_writable'] and role['public_tables']==role['public_readable'] and role['auth_tables']==role['auth_readable'] and role['frontend_tls_mode']=='verify-full'
    before=json.loads((local/'metadata-before-private.json').read_text());after=json.loads((local/'metadata-after-private.json').read_text());assert before==after and len(after['vault'])==1
    row=after['vault'][0];lines=(local/'vault-copy-private.sql').read_text().splitlines();header=next(l for l in lines if l.startswith('COPY vault.secrets '));columns=header.split('(',1)[1].split(')',1)[0].split(', ')
    data=[]
    for l in lines[lines.index(header)+1:]:
        if l==r'\.':break
        data.append(dict(zip(columns,map(copy_value,l.split('\t')))))
    assert len(data)==1
    for k in ['id','name','description']:assert data[0][k]==row[k]
    assert hashlib.sha256(data[0]['secret'].encode()).hexdigest()==row['cipher_sha256'] and data[0]['nonce']=='\\x'+row['nonce_hex']
    for k in ['created_at','updated_at']:assert datetime.datetime.fromisoformat(data[0][k])==datetime.datetime.fromisoformat(row[k])
    with (local/'archive-offline-final-check.stderr').open('xb') as err:
        r=subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(local/'full.dump')],stderr=err,timeout=600)
    assert r.returncode==0
    sha=digest(local/'full.dump');receipt={'status':'EXPORTED_AND_VALIDATED','run_dir':remote,'dump_sha256':sha,'dump_bytes':(local/'full.dump').stat().st_size,'final_readonly_leases_total':2,'final_dumps_total':1,'source_accesses_added':0,'archive_valid':True,'vault_cipher_nonce_metadata_archive_bound':True,'original_export_failure_and_followup_guard_failure_preserved':True,'offline_finalize_attempt':1}
    save(local/'final-export-receipt.json',receipt)
    off=Path.home()/'Library/Application Support/Dashboard Job Backup/hetzner-migration-20261003'/a.name;off.mkdir(mode=0o700)
    manifest={}
    for src in sorted(local.iterdir()):
        if src.is_file():
            dst=off/src.name
            with src.open('rb') as s,dst.open('xb') as d:shutil.copyfileobj(s,d,1048576)
            dst.chmod(0o600);assert digest(dst)==digest(src);manifest[src.name]=digest(src)
    for src in [original/'source-original-config-private.json',original/'gate.json',original/'freeze-verifier-failure.json',original/'export-followup-result.json']:
        dst=off/('original-'+src.name)
        with src.open('rb') as s,dst.open('xb') as d:shutil.copyfileobj(s,d)
        dst.chmod(0o600);assert digest(dst)==digest(src);manifest[dst.name]=digest(src)
    save(local/'offserver-receipt.json',{'all_files_equal':True,'dump_sha256':digest(off/'full.dump'),'files':manifest})
    for filename in ['full.dump','roles.sql','vault-plaintext.json','toc.txt','final-export-receipt.json','offserver-receipt.json']:upload(local/filename,remote+'/'+filename)
    assert shell('sha256sum '+remote+'/full.dump').decode().split()[0]==sha
    bound={**gate,'dump_sha256':sha,'derivation':'Actual offline-validated immutable export; future SHA not independently pre-reviewed'}
    save(local/'restore-gate-bound.json',bound);upload(local/'restore-gate-bound.json',remote+'/restore-gate-bound.json')
    save(original/'offline-finalization-result.json',{**receipt,'offserver_verified':True,'host_sha_verified':True})
    print(json.dumps({**receipt,'offserver_verified':True,'host_sha_verified':True}))
if __name__=='__main__':main()
