"""Install only stage bundles, preserve source per-function JWT requirements."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');manifest=json.loads((ROOT/'functions-export/manifest.json').read_text())
for item in manifest:
 src=ROOT/'functions-export'/item['slug'];dst=ROOT/'functions'/item['slug'];shutil.copytree(src,dst,dirs_exist_ok=True)
main=ROOT/'functions/main/index.ts';text=main.read_text()
original="if (req.method !== 'OPTIONS' && VERIFY_JWT) {"
previous="if (req.method !== 'OPTIONS' && VERIFY_JWT && new URL(req.url).pathname.split('/')[1] !== 'working-memory-journal') {"
allowed=[x['slug'] for x in manifest if not x['verify_jwt']]
condition="if (req.method !== 'OPTIONS' && VERIFY_JWT && !"+json.dumps(allowed)+".includes(new URL(req.url).pathname.split('/')[1])) {"
if original in text:text=text.replace(original,condition)
elif previous in text:text=text.replace(previous,condition)
elif condition not in text:raise SystemExit('Unexpected pinned router contract')
main.write_text(text)
proof={'functions':manifest,'router_sha256':hashlib.sha256(main.read_bytes()).hexdigest(),'source_only_journal_origin_adapted':True}
(ROOT/'edge-stage-evidence.json').write_text(json.dumps(proof,indent=2))
subprocess.run(['docker','compose','--env-file','.private.env','restart','functions'],cwd=ROOT,check=True)
print('11 source function contracts installed on isolated stage')
