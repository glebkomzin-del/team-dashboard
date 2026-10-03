"""Risk checks: activation fails closed, roles remain, transfer covers additions."""
import hashlib, io, json, sys, tarfile, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import scheduled_backup as backup
from offserver_backup import verify_bundle

class BackupAdapterTests(unittest.TestCase):
    def test_hosted_without_marker_and_disabled_stage_keep_old_path(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backup,'ROOT',Path(directory)):
            cfg={'SUPABASE_URL':'https://existing.supabase.co'}
            self.assertFalse(backup.selfhost_enabled(cfg))
            marker=Path(directory)/'.local/selfhost-backup.json';marker.parent.mkdir();marker.write_text('{"enabled":false}')
            self.assertFalse(backup.selfhost_enabled(cfg))
            for origin in ('http://127.0.0.1:8800','https://178-105-167-26.nip.io/supabase','https://existing.supabase.co.evil'):
                with self.assertRaises(RuntimeError):backup.selfhost_enabled({'SUPABASE_URL':origin})
            marker.write_text('{"enabled":true}');self.assertTrue(backup.selfhost_enabled(cfg))
            marker.write_text('{"enabled":"true"}')
            with self.assertRaises(RuntimeError):backup.selfhost_enabled(cfg)

    def test_active_missing_database_fails_and_roles_preserve_credentials(self):
        with patch.object(backup,'selfhost_enabled',return_value=True),patch.object(backup,'container',return_value={'State':{'Running':False}}):
            with self.assertRaises(RuntimeError):backup.backup_selfhost(Path('/unused'),{})
        sql=b'CREATE ROLE postgres;\nALTER ROLE postgres WITH SUPERUSER PASSWORD \'private\';\nCREATE ROLE "a space";\nGRANT postgres TO "a space";\n'
        restored=backup.restore_roles_sql(sql,['postgres'])
        self.assertNotIn(b'CREATE ROLE postgres;',restored)
        self.assertIn(b"PASSWORD 'private'",restored)
        self.assertIn(b'CREATE ROLE "a space";',restored)
        self.assertIn(b'GRANT postgres',restored)

    def test_existing_transfer_verifier_covers_new_dump_and_private_config(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'bundle.tar.gz'
            files={'selfhost/postgres.dump':b'PGDMP fixture','selfhost/roles.sql':b'private roles',
                   'selfhost/configuration/.private.env':b'private configuration','selfhost/restore-check.json':b'{}'}
            manifest={'format':'dashboard-full-backup-v1','files':{name:{'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()} for name,body in files.items()}}
            def write():
                with tarfile.open(archive,'w:gz') as tar:
                    for name,body in {**files,'bundle-manifest.json':json.dumps(manifest).encode()}.items():
                        entry=tarfile.TarInfo(name);entry.size=len(body);tar.addfile(entry,io.BytesIO(body))
            write();self.assertEqual(verify_bundle(archive)['files_verified'],4)
            files['selfhost/configuration/.private.env']=b'tampered';write()
            with self.assertRaises(ValueError):verify_bundle(archive)

if __name__=='__main__':unittest.main()
