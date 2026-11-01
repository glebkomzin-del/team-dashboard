"""Readonly reconciliation of completed freeze1 after verifier parsing failure; no mutations/retry."""
import argparse,json,os,shlex
from final_phase_common import *
from final_quiescence_once import state,empty,acl_query

def main():
    a=argparse.ArgumentParser();a.add_argument('--name',required=True);a.add_argument('--gate-receipt',required=True);v=a.parse_args();os.umask(0o077)
    local,remote=paths(v.name);gate_check(v.gate_receipt,v.name)
    failure=json.loads((local/'freeze-verifier-failure.json').read_text());assert failure['phase_attempt']==1 and failure['freeze_sql_executed'] and failure['final_dump_attempts']==0
    save(local/'readonly-freeze-reconciliation-attempt.json',{'read_only':True,'attempt':1,'source_mutations':0,'revoke_attempts_added':0})
    assert shell('docker inspect -f '+shlex.quote('{{.State.Running}}')+' '+CANONICAL).strip()==b'false'
    assert shell('cat /etc/nginx/sites-available/alexa')==(local/'nginx-maintenance.conf').read_bytes()
    paused=json.loads(shell('cat '+remote+'/n8n-pause-receipt.json'));assert paused['status']=='PASSED' and set(paused['changed'])=={'nzyaKxs5Om9wuPEc','dashboardDriveMove','dashboardDriveWatch'}
    assert int(n8n_sql('SELECT count(*) FROM workflow_entity WHERE id IN (\'nzyaKxs5Om9wuPEc\',\'dashboardDriveMove\',\'dashboardDriveWatch\') AND NOT active;').strip())==3
    final=state();assert empty(final)
    original=json.loads((local/'source-original-config-private.json').read_text());assert [{**r,'enabled':False} for r in original]==final['config']
    assert sql(acl_query())==[]
    # Broader than the original32-function set. OIDs come from pg_proc, never parameter-name casts.
    effective=sql("""SELECT r.rolname AS role,
      (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') AND has_table_privilege(r.rolname,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')) AS writable_tables,
      (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proowner='postgres'::regrole AND p.provolatile='v' AND p.prorettype<>'trigger'::regtype AND has_function_privilege(r.rolname,p.oid,'EXECUTE')) AS executable_writers
      FROM pg_roles r WHERE r.rolname IN ('anon','authenticated','service_role') ORDER BY r.rolname""")
    assert len(effective)==3 and all(not r['writable_tables'] and not r['executable_writers'] for r in effective)
    receipt={'status':'FROZEN','attempt':1,'run_dir':remote,'effective_privileges':effective,'post_stop_empty':True,'config_disabled':True,'ingress_maintenance':True,'source_password_unchanged':True,'runtime_enforcement':'RULES_ONLY','dump_attempts':0,'original_verifier_failure_preserved':True,'readonly_reconciliation_attempts':1,'revoke_attempts_added':0,'basis':'Original unchanged approved criteria established by broader actual effective-privilege query; no second freeze phase'}
    save(local/'freeze-receipt.json',receipt);save(local/'readonly-final-state-private.json',final);upload(local/'freeze-receipt.json',remote+'/freeze-receipt.json')
    print(json.dumps(receipt))
if __name__=='__main__':main()
