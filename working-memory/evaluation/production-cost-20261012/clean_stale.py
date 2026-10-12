import pathlib,subprocess,json,hashlib,fcntl,shutil,os,time
root=pathlib.Path('/var/backups/dashboard-job')
targets=['.building-dhlz01zm','.building-2tk29j11','.building-eo41_sg6']
out=pathlib.Path('/opt/dashboard-memory-canonical-draft/.local/recovery/production-cost-20261012')
out.mkdir(mode=0o700,parents=True,exist_ok=True)
with open('/run/lock/dashboard-job-backup.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 state=subprocess.check_output(['systemctl','show','dashboard-job-backup.service','-p','ActiveState','--value'],text=True).strip()
 if state not in ('failed','inactive'):raise RuntimeError('Backup active; cleanup denied')
 before={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in root.glob('dashboard-*.tar.gz')}
 for name in targets:
  folder=root/name
  if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent!=root:raise RuntimeError('Invalid stale folder')
  if folder.stat().st_mtime>time.time()-86400:raise RuntimeError('Not stale')
  if not (folder/'canonical/request.json').is_file():raise RuntimeError('Missing canonical request identity')
  manifest=[]
  for path in sorted(folder.rglob('*')):
   if path.is_symlink():raise RuntimeError('Symlink in stale folder; preserve')
   if not path.is_file():continue
   st=path.stat();h=hashlib.sha256()
   with path.open('rb') as stream:
    for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
   manifest.append({'path':str(path.relative_to(folder)),'bytes':st.st_size,'sha256':h.hexdigest()})
   if st.st_size<=524288:
    dest=out/name/path.relative_to(folder);dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True);shutil.copy2(path,dest);dest.chmod(0o600)
  receipt=out/(name+'.manifest.json');receipt.write_text(json.dumps({'state':'approved_stale_cleanup','original':str(folder),'files':manifest,'user_authorized':True}));receipt.chmod(0o600)
  shutil.rmtree(folder)
  print(json.dumps({'removed_stale_folder':name,'preserved_files_manifest':str(receipt),'bytes':sum(x['bytes'] for x in manifest)}),flush=True)
 after={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in root.glob('dashboard-*.tar.gz')}
 if before!=after:raise RuntimeError('Completed backup archives changed')
 (out/'cleanup-receipt.json').write_text(json.dumps({'completed_archives_unchanged':True,'removed':targets,'free_bytes':shutil.disk_usage(root).free}));(out/'cleanup-receipt.json').chmod(0o600)
 print(json.dumps({'completed_archives_unchanged':True,'free_bytes':shutil.disk_usage(root).free}),flush=True)
