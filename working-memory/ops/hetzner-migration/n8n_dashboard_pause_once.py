"""Prepared only: targeted supported n8n API pause/resume, gated and immutable."""
import argparse,json,os,urllib.request
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003')
VERSIONS={'nzyaKxs5Om9wuPEc':'d7211499-a941-4614-89e6-be6fb13f1f86','dashboardDriveMove':'74b389a7-0b56-4cfe-a7c1-720c5867d031','dashboardDriveWatch':'d0475768-b276-43b7-b5a2-67b7ceb13dce'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--action',choices=['pause','resume'],required=True);p.add_argument('--run-dir',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args();os.umask(0o077)
 run=Path(a.run_dir).resolve();assert run.parent==ROOT and run.name.startswith('final-export-')
 gate=json.loads(Path(a.gate_receipt).read_text());assert gate['problem_id']=='HZ-MIGRATION-20261003-FINAL-CUTOVER' and gate['decision']=='CONTINUE_BOUNDED' and gate['run_dir']==str(run)
 key=json.loads((ROOT/'n8n-pause-access-1/existing-api-key-private.json').read_text())['apiKey']
 def api(w,op='',data=None):
  req=urllib.request.Request('http://127.0.0.1:5678/api/v1/workflows/'+w+op,headers={'X-N8N-API-KEY':key,'Content-Type':'application/json'},data=None if data is None else json.dumps(data).encode())
  with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
 (run/('n8n-'+a.action+'-attempt.marker')).open('x').write('single gated supported API sequence')
 receipt={'action':a.action,'status':'FAILED','changed':[],'scope_key_unchanged':True}
 try:
  before={w:api(w) for w in VERSIONS};(run/('n8n-'+a.action+'-before-private.json')).write_text(json.dumps(before))
  for w,v in VERSIONS.items():
   if a.action=='pause':assert before[w]['active'] and before[w]['activeVersionId']==v
   else:assert not before[w]['active']
  for w,v in VERSIONS.items():
   result=api(w,'/deactivate' if a.action=='pause' else '/activate',{} if a.action=='pause' else {'versionId':v})
   (run/(w+'-'+a.action+'-private.json')).write_text(json.dumps(result));receipt['changed'].append(w)
   actual=api(w);assert actual['active']==(a.action=='resume')
   if a.action=='resume':assert actual['activeVersionId']==v
  receipt['status']='PASSED'
 except Exception as err:receipt['failure_type']=type(err).__name__
 finally:(run/('n8n-'+a.action+'-receipt.json')).write_text(json.dumps(receipt,indent=2))
 print(json.dumps(receipt))
 if receipt['status']!='PASSED':raise SystemExit(1)
if __name__=='__main__':main()
