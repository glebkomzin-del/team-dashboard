"""Send one guarded action through SSH stdin. Default: read-only preflight."""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
PACKAGE=HERE.parent
NAMES=('hybrid_pipeline.py','hybrid_schema.py','hybrid_index.py','processor.py','memory.py','reconcile.py','temporal_guard.py','call_budget.py','openai_provider.py','planner.py','projection_order.py','evaluation/prompt-v9.txt','evaluation/schema-v9.json','evaluation/work-gate-prompt-v9.txt','evaluation/work-gate-schema-v9.json','evaluation/source-corrections.json','compact_reconcile.py','retrieval_context.py','human_decisions.py','candidate_filter.py','delta_codec.py')
def bundle(action):
 config=json.loads((PACKAGE/'audit/private/processing-config-before.json').read_text())
 files={'memory.py':(PACKAGE/'replay/overlay/memory.py').read_bytes(),'openai_provider.py':(PACKAGE/'provider/openai_provider.py').read_bytes()}
 assert {n:hashlib.sha256(v).hexdigest() for n,v in files.items()}=={'memory.py':'e822eb293d6d87cc74f0df5671e4d656c060c81ccce6502860b7c142803c2316','openai_provider.py':'fe6dc8e07c5e90bacca8e1b6b364b97fab2715d1589209ea457a909d4a92c0d3'},'Reviewed candidate changed'
 runtime=PACKAGE/'replay/private/runtime'
 old=hashlib.sha256(''.join((runtime/n).read_text() for n in NAMES).encode()).hexdigest()[:16]
 assert config['pipeline'].split(':')[4]==old,'Baseline fingerprint drift'
 new=hashlib.sha256(''.join(files[n].decode() if n in files else (runtime/n).read_text() for n in NAMES).encode()).hexdigest()[:16]
 fresh=PACKAGE/'replay/private/fresh338'
 manifest=json.loads((fresh/'manifest.json').read_text())
 steps=[]
 for prefix,expected in [('7b4057c2','4c9bd49460fa0bd814052a1ffd82efe537a4a74c34c18214ae208bee20fe57bc'),('a77d73b4','3cc0076570e4e0dfd2992cf50ace305960fd82cd52c5ede3f0dd099944eaee60')]:
  name='sequential-'+prefix+'.json';raw=(fresh/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==manifest[name]
  step=json.loads(raw);assert step['decide_request']['review_sha256']==step['verified_payload']['review_sha256']==expected;assert step['verified_payload']['personal_decisions_preserved']==11
  steps.append(step)
 assert [s['stage_request']['expected_revision'] for s in steps]==[338,339]
 return {'action':action,'original_config':config,'new_pipeline':config['pipeline'].replace(':'+old+':',':'+new+':',1),'steps':steps,'files':{n:base64.b64encode(v).decode() for n,v in files.items()}}
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('preflight','deploy','adopt','resume','verify'),nargs='?',default='preflight');parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 if args.action!='preflight' and not args.execute:parser.error('Mutating phases require --execute by Lead')
 raw=base64.b64encode(json.dumps(bundle(args.action),ensure_ascii=False).encode()).decode()
 source=(HERE/'remote.py').read_text()+'\nrun(json.loads(base64.b64decode('+repr(raw)+')))\n'
 command=['ssh','-i','/Users/glebkomzin/.ssh/id_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','root@178.105.167.26','python3 -']
 result=subprocess.run(command,input=source.encode(),capture_output=True,timeout=900)
 private=HERE/'private';private.mkdir(exist_ok=True,mode=0o700)
 for suffix,data in [('stdout',result.stdout),('stderr',result.stderr)]:
  target=private/(args.action+'.'+suffix);target.write_bytes(data);target.chmod(0o600)
 if result.returncode:raise SystemExit('Action failed; private diagnostics retained. Check processing hold.')
 print(result.stdout.decode(),end='')
if __name__=='__main__':main()
