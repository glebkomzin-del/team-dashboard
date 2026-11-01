"""Private read-only source Vault export. No master-key or OS access."""
import base64,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/'.local/hetzner-migration-20261003/source'
os.umask(0o077)
token=subprocess.run(['/usr/bin/security','find-generic-password','-s','Supabase CLI','-a','supabase','-w'],capture_output=True,text=True,check=True).stdout.strip()
if token.startswith('go-keyring-base64:'):token=base64.b64decode(token.split(':',1)[1]).decode()
request=urllib.request.Request('https://api.supabase.com/v1/projects/lghwikeotbkmojyyjglz/database/query',data=json.dumps({'query':'SELECT id,name,description,decrypted_secret FROM vault.decrypted_secrets'}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(request,timeout=30) as response:rows=json.load(response)
except Exception:raise SystemExit('Private source Vault read unavailable') from None
if not isinstance(rows,list) or len(rows)!=1 or not all(k in rows[0] for k in ['id','name','description','decrypted_secret']):raise SystemExit('Unexpected Vault result; stop')
path=ROOT/'vault-plaintext.json'
with path.open('x') as stream:json.dump(rows,stream)
path.chmod(0o600)
print(json.dumps({'private_export':str(path),'secret_count':len(rows),'decrypted_hash':hashlib.sha256(rows[0]['decrypted_secret'].encode()).hexdigest()}))
