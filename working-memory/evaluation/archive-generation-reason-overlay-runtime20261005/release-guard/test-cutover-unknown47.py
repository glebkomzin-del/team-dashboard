#!/usr/bin/env python3
"""Disposable PostgreSQL missing/unknown receipt guard; never uses production DB."""
import json
import subprocess
from pathlib import Path
ROOT=Path('/root/dashboard-archive-generation-reason-overlay-stage-20261005')
CONTAINER='dashboard-archive47-cutover-test-20261005'
NEW='v11:compact1:gate1:gpt-5.6-terra:25995eec984cca1d:canonical1:7c67663689250e1c'
OLD='v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c'
SPACE='96a2dc44-9b9e-4644-b236-c5c1956cd39d'
def sql(source):
    return subprocess.run(['docker','exec','-i',CONTAINER,'psql','-U','postgres','-d','postgres',
                           '-AtX','-v','ON_ERROR_STOP=1','-v','apply=true','-f','-'],
                          input=source,text=True,capture_output=True)
for name,value in [('missing','missing'),('null',None),('positive_unknown',1)]:
    assert sql((ROOT/'isolated-cutover-fixture.sql').read_text()).returncode==0
    base=sql((ROOT/'capture-inventory.sql').read_text())
    assert base.returncode==0,base.stderr
    p=json.loads(base.stdout)
    assert p['unknown_receipt_count']==0
    if value=='missing': del p['unknown_receipt_count']
    else: p['unknown_receipt_count']=value
    raw=json.dumps(p).encode()
    template=(ROOT/'cutover-template.sql').read_text()
    rendered=template.replace('__SNAPSHOT_HEX__',raw.hex()).replace('__NEW_PIPELINE__',NEW)
    result=sql(rendered)
    assert result.returncode!=0,(name,result.stdout,result.stderr)
    assert sql(f"select pipeline from public.wm_processing_config where space_id='{SPACE}';").stdout.strip()==OLD
    assert sql(f"select count(*) from public.wm_job_decisions where space_id='{SPACE}';").stdout.strip()=='0'
    print(name,'DENY')
