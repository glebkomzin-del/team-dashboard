"""Read-only note existence and live routine signatures; no credentials."""
import json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PRIVATE=ROOT/'private';v=json.loads((PRIVATE/'inputs.json').read_text())
ids=[j['document_id'] for j in v['jobs']];assert all(re.fullmatch('[0-9a-f]{64}',x) for x in ids)
query="BEGIN READ ONLY; SELECT coalesce(json_agg(t),'[]') FROM (SELECT * FROM wm_archive_notes WHERE document_id IN ('"+"','".join(ids)+"')) t; COMMIT;"
ssh=['ssh','-i','/Users/glebkomzin/.ssh/id_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','root@178.105.167.26','docker exec -i dashboard-supabase-20261003-db-1 psql -U postgres -d postgres -XqAt -v ON_ERROR_STOP=1']
notes=json.loads(subprocess.check_output(ssh,input=query.encode(),timeout=60));p=PRIVATE/'existing-notes.json';p.write_text(json.dumps(notes));p.chmod(0o600)
print(json.dumps({'existing_notes':len(notes),'documents':len(ids)}))
