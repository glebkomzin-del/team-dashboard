"""Stage-only exact hosted bundles; no invocation of former provider pipelines."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/'.local/hetzner-migration-20261003/source'
OUT=ROOT/'edge-stage';os.umask(0o077);OUT.mkdir(exist_ok=True)
metadata=[]
for path in sorted(ROOT.glob('edge-*.json')):
 obj=json.loads(path.read_text());slug=obj['slug'];directory=OUT/slug;directory.mkdir(exist_ok=True)
 for item in obj['files']:
  if '/' in item['name']:raise SystemExit('Unexpected bundle layout')
  content=item['content']
  if slug=='working-memory-journal' and item['name']=='handler.ts':
   content=(Path(__file__).resolve().parents[4]/'supabase/functions/working-memory-journal/handler.ts').read_text()
  (directory/item['name']).write_text(content);(directory/item['name']).chmod(0o644)
 directory.chmod(0o755)
 metadata.append({'slug':slug,'version':obj['version'],'verify_jwt':obj['verify_jwt']})
(OUT/'manifest.json').write_text(json.dumps(metadata,indent=2));(OUT/'manifest.json').chmod(0o644)
subprocess.run(['scp','-r','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',str(OUT)+'/','root@178.105.167.26:/opt/dashboard-supabase-20261003/functions-export'],check=True)
print(json.dumps({'exported_bundles':len(metadata),'provider_invocations':0}))
