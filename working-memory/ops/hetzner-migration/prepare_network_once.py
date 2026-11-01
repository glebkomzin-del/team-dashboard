"""One reversible stage network package; no public Nginx or source mutation."""
import hashlib,ipaddress,json,os,subprocess
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'network-prepare-1';os.umask(0o077);RUN.mkdir(mode=0o700)
def run(args):
 result=subprocess.run(args,capture_output=True)
 if result.returncode:
  (RUN/'failure-private.stderr').write_bytes(result.stderr);raise RuntimeError('Network operation failed '+args[0])
 return result.stdout
(RUN/'iptables-before.txt').write_bytes(run(['iptables-save']))
(RUN/'compose-before.yaml').write_bytes((ROOT/'compose.yaml').read_bytes())
(RUN/'networks-before.json').write_bytes(run(['docker','network','inspect','dashboard-supabase-20261003_restore']))
(RUN/'containers-before-private.json').write_bytes(run(['docker','inspect','dashboard-supabase-20261003-db-1','dashboard-supabase-20261003-auth-1','dashboard-supabase-20261003-api-gw-1']))
run(['iptables','-S','DOCKER-USER'])
chain=subprocess.run(['iptables','-S','DASHBOARD-SUPABASE-EGRESS'],capture_output=True)
if chain.returncode==0:raise SystemExit('Existing unowned egress chain requires review')
networks=json.loads(run(['docker','network','inspect',*run(['docker','network','ls','-q']).decode().split()]))
for subnet in ['172.28.80.0/29','172.28.81.0/29']:
 for network in networks:
  for config in network['IPAM'].get('Config',[]) or []:
   if config.get('Subnet') and ipaddress.ip_network(subnet).overlaps(ipaddress.ip_network(config['Subnet'])):raise SystemExit('Network address conflict')
for suffix,subnet in [('smtp-egress','172.28.80.0/29'),('api-ingress','172.28.81.0/29')]:
 run(['docker','network','create','--subnet',subnet,'dashboard-supabase-20261003_'+suffix])
run(['sh',str(ROOT/'network-egress.sh')])
(ROOT/'compose.yaml').write_bytes((ROOT/'compose-network-candidate.yaml').read_bytes())
run(['docker','compose','--env-file','.private.env','config','--quiet'])
run(['docker','compose','--env-file','.private.env','up','-d','--force-recreate','--no-deps','--wait','--wait-timeout','90','auth','api-gw'])
run(['docker','compose','--env-file','.private.env','restart','functions'])
receipt={'network_implementation':1,'production_source_unchanged':True,'public_nginx_changed':False,'private_original_saved':str(RUN),'compose_sha256':hashlib.sha256((ROOT/'compose.yaml').read_bytes()).hexdigest(),'verification_pending':True}
(RUN/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
