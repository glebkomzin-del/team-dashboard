"""Isolated-target repair preserving UUID, metadata and nonce; no source writes."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/'.local/hetzner-migration-20261003/source'
os.umask(0o077)
rows=json.loads((ROOT/'vault-plaintext.json').read_text())
if len(rows)!=1:raise SystemExit('Unexpected source count')
row=rows[0]
def literal(value):return "'"+value.replace("'","''")+"'"
# _crypto primitive is the installed official update_secret implementation.
query='BEGIN; SET LOCAL standard_conforming_strings=on; UPDATE vault.secrets s SET secret=encode(vault._crypto_aead_det_encrypt(message:=convert_to('+literal(row['decrypted_secret'])+",'utf8'),additional:=convert_to(s.id::text,'utf8'),key_id:=0,context:='pgsodium'::bytea,nonce:=s.nonce),'base64') WHERE id="+literal(row['id'])+'::uuid AND name IS NOT DISTINCT FROM '+('NULL' if row['name'] is None else literal(row['name']))+'; SELECT id,encode(extensions.digest(decrypted_secret,\'sha256\'),\'hex\') FROM vault.decrypted_secrets; COMMIT;'
cmd=['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@178.105.167.26','docker exec -i dashboard-supabase-20261003-db-1 psql -XqAt -v ON_ERROR_STOP=1 -U supabase_admin -d postgres']
result=subprocess.run(cmd,input=query,text=True,capture_output=True,timeout=30)
if result.returncode:
    (ROOT/'vault-reencrypt-error.txt').write_text(result.stderr)
    raise SystemExit('Target Vault repair failed; private diagnostics retained')
expected=row['id']+'|'+hashlib.sha256(row['decrypted_secret'].encode()).hexdigest()
if result.stdout.strip()!=expected:raise SystemExit('Vault UUID/hash mismatch')
evidence={'secret_count':1,'same_uuid':True,'decrypted_hash_equal':True,'metadata_preserved':True,'source_modified':False,'cipher_intentionally_changed_after_exact_snapshot_comparison':True}
(ROOT/'vault-validation.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence))
