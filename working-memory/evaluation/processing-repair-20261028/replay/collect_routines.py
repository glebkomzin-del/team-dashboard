"""Read-only export of existing guarded adoption RPC definitions."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PRIVATE=ROOT/'private'
query="BEGIN READ ONLY; SELECT json_object_agg(p.proname,pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('wm_generation_stage','wm_generation_decide','wm_archive_note_put'); COMMIT;"
ssh=['ssh','-i','/Users/glebkomzin/.ssh/id_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','root@178.105.167.26','docker exec -i dashboard-supabase-20261003-db-1 psql -U postgres -d postgres -XqAt -v ON_ERROR_STOP=1']
value=json.loads(subprocess.check_output(ssh,input=query.encode(),timeout=60));p=PRIVATE/'live-adoption-routines.json';p.write_text(json.dumps(value));p.chmod(0o600)
assert set(value)=={'wm_generation_stage','wm_generation_decide','wm_archive_note_put'}
checks={'wm_generation_stage':['Generation base changed','Job unavailable for generation review','job_updated_at'],'wm_generation_decide':['Reviewed generation changed','Reviewed job changed','Review already decided with different content',"id=g.job_id"],'wm_archive_note_put':['Note checksum mismatch','Active archive document required','Note identity reused with changed data','repeated']}
report={}
for name,needles in checks.items():
 text=value[name];report[name]={'sha256':hashlib.sha256(text.encode()).hexdigest(),'guards':{n:n in text for n in needles}}
(ROOT/'live-adoption-routines-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
