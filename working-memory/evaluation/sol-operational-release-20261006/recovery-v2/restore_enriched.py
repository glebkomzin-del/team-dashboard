"""Restore only a disposable network-none copy from the SHA-bound archive pair."""
import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile

WRAPPER_SHA = '89c804126b162e83a8dce7a0fc8a1929a38d24bc6b4fd98598c351f5c2227612'
SQL_SHA = 'c2394aa13faae4db8bd2c0ec033d169d194fccc00d8be02996c8c33f3d50e3d7'
INSTALLED_SHA = '954e5f163387952b6b7074e5ec3d6938cd9fbedc0473044f3fecd5d8c56d29ec'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def load_wrapper(folder):
    folder = Path(folder)
    for name, expected in (('full_backup_once.py', WRAPPER_SHA), ('enriched-fingerprint.sql', SQL_SHA)):
        path = folder / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('Missing or changed exact enriched recovery dependency: ' + name)
    spec = importlib.util.spec_from_file_location('enriched_final_backup', folder / 'full_backup_once.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_pair(receipt, full_archive, supplement_archive):
    pair = json.loads(Path(receipt).read_text())
    if pair.get('format') != 'dashboard-final-backup-pair-v1':
        raise ValueError('Missing explicit final backup/supplement pair receipt')
    for key, archive in (('full_backup', Path(full_archive)), ('supplement', Path(supplement_archive))):
        expected = pair[key]
        if (archive.is_symlink() or archive.name != expected['archive']
                or archive.stat().st_size != expected['bytes'] or digest(archive) != expected['sha256']):
            raise ValueError('Wrong archive pair member: ' + key)
    return pair


def bind_unpacked_backup(archive, folder):
    folder = Path(folder)
    with tarfile.open(archive, 'r:gz') as tar:
        with tar.extractfile('bundle-manifest.json') as stream:
            manifest = json.load(stream)
    if manifest.get('format') != 'dashboard-full-backup-v1':
        raise ValueError('Wrong full backup format')
    for relative, proof in manifest['files'].items():
        if not relative.startswith(('runtime/', 'selfhost/')):
            continue
        path = folder / relative
        if (Path(relative).is_absolute() or '..' in Path(relative).parts or path.is_symlink()
                or not path.is_file() or path.stat().st_size != proof['bytes'] or digest(path) != proof['sha256']):
            raise ValueError('Unpacked restore source differs from bound full archive: ' + relative)
    if digest(folder / 'runtime/scheduled_backup.py') != INSTALLED_SHA:
        raise ValueError('Archived backup runtime is not the required 954e5f version')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full-backup-archive', type=Path, required=True)
    parser.add_argument('--supplement-archive', type=Path, required=True)
    parser.add_argument('--paired-receipt', type=Path, required=True)
    parser.add_argument('--unpacked-full-backup', type=Path, required=True)
    parser.add_argument('--execute-isolated-restore', action='store_true')
    args = parser.parse_args()
    wrapper = load_wrapper(Path(__file__).parent)
    pair = validate_pair(args.paired_receipt, args.full_backup_archive, args.supplement_archive)
    bind_unpacked_backup(args.full_backup_archive, args.unpacked_full_backup)
    # Use archived source exclusively; never import a later installed backup.
    runtime = args.unpacked_full_backup / 'runtime'
    sys.path.insert(0, str(runtime))
    backup = importlib.import_module('scheduled_backup')
    backup.ROOT = runtime
    (runtime / '.local').mkdir(mode=0o700, exist_ok=True)
    wrapper.prepare(backup)
    if hashlib.sha256(backup.SELFHOST_FINGERPRINT_SQL.encode()).hexdigest() != SQL_SHA:
        raise ValueError('Generated restore SQL does not match the exact archived SQL')
    folder = args.unpacked_full_backup / 'selfhost'
    expected = json.loads((folder / 'source-fingerprint.json').read_text())
    if set(expected.get('row_integrity', {})) != set(wrapper.TABLES):
        raise ValueError('Full backup lacks the required 16-table enriched snapshot')
    if not args.execute_isolated_restore:
        print(json.dumps({'result': 'BOUND_ENRICHED_RECOVERY_PREPARED_NOT_EXECUTED',
                          'full_backup_sha256': pair['full_backup']['sha256'],
                          'supplement_sha256': pair['supplement']['sha256'], 'sql_sha256': SQL_SHA}))
        return
    image = json.loads((folder / 'runtime-image.json').read_text())
    database = {'Image': image['image_id'], 'Config': {'Cmd': image['command']}}
    # Existing implementation runs only PostgreSQL in network-none and removes
    # only its own disposable container/data. No live DB/gateway/worker reads.
    result = backup.selfhost_restore(folder, database, expected)
    print(json.dumps({'result': 'BOUND_ENRICHED_ISOLATED_RESTORE_VERIFIED',
                      'full_backup_sha256': pair['full_backup']['sha256'],
                      'supplement_sha256': pair['supplement']['sha256'], 'restore': result}))


if __name__ == '__main__':
    main()
