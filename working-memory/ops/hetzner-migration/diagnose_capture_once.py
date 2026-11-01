"""Exactly one approved capture/process diagnostic; no Recovery or DATA."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path('/opt/dashboard-supabase-20261003');RUN=ROOT/'recovery-diagnose-1';os.umask(0o077);RUN.mkdir(mode=0o700)
name='dashboard-migration-capture-diagnose-1';network='dashboard-supabase-20261003_restore'
original=ROOT/'recovery-authorized-1/capture.js';(RUN/'capture.js').write_bytes(original.read_bytes())
image=json.loads(subprocess.check_output(['docker','inspect','n8n']))[0]['Image']
auth=json.loads(subprocess.check_output(['docker','inspect','dashboard-supabase-20261003-auth-1']))[0]
identity={'auth_container_id':auth['Id'],'auth_pid':auth['State']['Pid'],'auth_networks':list(auth['NetworkSettings']['Networks']),'capture_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'original_capture_unmodified':True}
(RUN/'identity.json').write_text(json.dumps(identity,indent=2))
def result_file(label,result):
 (RUN/(label+'.stdout')).write_bytes(result.stdout);(RUN/(label+'.stderr')).write_bytes(result.stderr);(RUN/(label+'.result.json')).write_text(json.dumps({'returncode':result.returncode,'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()},indent=2))
def inspect(label):
 v=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
 (RUN/(label+'.json')).write_text(json.dumps({'Id':v['Id'],'State':v['State'],'NetworkSettings':v['NetworkSettings']},indent=2));return v
started=False
try:
 result=subprocess.run(['docker','run','-d','--name',name,'--network',network,'--read-only','--user','0','--memory','128m','--cpus','.25','-v',str(RUN)+':/capture','--entrypoint','node',image,'/capture/capture.js'],capture_output=True);result_file('capture-start',result)
 if result.returncode:raise RuntimeError('Capture start failed')
 started=True;before=inspect('capture-before-node');ip=before['NetworkSettings']['Networks'][network]['IPAddress']
 probe="const net=require('net');let v='';const s=net.connect(1025,'"+ip+"');s.setTimeout(5000,()=>process.exit(2));s.on('data',b=>{v+=b;if(v.startsWith('220')&&!v.includes('250'))s.write('EHLO isolated-auth.invalid\\r\\n');if(v.includes('250 8BITMIME')){s.end('QUIT\\r\\n');process.exit(0)}});s.on('error',()=>process.exit(3));"
 (RUN/'node-probe.js').write_text(probe)
 node=subprocess.run(['docker','run','--rm','--network','container:dashboard-supabase-20261003-auth-1','--read-only','--memory','128m','--cpus','.25','--entrypoint','node',image,'-e',probe],capture_output=True,timeout=15);result_file('node-probe',node)
 after=inspect('capture-after-node');logs=subprocess.run(['docker','logs',name],capture_output=True);result_file('capture-after-node-logs',logs)
 nativecode="import smtplib; c=smtplib.SMTP('"+ip+"',1025,local_hostname='namespace.invalid',timeout=5); r=c.ehlo(); print('EHLO_STATUS='+str(r[0])); r=c.quit(); print('QUIT_STATUS='+str(r[0]))"
 (RUN/'native-probe.py').write_text(nativecode)
 native=subprocess.run(['nsenter','-t',str(auth['State']['Pid']),'-n','python3','-c',nativecode],capture_output=True,timeout=15);result_file('native-probe',native)
 final=inspect('capture-after-native');result_file('capture-final-logs',subprocess.run(['docker','logs',name],capture_output=True))
 receipt={'diagnostic_run':1,'original_capture_unmodified':True,'auth_pid':identity['auth_pid'],'node_returncode':node.returncode,'capture_running_after_node':after['State']['Running'],'capture_exit_after_node':after['State']['ExitCode'],'native_returncode':native.returncode,'capture_running_after_native':final['State']['Running'],'capture_exit_after_native':final['State']['ExitCode'],'recovery_requests':0,'smtp_data_commands':0}
 (RUN/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
finally:
 if started:result_file('capture-remove',subprocess.run(['docker','rm','-f',name],capture_output=True))
 hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.iterdir() if p.is_file()};(RUN/'hashes.json').write_text(json.dumps(hashes,indent=2))
 for p in RUN.iterdir():p.chmod(0o600)
