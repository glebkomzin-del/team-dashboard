#!/usr/bin/env python3
"""Disposable PostgreSQL-only contract test; never connects to the live DB."""
import json
import subprocess
from pathlib import Path

ROOT = Path('/root/dashboard-archive-overlay-stage-20261005')
CONTAINER = 'dashboard-archive-cutover-test-20261005'
BASE = 'v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c'
NEW = 'v11:compact1:gate1:gpt-5.6-terra:25995eec984cca1d:canonical1:7c67663689250e1c'
SPACE = '96a2dc44-9b9e-4644-b236-c5c1956cd39d'


def sql(source, *, apply=False):
    completed = subprocess.run(['docker','exec','-i',CONTAINER,'psql','-U','postgres','-d','postgres',
                                '-AtX','-v','ON_ERROR_STOP=1','-v',f'apply={str(apply).lower()}','-f','-'],
                               input=source,text=True,capture_output=True)
    return completed.returncode, completed.stdout, completed.stderr


def must(source):
    code,out,err = sql(source)
    if code:
        raise AssertionError(f'isolated setup/query failed: {err}')
    return out.strip()


inspect = json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
host = inspect['HostConfig']
assert host['NetworkMode']=='none' and host['Memory']==536870912 and host['NanoCpus']==1000000000
assert not inspect['NetworkSettings']['Ports'] and not host.get('Mounts')
assert inspect['Image']=='sha256:a9946f08d31e8eb1149229c94e5c26603a9233116807cbbd93d75179cbac516a'
fixture=(ROOT/'isolated-cutover-fixture.sql').read_text()
capture=(ROOT/'capture-inventory.sql').read_text()
template=(ROOT/'cutover-template.sql').read_text()
assert template.count('__SNAPSHOT_HEX__')==template.count('__NEW_PIPELINE__')==1

mutations={
    'positive':None,
    'changed_cohort':f"insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state) values('{SPACE}',repeat('e',64),'doc-e','source-e','2026-10-03','{BASE}','queued');",
    'running':f"update public.wm_jobs set state='running' where space_id='{SPACE}' and id=repeat('a',64);",
    'unknown_paid':f"insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd) values('{SPACE}',repeat('a',64),0,'{{}}',repeat('3',64),10);",
    'stale_revision':f"update public.wm_spaces set revision=227 where id='{SPACE}';",
    'config_wrong':f"update public.wm_processing_config set pipeline='wrong' where space_id='{SPACE}';",
}

for case,mutation in mutations.items():
    must(fixture)
    raw=must(capture)
    snapshot=json.loads(raw)
    assert snapshot['queue_all_unstarted'] and snapshot['running_count']==0
    assert len(snapshot['queued'])==2 and snapshot['call_count']==1
    if mutation: must(mutation)
    rendered=template.replace('__SNAPSHOT_HEX__',raw.encode().hex()).replace('__NEW_PIPELINE__',NEW)
    code,out,err=sql(rendered,apply=True)
    after=json.loads(must(capture))
    decisions=int(must(f"select count(*) from public.wm_job_decisions where space_id='{SPACE}';"))
    paid=int(must(f"select count(*) from public.wm_jobs where space_id='{SPACE}' and state in ('applied','archived') and pipeline='{BASE}';"))
    retargeted=int(must(f"select count(*) from public.wm_jobs where space_id='{SPACE}' and state='queued' and pipeline='{NEW}';"))
    if case=='positive':
        assert code==0,(out,err)
        assert 'ARCHIVE_OVERLAY_CUTOVER_VALID' in out and 'COMMIT' in out,(out,err)
        assert after['pipeline']==NEW and after['enabled'] is False
        assert after['call_hash']==snapshot['call_hash'] and after['nonqueued_job_hash']==snapshot['nonqueued_job_hash']
        assert (decisions,paid,retargeted)==(2,2,2),(decisions,paid,retargeted)
    else:
        assert code!=0,(case,out,err)
        assert after['pipeline']!=NEW and (decisions,paid,retargeted)==(0,2,0),(case,decisions,paid,retargeted)
    print(json.dumps({'case':case,'psql_exit':code,'decision_rows':decisions,'paid_or_archived_preserved':paid,
                      'retargeted_unpaid_queued':retargeted,'error_tail':err.strip().splitlines()[-1] if err.strip() else None},sort_keys=True))

for case,mutation in {
    'running_at_capture':f"update public.wm_jobs set state='running' where space_id='{SPACE}' and id=repeat('a',64);",
    'unknown_paid_at_capture':f"insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd) values('{SPACE}',repeat('a',64),0,'{{}}',repeat('3',64),10);",
    'empty_queue_at_capture':f"update public.wm_jobs set state='archived' where space_id='{SPACE}' and state='queued';",
}.items():
    must(fixture)
    must(mutation)
    raw=must(capture)
    snapshot=json.loads(raw)
    rendered=template.replace('__SNAPSHOT_HEX__',raw.encode().hex()).replace('__NEW_PIPELINE__',NEW)
    code,out,err=sql(rendered,apply=True)
    assert code!=0,(case,out,err)
    assert must(f"select pipeline from public.wm_processing_config where space_id='{SPACE}';")==BASE
    assert must(f"select count(*) from public.wm_job_decisions where space_id='{SPACE}';")=='0'
    assert must(f"select count(*) from public.wm_jobs where space_id='{SPACE}' and pipeline='{NEW}';")=='0'
    print(json.dumps({'case':case,'psql_exit':code,'running_count':snapshot['running_count'],
                      'queue_all_unstarted':snapshot['queue_all_unstarted'],'queued_count':len(snapshot['queued']),
                      'retargeted_jobs':0},sort_keys=True))
