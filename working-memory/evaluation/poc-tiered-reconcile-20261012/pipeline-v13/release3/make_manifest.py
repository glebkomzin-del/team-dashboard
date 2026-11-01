"""Update only overlay runtime payload entries in a supplied path-to-SHA256 map."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent
# Reused from ../release2/make_manifest.py; only Release-3 COPY payloads differ.
TARGETS=('candidate_filter.py','hybrid_pipeline.py','offline_check.py','default_contract.json')
EXISTING=TARGETS

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate manifest entry')
        result[key]=value
    return result

def updated_manifest(manifest,directory):
    if not isinstance(manifest,dict) or not manifest or any(not isinstance(k,str) or not k or not isinstance(v,str) or re.fullmatch('[0-9a-fA-F]{64}',v) is None for k,v in manifest.items()):
        raise ValueError('Expected path-to-SHA256 map')
    if any(name not in manifest for name in EXISTING):raise ValueError('Production manifest missing modified module')
    result=dict(manifest)
    for name in TARGETS:result[name]=hashlib.sha256((Path(directory)/name).read_bytes()).hexdigest()
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('production_manifest',type=Path)
    parser.add_argument('--local-version',action='store_true');args=parser.parse_args(argv)
    manifest=json.loads(args.production_manifest.read_text(),object_pairs_hook=unique_object)
    updated=updated_manifest(manifest,ROOT/'overlay')
    (ROOT/'overlay/build-manifest.json').write_text(json.dumps(updated,indent=2)+'\n')
    print('manifest '+str(len(TARGETS)))
    if args.local_version:
        sys.path.insert(0,str(ROOT));from local_support import configure,sources
        configure()
        with sources():
            import processor,canonical_worker
            processor.PROMPT_VERSION='v11'
            # Load the container checker, not its CLI wrapper.
            import importlib.util
            spec=importlib.util.spec_from_file_location('release_checker',ROOT/'overlay/offline_check.py')
            check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
            value=canonical_worker.pipeline_version('gpt-6.1-sol')
            if value!=check.independent_version(ROOT/'overlay'):raise ValueError('Version mismatch')
            print(value)
    return 0

if __name__=='__main__':raise SystemExit(main())
