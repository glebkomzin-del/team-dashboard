"""Restore only our prior stage mappings and remove only our scoped rules."""
import subprocess
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'network-prepare-1'
unit=Path('/etc/systemd/system/dashboard-supabase-egress.service')
if (ROOT/'network-persist-1/receipt.json').exists():
 subprocess.run(['systemctl','disable','--now','dashboard-supabase-egress.service'],check=True)
 unit.unlink()
 subprocess.run(['systemctl','daemon-reload'],check=True)
(ROOT/'compose.yaml').write_bytes((RUN/'compose-before.yaml').read_bytes())
subprocess.run(['docker','compose','--env-file','.private.env','up','-d','--force-recreate','--no-deps','--wait','--wait-timeout','90','auth','api-gw'],cwd=ROOT,check=True)
for subnet in ['172.28.80.0/29','172.28.81.0/29']:
 subprocess.run(['iptables','-D','DOCKER-USER','-s',subnet,'-j','DASHBOARD-SUPABASE-EGRESS'],check=True)
subprocess.run(['iptables','-F','DASHBOARD-SUPABASE-EGRESS'],check=True);subprocess.run(['iptables','-X','DASHBOARD-SUPABASE-EGRESS'],check=True)
for suffix in ['smtp-egress','api-ingress']:subprocess.run(['docker','network','rm','dashboard-supabase-20261003_'+suffix],check=True)
print('Original stage network restored; unrelated rules untouched')
