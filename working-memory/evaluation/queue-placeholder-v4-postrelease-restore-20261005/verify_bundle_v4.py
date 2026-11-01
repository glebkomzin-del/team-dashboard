"""Read-only V4 backup byte/identity check; extracts only the image to private temp."""

import hashlib
import json
from pathlib import Path
import tarfile
import tempfile

STATUS = Path('/opt/dashboard-memory-canonical-draft/.local/cache/backup-status.json')
BACKUPS = Path('/var/backups/dashboard-job')
IMAGE = 'sha256:2c935de2b6c458810c67dbe7b10e07ec8ee06a97bbca305bc9e8582bf5e3e6cb'
TAG = 'dashboard-memory:queue-placeholder-20261005-b3e22868'
OCT = 'schema/20261005133858_archive_verified_image_placeholder_job.sql'
EXPECTED = {
    'runtime/build-manifest.json': '608fe3b0f1c2d6cd6a145c49a05cc2444009192a1193bc15c3f70fa3691cbbb5',
    'runtime/restore_schema.py': '5963514dca18c8bcf2f3fc28560063fe4030021251bc43ed44cdf376991838c1',
    'runtime/Dockerfile': 'cca2bfa626af28763c29ea29614b20ee2965b0e9ddabd7c1a5d8c746428300f5',
    'runtime/scheduled_backup.py': '954e5f163387952b6b7074e5ec3d6938cd9fbedc0473044f3fecd5d8c56d29ec',
    OCT: '22ac14542d1f2ec8a025e831b5f8c7f4fb23de7ea1dbf3a19a726e6ed99a5f5d',
}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    status = json.loads(STATUS.read_text())
    assert status['state'] == 'ok'
    assert status['started_at'] == '2026-10-05T19:02:10.966637+00:00'
    name = status['archive']
    assert Path(name).name == name and name.startswith('dashboard-') and name.endswith('.tar.gz')
    archive = BACKUPS / name
    archive_hash = digest(archive)
    assert archive_hash == status['sha256']
    small = {'bundle-manifest.json', 'runtime-images.json',
             'configuration/memory-compose.yaml', 'runtime/build-manifest.json'}
    hashes, contents, names = {}, {}, set()
    with tempfile.TemporaryDirectory(prefix='v4-image-check-', dir='/root/dashboard-v4-restore-test-20261005') as tmp:
        image_path = Path(tmp) / 'memory-image.tar'
        with tarfile.open(archive, 'r|gz') as bundle:
            for member in bundle:
                path = member.name
                names.add(path)
                wanted = (path in small or path in EXPECTED or path == 'memory-image.tar'
                          or path.startswith('schema/') or path.startswith('runtime/schema/'))
                if not member.isfile() or not wanted:
                    continue
                h = hashlib.sha256()
                chunks = []
                with bundle.extractfile(member) as source:
                    target = image_path.open('wb') if path == 'memory-image.tar' else None
                    try:
                        for chunk in iter(lambda: source.read(1024 * 1024), b''):
                            h.update(chunk)
                            if path in small:
                                chunks.append(chunk)
                            if target is not None:
                                target.write(chunk)
                    finally:
                        if target is not None:
                            target.close()
                hashes[path] = h.hexdigest()
                if path in small:
                    contents[path] = b''.join(chunks)
        listed = json.loads(contents['bundle-manifest.json'])['files']
        assert all(path in listed and listed[path]['sha256'] == value
                   for path, value in hashes.items() if path != 'bundle-manifest.json')
        assert all(hashes[path] == value for path, value in EXPECTED.items()), [(path, hashes.get(path), value) for path, value in EXPECTED.items() if hashes.get(path) != value]
        metadata = json.loads(contents['runtime-images.json'])['memory']
        assert metadata == {'image_id': IMAGE, 'configured_image': TAG}
        assert contents['configuration/memory-compose.yaml'].decode().count('image: ' + TAG) == 1
        build = json.loads(contents['runtime/build-manifest.json'])
        source_format = (json.dumps(build, sort_keys=True, indent=2) + '\n').encode()
        assert hashlib.sha256(source_format).hexdigest() == 'bbb1bda7b73b7dc9f885129c6fec83cdd6b23435ecf493c20dd86f39e254d85c'
        sources = {key for key in build if key.startswith('schema/')}
        assert len(sources) == 46
        assert {key for key in names if key.startswith('schema/') and key.endswith('.sql')} == sources
        assert all(key in hashes and 'runtime/' + key in hashes
                   and hashes[key] == hashes['runtime/' + key] == build[key] for key in sources)
        assert build[OCT] == EXPECTED[OCT]
        assert digest(image_path) == hashes['memory-image.tar']
        with tarfile.open(image_path) as image:
            index = json.load(image.extractfile('index.json'))
            manifest = json.load(image.extractfile('manifest.json'))
            assert any(entry['digest'] == IMAGE for entry in index['manifests'])
            assert manifest and manifest[0]['Config'] in image.getnames()
        print('BUNDLE_V4_OK', name, archive_hash, hashes['memory-image.tar'], len(sources), IMAGE)


if __name__ == '__main__':
    main()
