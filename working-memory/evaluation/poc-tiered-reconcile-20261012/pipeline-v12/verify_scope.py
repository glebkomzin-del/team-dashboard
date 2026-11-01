"""Compare source timestamps and hashes without reading meeting bodies."""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WM = ROOT.parents[2]


def snapshot():
    data = {}
    for parent, dirs, files in os.walk(WM):
        dirs[:] = [d for d in dirs if Path(parent, d) != ROOT]
        for name in files:
            path = Path(parent, name)
            stat = path.lstat()
            data[str(path.relative_to(WM))] = [stat.st_mtime_ns, stat.st_size, stat.st_mode]
    return data


def main():
    evidence = ROOT / 'evidence'
    before = json.loads((evidence / 'source-timestamps-before.json').read_text())
    after = snapshot()
    result = {'before_files': len(before), 'after_files': len(after),
              'changed': sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
              'added': sorted(after.keys() - before.keys()), 'removed': sorted(before.keys() - after.keys())}
    manifest = json.loads((evidence / 'copy-manifest.json').read_text())
    result['source_hash_drift'] = []
    result['copy_changed'] = []
    diffs = []
    for relative, entry in manifest.items():
        source, copy = Path(entry['source']), ROOT / relative
        source_bytes, copy_bytes = source.read_bytes(), copy.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != entry['sha256']:
            result['source_hash_drift'].append(relative)
        if hashlib.sha256(copy_bytes).hexdigest() != entry['sha256']:
            result['copy_changed'].append(relative)
            if copy.suffix == '.py':
                diffs.extend(difflib.unified_diff(source_bytes.decode().splitlines(keepends=True),
                             copy_bytes.decode().splitlines(keepends=True), fromfile='original/'+relative,
                             tofile='pipeline-v12/'+relative))
    for copy in sorted((ROOT / 'backend').glob('*.py')):
        relative = str(copy.relative_to(ROOT))
        if relative not in manifest:
            diffs.extend(difflib.unified_diff([], copy.read_text().splitlines(keepends=True),
                         fromfile='/dev/null', tofile='pipeline-v12/'+relative))
    test_sources = {}
    for copy in sorted((ROOT / 'tests/existing').glob('*.py')):
        test_sources[copy.name] = copy.read_bytes() == (WM / copy.name).read_bytes()
    result['existing_test_copies_byte_identical'] = test_sources
    result['changed_python_parse_errors'] = []
    for path in [ROOT/'backend/candidate_filter.py', ROOT/'backend/hybrid_pipeline.py',
                 ROOT/'tests/test_hotset.py', ROOT/'run_tests.py', ROOT/'verify_scope.py']:
        try:
            ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            result['changed_python_parse_errors'].append(str(path.relative_to(ROOT)))
    (evidence / 'source-timestamps-after.json').write_text(json.dumps(after, sort_keys=True, indent=2)+'\n')
    (evidence / 'scope-verification.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    (evidence / 'backend.diff').write_text(''.join(diffs))
    print(json.dumps(result, sort_keys=True))
    return int(bool(result['changed'] or result['added'] or result['removed'] or result['source_hash_drift']
                    or result['changed_python_parse_errors'] or not all(test_sources.values())))


if __name__ == '__main__':
    raise SystemExit(main())
