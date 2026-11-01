#!/usr/bin/env python3
"""Synthetic renderer contract only; bypasses release prerequisites in memory."""
import hashlib
import importlib.machinery
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/root/dashboard-archive-generation-reason-overlay-stage-20261005')
r = importlib.machinery.SourceFileLoader('renderer47test', str(ROOT/'render-cutover.py')).load_module()
r.require_release = lambda *a: None
r.require_drain = lambda *a: None
r.require_deployed_image = lambda *a: None
rows = [{'id': f'{i:064x}', 'updated_at': '2026-10-05T20:00:00+00:00'} for i in range(1,60)]
p = {'schema_version':1, 'captured_at':datetime.now(timezone.utc).isoformat(),
     'space_id':r.SPACE, 'revision':226, 'pipeline':r.OLD, 'enabled':False,
     'queue_all_unstarted':True, 'running_count':0, 'owner_id':'owner', 'space_state':'active',
     'job_count':59, 'call_count':4, 'job_hash':'a'*64, 'nonqueued_job_hash':'b'*64,
     'call_hash':'c'*64, 'queued':rows, 'unknown_receipt_count':0}
with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    for name,value,passes in [('zero',0,True),('positive',1,False),('missing','missing',False),('null',None,False)]:
        case=dict(p)
        if value=='missing': del case['unknown_receipt_count']
        else: case['unknown_receipt_count']=value
        snap=t/(name+'.json'); snap.write_text(json.dumps(case))
        out=t/(name+'.sql')
        try:
            result=r.render(snap,hashlib.sha256(snap.read_bytes()).hexdigest(), ROOT/'package/package-manifest.json',
                            ROOT/'cutover-template.sql',out,t/'release', 'ignored',t/'drain','ignored')
            assert passes and result['result']=='CUTOVER_SQL_RENDERED_ONLY' and out.exists(),name
        except ValueError:
            assert not passes and not out.exists(),name
        print(name, 'PASS' if passes else 'DENY')
