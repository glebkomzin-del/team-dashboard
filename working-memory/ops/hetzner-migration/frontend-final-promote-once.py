"""Bounded final promotion; run only with explicit target-restored-readonly GO."""
import argparse, base64, datetime, hashlib, json, os, subprocess, urllib.request
from pathlib import Path
OPS = Path(__file__).resolve().parent
artifact = json.loads((OPS/'frontend-target-artifact.json').read_text())
BUILD = Path(artifact['build_path'])
PRIVATE = Path('/private/tmp/hz-frontend-cutover-private')
ALIASES = {'team-dashboard-rho.vercel.app', 'team-dashboard-glebkomzin-dels-projects.vercel.app'}
ROLLBACK = 'dpl_84v5UqEaCs5TnRsb6QzahSNxeNxL'
PREVIEW = 'dpl_DfSYKEA5xDAH6XKT9yV3djWfAWZC'
RECEIPT = OPS/'frontend-final-promotion-evidence.json'

def cli(args, value=None):
    result = subprocess.run(['vercel', *args], cwd=BUILD, input=value, text=True, capture_output=True, timeout=240)
    if result.returncode:
        raise RuntimeError('Vercel command failed: '+args[0]+' exit '+str(result.returncode))
    return result.stdout

def inspect(alias):
    return json.loads(cli(['inspect', alias, '--format', 'json']))

def frozen_checks():
    output=BUILD/'.vercel/output'
    assert hashlib.sha256((output/'config.json').read_bytes()).hexdigest()==artifact['output_hashes']['config.json']
    for name, digest in artifact['current_static_hashes'].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest()==digest, name
    assert hashlib.sha256(Path(artifact['artifact_archive']['path']).read_bytes()).hexdigest()==artifact['artifact_archive']['sha256']
    link=json.loads((BUILD/'.vercel/project.json').read_text())
    assert link['projectId']=='prj_pWCB8TaGLQesLsT9me0jgT0FqcC5' and link['orgId']=='team_xbeBltwkXhOuVc8JUUR0CqoF'
    return output

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--target-restored-readonly-go', required=True)
    args=parser.parse_args(); assert args.target_restored_readonly_go=='HZ-MIGRATION-20261003-FINAL-FRONTEND'
    output=frozen_checks(); PRIVATE.mkdir(mode=0o700, exist_ok=True)
    marker=PRIVATE/'frontend-final-promotion-started'
    fd=os.open(marker, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600); os.close(fd)
    evidence={'problem_id':'HZ-MIGRATION-20261003-FINAL-FRONTEND','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'promotion_attempts':0,'auth_calls':0,'source_builds':0,'status':'STARTED'}
    try:
        for alias in ALIASES:
            old=inspect(alias); assert old['id']==ROLLBACK and old['readyState']=='READY'
        backup=PRIVATE/'final-production-before-promotion.env'
        cli(['env','pull',str(backup),'--environment','production','--yes']); backup.chmod(0o600)
        assert not any(line.startswith(('VITE_SUPABASE_URL=', 'VITE_SUPABASE_ANON_KEY=')) for line in backup.read_text().splitlines())
        remote="python3 -c \"from pathlib import Path; d=dict(x.split('=',1) for x in Path('/opt/dashboard-supabase-20261003/.private.env').read_text().splitlines() if '=' in x and not x.startswith('#')); print(d['ANON_KEY'].strip(chr(39)))\""
        key=subprocess.check_output(['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','StrictHostKeyChecking=yes','root@178.105.167.26',remote],text=True,timeout=30).strip()
        assert hashlib.sha256(key.encode()).hexdigest()==artifact['target_key_sha256']
        payload=json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'===')); assert payload['role']=='anon'
        cli(['env','add','VITE_SUPABASE_URL','production','--yes'],artifact['target_url']+'\n'); evidence['url_env_added']=True
        cli(['env','add','VITE_SUPABASE_ANON_KEY','production','--yes','--sensitive'],key+'\n'); evidence['anon_env_added']=True
        evidence['promotion_attempts']=1
        RECEIPT.write_text(json.dumps(evidence,indent=2)+'\n')
        cli(['promote',PREVIEW,'--yes'])
        deployments=[inspect(alias) for alias in sorted(ALIASES)]
        assert len({x['id'] for x in deployments})==1
        prod=deployments[0]; assert prod['readyState']=='READY' and prod['target']=='production'
        assert ALIASES.issubset(set(prod['aliases']))
        evidence['production']={k:prod[k] for k in ('id','readyState','target','aliases','url')}
        headers_expected=json.loads((output/'config.json').read_text())['routes'][0]['headers']
        checks=[]
        for alias in sorted(ALIASES):
            for route in ['/', '/memory-next?recovery=1']:
                with urllib.request.urlopen('https://'+alias+route,timeout=45) as response:
                    body=response.read(); assert response.status==200
                    for name,value in headers_expected.items(): assert response.headers.get(name)==value,name
                    assert body.strip()==(output/'static/index.html').read_bytes().strip()
                    checks.append({'alias':alias,'route':route,'http':200,'exact_index':True,'exact_headers':True})
            for name,digest in artifact['current_static_hashes'].items():
                if not name.startswith('static/assets/'): continue
                with urllib.request.urlopen('https://'+alias+'/'+name.removeprefix('static/'),timeout=45) as response:
                    assert response.status==200 and hashlib.sha256(response.read()).hexdigest()==digest,name
                    checks.append({'alias':alias,'route':name.removeprefix('static'),'sha256':digest,'exact_asset':True})
        evidence.update(status='PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED',checks=checks)
    except Exception as error:
        evidence.update(status='STOPPED_NO_RETRY',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        RECEIPT.write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps({k:evidence[k] for k in ('status','promotion_attempts','auth_calls','source_builds')}))
if __name__=='__main__': main()
