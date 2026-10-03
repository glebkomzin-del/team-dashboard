"""Controlled original Source recovery after explicit reviewer BLOCK; never restores stale target data."""
import argparse,json,os,shlex
from final_phase_common import *
from final_quiescence_once import acl_query,state

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args();os.umask(0o077)
    local,remote=paths(a.name);gate_check(a.gate_receipt,a.name)
    save(local/'source-rollback-attempt.json',{'attempt':1,'reason':'Explicit final_vault_copy_gate BLOCK; original FOLLOWUP_FAILED stop requires source recovery','target_final_restore_attempts':0})
    assert shell('test ! -e '+remote+'/final-restore-attempt.json && test ! -e '+remote+'/target-runtime-attempt.marker && test ! -e /opt/dashboard-memory-canonical-draft/.local/selfhost-backup.json')==b''
    code="import json;from pathlib import Path;d=dict(l.split('=',1) for l in Path('/opt/dashboard-memory-canonical-draft/.local/service.env').read_text().splitlines() if l and not l.startswith('#'));assert d['SUPABASE_URL'].rstrip('/')=='https://lghwikeotbkmojyyjglz.supabase.co';print(json.dumps({k:d[k] for k in ['MEMORY_READ_ONLY','MEMORY_INTAKE_ENABLED','MEMORY_AUTOMATIC_ENABLED']}))"
    flags=json.loads(shell('python3 -c '+shlex.quote(code)));assert flags=={'MEMORY_READ_ONLY':'0','MEMORY_INTAKE_ENABLED':'1','MEMORY_AUTOMATIC_ENABLED':'1'}
    assert shell('docker inspect -f '+shlex.quote('{{.Image}}')+' '+CANONICAL).strip()==b'sha256:15a6a820f9d887fac5f0bcd3e2dd29c477d4d5f6a7e82db41bb83cd899f43a2f'
    assert shell('cat /etc/nginx/sites-available/alexa')==(local/'nginx-maintenance.conf').read_bytes()
    assert not sql(acl_query())
    restore=HERE/'freeze-business-restore-acl.sql';assert digest(restore)=='26c34f43afa8408e933589b6ce705bf09bd3e36234904de81166b26dd1955f02'
    sql(restore.read_text());assert sql(acl_query())==json.loads((PRIVATE/'source/freeze-business-original-acl.json').read_text())
    original=json.loads((local/'source-original-config-private.json').read_text());cfg=state()['config'];assert cfg==[{**r,'enabled':False} for r in original]
    for r in original:sql('UPDATE public.wm_processing_config SET enabled='+('true' if r['enabled'] else 'false')+' WHERE space_id='+literal(r['space_id'])+'::uuid;')
    assert state()['config']==original
    shell('docker start '+CANONICAL)
    # Public ingress returns only after original Source health, preserving all unrelated Nginx blocks.
    code="""import json,time,urllib.request
end=time.monotonic()+90
while True:
 try:
  with urllib.request.urlopen('http://127.0.0.1:8798/health',timeout=5) as r:v=json.load(r)
  print(json.dumps(v));break
 except Exception:
  if time.monotonic()>end:raise RuntimeError('Source runtime not healthy')
  time.sleep(2)"""
    health=json.loads(shell('python3 -c '+shlex.quote(code),timeout=100))
    shell('cp '+remote+'/nginx-original.conf /etc/nginx/sites-available/alexa && nginx -t && systemctl reload nginx')
    resumed=json.loads(shell('python3 '+remote+'/n8n_dashboard_pause_once.py --action resume --run-dir '+remote+' --gate-receipt '+remote+'/gate.json'));assert resumed['status']=='PASSED'
    restore_scope=PRIVATE/'current-evidence/n8n-scope-plan-1/restore-scopes.sql';assert digest(restore_scope)=='c1fa6235bdee05964f84e3e06521278f7ffcdd463340e8d2bb2644d9492d589a'
    n8n_sql(restore_scope.read_text())
    key=json.loads((PRIVATE/'current-evidence/n8n-pause-access-1/existing-api-key-private.json').read_text())
    actual_scopes=json.loads(n8n_sql('SELECT scopes FROM user_api_keys WHERE id='+literal(key['id'])+';'));assert actual_scopes==key['scopes']
    actual_nginx=shell('sha256sum /etc/nginx/sites-available/alexa').decode().split()[0];assert actual_nginx=='7cfba8642673162a182f67926bc26dbb0def8bdafecd7952e7ee5c524511fe51'
    receipt={'status':'SOURCE_OPERATING_STATE_RESTORED','source_acl_exact_original':True,'source_config_exact_original':True,'source_runtime_original_image_env':True,'original_flags':flags,'original_three_n8n_versions_restored':True,'api_key_original_scopes_restored':True,'nginx_exact_original_sha256':actual_nginx,'health':health,'target_final_restore':False,'frontend_production_switched':False,'source_password_reset':False,'migration_complete':False}
    save(local/'source-rollback-receipt.json',receipt);upload(local/'source-rollback-receipt.json',remote+'/source-rollback-receipt.json');print(json.dumps(receipt))
if __name__=='__main__':main()
