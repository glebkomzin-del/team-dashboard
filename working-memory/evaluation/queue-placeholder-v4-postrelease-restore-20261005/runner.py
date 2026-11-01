import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

base = Path('/root/dashboard-v4-restore-test-20261005')
folder = base / 'input'
script = Path('/opt/dashboard-memory-canonical-draft/scheduled_backup.py')
assert hashlib.sha256(script.read_bytes()).hexdigest() == '954e5f163387952b6b7074e5ec3d6938cd9fbedc0473044f3fecd5d8c56d29ec'
assert hashlib.sha256((folder / 'postgres.dump').read_bytes()).hexdigest() == '590fda5f27c856299b5aa66d37cfe97893bec95460c6cabea0f5c2fc43efe562'
assert hashlib.sha256((folder / 'roles.sql').read_bytes()).hexdigest() == '2c551c896202f62b94d97e24bbd41e8b662b15f720596e566299bfba8fd95b1a'
assert hashlib.sha256((folder / 'source-fingerprint.json').read_bytes()).hexdigest() == '34f236e031750e5d049254374cb8cffcf72941d1d12337e3f7d02ab4a7979a29'
meta = json.loads((folder / 'runtime-image.json').read_text())
assert meta['image_id'] == 'sha256:a9946f08d31e8eb1149229c94e5c26603a9233116807cbbd93d75179cbac516a'
pg = {'Image': meta['image_id'], 'Config': {'Cmd': meta['command']}}
expected = json.loads((folder / 'source-fingerprint.json').read_text())
sys.path.insert(0, '/opt/dashboard-memory-canonical-draft')
spec = importlib.util.spec_from_file_location('isolated_existing_backup', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = base
(base / '.local').mkdir(mode=0o700, exist_ok=True)
original_psql = module.selfhost_psql
proof = {}
query = """with f as (select to_regprocedure('public.wm_archive_image_placeholder_job(uuid,text,uuid,text)') oid)
select coalesce(md5(pg_get_functiondef(f.oid)),'MISSING'),
 coalesce(has_function_privilege('service_role',f.oid,'EXECUTE'),false),
 coalesce(has_function_privilege('anon',f.oid,'EXECUTE'),false),
 coalesce(has_function_privilege('authenticated',f.oid,'EXECUTE'),false),
 exists(select 1 from pg_proc p cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
        where p.oid=f.oid and a.grantee=0 and a.privilege_type='EXECUTE')
from f"""

def checked_psql(name, sql, database='postgres'):
    result = original_psql(name, sql, database)
    if sql == module.SELFHOST_FINGERPRINT_SQL:
        info = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
        assert info['HostConfig']['NetworkMode'] == 'none'
        assert info['HostConfig']['Memory'] == 1073741824
        assert info['HostConfig']['NanoCpus'] == 1000000000
        assert not info['HostConfig'].get('PortBindings')
        assert info['Image'] == meta['image_id']
        assert all(m['Source'].startswith(str(folder / 'isolated-restore') + '/') for m in info['Mounts'])
        value = original_psql(name, query).decode().strip()
        proof.update(container_id=info['Id'], image_id=info['Image'], network_mode='none', memory_bytes=info['HostConfig']['Memory'], nano_cpus=info['HostConfig']['NanoCpus'], port_bindings=0, isolated_mounts=len(info['Mounts']), function_acl=value)
        assert value == '24d842da7d29e681c16a79954dc9e130|t|f|f|f', value
    return result

module.selfhost_psql = checked_psql
receipt = module.selfhost_restore(folder, pg, expected)
assert proof and receipt['dump_sha256'] == '590fda5f27c856299b5aa66d37cfe97893bec95460c6cabea0f5c2fc43efe562'
assert receipt['auth_users_verified'] and receipt['vault_decryption_verified'] and receipt['roles_verified']
assert receipt['external_network'] is False and receipt['services_started'] == ['postgres']
cleanup = subprocess.run(['docker', 'inspect', proof['container_id']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
assert cleanup.returncode != 0, 'isolated container cleanup not confirmed'
proof.update(dump_sha256=receipt['dump_sha256'], roles_sha256=receipt['roles_sha256'], source_fingerprint_sha256='34f236e031750e5d049254374cb8cffcf72941d1d12337e3f7d02ab4a7979a29', table_count=len(receipt['tables']), auth_users_verified=True, vault_decryption_verified=True, roles_verified=True, fingerprint_equal=True, container_removed=True)
(base / 'result-private.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
print('ISOLATED_FULL_RESTORE_V4_OK', proof['container_id'], proof['dump_sha256'], proof['function_acl'], proof['table_count'], 'cleanup=true')
