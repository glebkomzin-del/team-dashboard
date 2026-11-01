"""Wire only our existing scoped rules; no Docker/host reboot or full restore."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'network-persist-1';os.umask(0o077);RUN.mkdir(mode=0o700)
unit=Path('/etc/systemd/system/dashboard-supabase-egress.service');candidate=ROOT/'network-egress.service'
if unit.exists():raise SystemExit('Existing unit requires ownership review')
def run(args):return subprocess.check_output(args,stderr=subprocess.STDOUT)
def rules():return run(['iptables','-S','DASHBOARD-SUPABASE-EGRESS'])+b'\n'+run(['iptables','-S','DOCKER-USER'])
before=rules();(RUN/'rules-before.txt').write_bytes(before)
unit.write_bytes(candidate.read_bytes());unit.chmod(0o644)
run(['systemctl','daemon-reload']);run(['systemctl','enable','--now','dashboard-supabase-egress.service'])
run(['systemctl','restart','dashboard-supabase-egress.service'])
after=rules();(RUN/'rules-after.txt').write_bytes(after)
assert before==after
active=run(['systemctl','is-active','dashboard-supabase-egress.service']).decode().strip();enabled=run(['systemctl','is-enabled','dashboard-supabase-egress.service']).decode().strip();assert active=='active' and enabled=='enabled'
receipt={'persistent_unit':'dashboard-supabase-egress.service','enabled':True,'active':True,'after_and_part_of_docker':True,'scoped_restart_reapply_passed':True,'rules_hash_unchanged':hashlib.sha256(after).hexdigest(),'docker_restarted':False,'host_rebooted':False,'actual_boot_behavior_not_tested':True,'host_input_ufw_unchanged':True,'unit_sha256':hashlib.sha256(unit.read_bytes()).hexdigest()}
(RUN/'receipt.json').write_text(json.dumps(receipt,indent=2));(RUN/'unit-status.txt').write_bytes(run(['systemctl','show','dashboard-supabase-egress.service','-p','ActiveState','-p','SubState','-p','After','-p','PartOf','-p','UnitFileState']))
print(json.dumps(receipt))
