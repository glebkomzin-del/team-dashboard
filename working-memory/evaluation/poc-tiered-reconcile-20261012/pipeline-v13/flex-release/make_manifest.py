"""Update exactly two entries in a supplied production path -> SHA-256 map."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
TARGETS = ('openai_provider.py', 'call_budget.py')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest entry')
        result[key] = value
    return result


def updated_manifest(manifest, directory):
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError('Expected a nonempty path to SHA-256 object')
    if any(not isinstance(key, str) or not key or
           not isinstance(value, str) or re.fullmatch(r'[0-9a-fA-F]{64}', value) is None
           for key, value in manifest.items()):
        raise ValueError('Invalid manifest entry')
    if any(name not in manifest for name in TARGETS):
        raise ValueError('Production manifest must contain both exact target paths')
    result = dict(manifest)
    for name in TARGETS:
        result[name] = hashlib.sha256((Path(directory) / name).read_bytes()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('production_manifest', type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.production_manifest.read_text(), object_pairs_hook=unique_object)
    overlay = ROOT / 'overlay'
    for name in TARGETS:
        if (ROOT / name).read_bytes() != (overlay / name).read_bytes():
            raise ValueError('Overlay differs from the tested package')
    result = updated_manifest(manifest, overlay)
    (overlay / 'build-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print('ok manifest 2')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
