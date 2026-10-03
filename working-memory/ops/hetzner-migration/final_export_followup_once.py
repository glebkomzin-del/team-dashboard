"""Astra-approved single append-only credential followup; original export helper unchanged."""
import argparse,datetime,importlib.util,json,os,shutil
from final_phase_common import *
from final_quiescence_once import state,empty,acl_query

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args();os.umask(0o077)
    original,remote=paths(a.name);gate=gate_check(a.gate_receipt,a.name)
    assert gate['export_followup']['reviewer']=='/root/final_export_login_gate'
    assert gate['export_followup']['decision']=='CONTINUE_BOUNDED'
    assert gate['export_followup']['new_lease_budget']==1 and gate['export_followup']['dump_budget']==1
    lease=json.loads((original/'login-role.json').read_text())
    expiry=datetime.datetime.fromisoformat(lease['created_at'])+datetime.timedelta(seconds=lease['ttl_seconds'])
    assert datetime.datetime.now(datetime.timezone.utc)>expiry and not (original/'full.dump').exists()
    assert json.loads((original/'freeze-receipt.json').read_text())['status']=='FROZEN'
    assert empty(state()) and sql(acl_query())==[]
    local=original/'readonly-export-followup-1';local.mkdir(mode=0o700)
    save(local/'followup-budget.json',{'phase_id':'HZ-MIGRATION-20261003-FINAL-SOURCE-EXPORT','followup':1,'new_leases_max':1,'connections_max':1,'final_dump_max':1,'previous_final_leases':1,'previous_final_dumps':0,'original_lease_expired':True,'on_failure':'FOLLOWUP_FAILED and controlled Source rollback; no automatic further review/fix loop'})
    shutil.copyfile(original/'freeze-receipt.json',local/'freeze-receipt.json')
    spec=importlib.util.spec_from_file_location('original_final_export',HERE/'final_export_once.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    # Explicit reviewed continuation directory; never erase/reuse the expired login or prior markers.
    mod.paths=lambda name:(local,remote) if name==a.name else (_ for _ in ()).throw(AssertionError())
    try:
        mod.main()
        save(original/'export-followup-result.json',{'status':'FOLLOWUP_PASSED','final_leases_total':2,'final_dump_attempts_total':1,'private_export_dir':str(local),'original_failed_export_preserved':True})
    except BaseException as err:
        save(original/'export-followup-result.json',{'status':'FOLLOWUP_FAILED','final_leases_total':2 if (local/'login-role.json').exists() else 1,'final_dump_attempts_total':int((local/'full.dump').exists()),'failure_type':type(err).__name__,'original_failed_export_preserved':True})
        raise
if __name__=='__main__':main()
