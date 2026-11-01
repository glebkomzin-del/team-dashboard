"""Generate private guarded metadata SQL only; never applies scopes or workflow changes."""
import hashlib,json,os
from pathlib import Path
os.umask(0o077)
ROOT=Path(__file__).resolve().parents[2]/'.local/hetzner-migration-20261003/current-evidence'
k=json.loads((ROOT/'n8n-pause-access-1/existing-api-key-private.json').read_text());base=k['scopes'];added=['workflow:activate','workflow:deactivate'];assert all(s not in base for s in added);expanded=base+added
out=ROOT/'n8n-scope-plan-1';out.mkdir(mode=0o700)
def lit(v):return "'"+v.replace("'","''")+"'"
def plan(expected,new):
 return '''BEGIN;
DO $migration$
DECLARE k user_api_keys%%ROWTYPE;
BEGIN
 SELECT * INTO STRICT k FROM user_api_keys WHERE id=%s FOR UPDATE;
 IF k."userId"<>%s::uuid OR md5(k."apiKey")<>%s OR k.scopes::jsonb<>%s::jsonb THEN
  RAISE EXCEPTION 'Migration key metadata changed; refuse scope mutation';
 END IF;
 UPDATE user_api_keys SET scopes=%s::json WHERE id=k.id;
END $migration$;
COMMIT;
'''%(lit(k['id']),lit(k['userId']),lit(hashlib.md5(k['apiKey'].encode()).hexdigest()),lit(json.dumps(expected)),lit(json.dumps(new)))
(out/'add-scopes.sql').write_text(plan(base,expanded));(out/'restore-scopes.sql').write_text(plan(expanded,base))
receipt={'executed':False,'existing_api_key_reused':True,'added_scopes':added,'original_scope_sha256':hashlib.sha256(json.dumps(base,separators=(',',':')).encode()).hexdigest(),'expanded_scope_sha256':hashlib.sha256(json.dumps(expanded,separators=(',',':')).encode()).hexdigest(),'sql_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()},'workflow_states_changed':False,'key_secret_changed':False,'project_role_changed':False,'gate_required_before_metadata_mutation':True}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
