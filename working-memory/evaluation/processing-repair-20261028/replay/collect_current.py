"""Read-only bounded current journal export for a local generation preview."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PRIVATE=ROOT/'private'
v=json.loads((PRIVATE/'inputs.json').read_text());space=v['jobs'][0]['space_id']
assert all(j['space_id']==space for j in v['jobs'])
import uuid
assert str(uuid.UUID(space))==space
sql="""BEGIN READ ONLY;
SELECT json_build_object('space',(SELECT row_to_json(s) FROM wm_spaces s WHERE s.id='%s'),'entries',(SELECT json_agg(t ORDER BY revision) FROM (SELECT * FROM wm_journal WHERE space_id='%s') t),'sources',(SELECT json_agg(t) FROM (SELECT * FROM wm_source_versions WHERE space_id='%s') t));
COMMIT;"""%(space,space,space)
ssh=['ssh','-i','/Users/glebkomzin/.ssh/id_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','root@178.105.167.26','docker exec -i dashboard-supabase-20261003-db-1 psql -U postgres -d postgres -XqAt -v ON_ERROR_STOP=1']
data=json.loads(subprocess.check_output(ssh,input=sql.encode(),timeout=90));path=PRIVATE/'current-inputs.json';path.write_text(json.dumps(data));path.chmod(0o600)
assert len(data['entries'])==data['space']['revision']
print(json.dumps({'revision':data['space']['revision'],'entries':len(data['entries']),'sources':len(data['sources'])}))
