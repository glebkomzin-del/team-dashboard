"""Run only adapter against approved stage; never replace production backup code."""
import argparse, importlib.util, json, os, sys, tarfile
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--candidate',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--reuse-dump',action='store_true')
args=parser.parse_args()
output=Path(args.output)
if not output.is_absolute() or output.parent!=Path('/var/backups/dashboard-job') or not output.name.startswith('.adapter-check-'):
    raise SystemExit('Use a new private .adapter-check- directory on the backup filesystem')
os.umask(0o077)
if not args.reuse_dump:output.mkdir(mode=0o700)
elif not (output/'selfhost/source-fingerprint.json').is_file():raise SystemExit('No prior isolated source snapshot')
sys.path.insert(0,'/opt/dashboard-memory-canonical-draft')
spec=importlib.util.spec_from_file_location('backup_candidate',args.candidate)
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
backup.ROOT=output/'diagnostics';(backup.ROOT/'.local').mkdir(mode=0o700,parents=True,exist_ok=args.reuse_dump)
marker=backup.ROOT/'.local/selfhost-backup.json'
if not marker.exists():backup.private_json(marker,{'enabled':True})
elif json.loads(marker.read_text())!={'enabled':True}:raise SystemExit('Unexpected prior check marker')
try:
    if args.reuse_dump:
        folder=output/'selfhost';pg=backup.container(backup.SELFHOST_CONTAINER)
        metadata=json.loads((folder/'runtime-image.json').read_text())
        if metadata['image_id']!=pg['Image']:raise RuntimeError('Snapshot image changed')
        metadata['postgres_account']={'uid':int(backup.run(['docker','exec',pg['Id'],'id','-u','postgres']).strip()),'gid':int(backup.run(['docker','exec',pg['Id'],'id','-g','postgres']).strip())}
        (folder/'runtime-image.json').rename(output/'runtime-image-cycle1.json')
        backup.private_json(folder/'runtime-image.json',metadata)
        receipt=backup.selfhost_restore(folder,pg,json.loads((folder/'source-fingerprint.json').read_text()))
        backup.private_json(folder/'restore-check.json',receipt)
        result={'enabled':True,'tables_verified':len(receipt['tables']),'dump_sha256':receipt['dump_sha256'],'restore_verified':True}
    else:result=backup.backup_selfhost(output,{'SUPABASE_URL':'http://127.0.0.1:8800'})
    files={str(p.relative_to(output)):{'bytes':p.stat().st_size,'sha256':backup.checksum(p)}
           for p in (output/'selfhost').rglob('*') if p.is_file()}
    backup.private_json(output/'bundle-manifest.json',{'format':'dashboard-full-backup-v1','files':files})
    archive=output/'backup-adapter-isolated.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name in [*files,'bundle-manifest.json']:tar.add(output/name,arcname=name)
    result.update(archive_sha256=backup.checksum(archive),archive_bytes=archive.stat().st_size,
                  files=len(files),production_backup_deployed=False)
    backup.private_json(output/'result.json',result)
    print(json.dumps(result))
except Exception as error:
    # No private SQL/secret data in terminal; original errors remain private.
    backup.private_json(output/'failure.json',{'type':type(error).__name__,'message':str(error)[:300]})
    raise SystemExit('Isolated adapter check failed; inspect private failure.json') from None
