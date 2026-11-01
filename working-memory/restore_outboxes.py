"""Persist archived provider receipts after a paused database restore.

This program only retries the gateway receipt operations.  It never reserves or
sends a model request.  Run it on the host with the current runtime and service
environment, after the paused canonical SQL restore has committed.
"""
import argparse,hashlib,json,os,re,tempfile
from pathlib import Path

from durable_calls import drain_outbox,sha
from gateway_journal import GatewayJournal
from question_calls import drain_all_question_outbox

ROOT=Path('/opt/dashboard-memory-canonical-draft')
APP_UID=10001
APP_GID=10001
OUTBOX_NAMES=('response-outbox','question-outbox')
UUID='[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
MODEL_NAME=re.compile(r'^[0-9a-f]{64}-(?:0|[1-9][0-9]{0,3})\.json$')
QUESTION_NAME=re.compile('^question-'+UUID+r'-(?:0|[1-9][0-9]{0,3})\.json$')


def env_file(path):
    result={}
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            key,value=line.split('=',1);result[key]=value
    return result


def host_cache_path(container_path):
    path=Path(container_path)
    if not path.is_absolute():path=Path('/app')/path
    if '..' in path.parts or not path.is_relative_to('/app/.local'):
        raise RuntimeError('Unsupported receipt mount for restore')
    return ROOT/'.local/cache'/path.relative_to('/app/.local')


def configured_outboxes(cfg):
    cache=Path(cfg.get('MEMORY_CACHE_DIR','/app/.local/projections'))
    question=Path(cfg.get('MEMORY_QA_OUTBOX','/app/.local/question-outbox'))
    return {'response-outbox':host_cache_path(cache)/'response-outbox',
            'question-outbox':host_cache_path(question)}


def _validate_receipt(name,body,space_id):
    try:receipt=json.loads(body)
    except (TypeError,json.JSONDecodeError):raise RuntimeError('Archived receipt is not valid JSON') from None
    if not isinstance(receipt,dict):raise RuntimeError('Archived receipt is not an object')
    if name.startswith('question-'):
        match=QUESTION_NAME.fullmatch(name)
        question_id,index=name[9:-5].rsplit('-',1)
        if not match or receipt.get('question_id')!=question_id or receipt.get('call_index')!=int(index):
            raise RuntimeError('Question receipt identity does not match its filename')
    else:
        match=MODEL_NAME.fullmatch(name)
        job_id,index=name[:-5].rsplit('-',1)
        if not match or receipt.get('job_id')!=job_id or receipt.get('call_index')!=int(index):
            raise RuntimeError('Model receipt identity does not match its filename')
    if receipt.get('space_id')!=space_id or not isinstance(receipt.get('response_json'),str) or receipt.get('response_hash')!=sha(receipt['response_json']):
        raise RuntimeError('Archived receipt lacks its canonical scope or response')
    return body


def _copy_receipts(receipts,target):
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    if target.is_symlink() or not target.is_dir():raise RuntimeError('Live receipt directory is invalid')
    os.chown(target,APP_UID,APP_GID);os.chmod(target,0o700)
    copied=0
    for name,body in receipts:
        destination=target/name
        if destination.exists():
            if destination.is_symlink() or not destination.is_file() or destination.read_bytes()!=body:
                raise RuntimeError('Live receipt identity changed')
            continue
        fd,temporary=tempfile.mkstemp(prefix='.restore-receipt-',dir=target)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
            os.chmod(temporary,0o600);os.chown(temporary,APP_UID,APP_GID);os.replace(temporary,destination);copied+=1
            descriptor=os.open(target,os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
    return copied


def _receipt_manifest(archive):
    path=archive/'receipt-manifest.json';bundle=archive/'bundle-manifest.json'
    if path.is_symlink() or bundle.is_symlink() or not path.is_file() or not bundle.is_file():
        raise RuntimeError('Receipt bundle manifest is missing')
    try:proof=json.loads(bundle.read_text());manifest=json.loads(path.read_text())
    except json.JSONDecodeError:raise RuntimeError('Receipt bundle manifest is invalid') from None
    if not isinstance(proof,dict) or proof.get('format')!='dashboard-full-backup-v1' or not isinstance(proof.get('files'),dict):
        raise RuntimeError('Receipt bundle manifest format is invalid')
    record=proof['files'].get('receipt-manifest.json')
    if not isinstance(record,dict) or record.get('bytes')!=path.stat().st_size or record.get('sha256')!=hashlib.sha256(path.read_bytes()).hexdigest():
        raise RuntimeError('Receipt manifest is not covered by the bundle')
    if manifest.get('format')!='working-memory-receipts-v1' or not isinstance(manifest.get('outboxes'),dict):
        raise RuntimeError('Receipt manifest format is invalid')
    return proof['files'],manifest['outboxes']


def _preflight_receipts(store,archive):
    files,declared=_receipt_manifest(archive);result={}
    if set(declared)!=set(OUTBOX_NAMES):raise RuntimeError('Receipt manifest layout is invalid')
    for name,pattern in (('response-outbox',MODEL_NAME),('question-outbox',QUESTION_NAME)):
        rows=declared[name]
        if not isinstance(rows,list):raise RuntimeError('Receipt manifest entries are invalid')
        directory=archive/name;actual=[]
        if directory.exists():
            if directory.is_symlink() or not directory.is_dir():raise RuntimeError('Archived receipt directory is invalid')
            actual=sorted(directory.iterdir(),key=lambda path:path.name)
        expected=[]
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'name','bytes','sha256'} or not isinstance(row['name'],str) or not pattern.fullmatch(row['name']):
                raise RuntimeError('Receipt manifest entry is invalid')
            expected.append(row['name'])
        if [path.name for path in actual]!=expected:raise RuntimeError('Archived receipts do not match their manifest')
        values=[]
        for path,row in zip(actual,rows):
            if path.is_symlink() or not path.is_file():raise RuntimeError('Archived receipt is invalid')
            body=path.read_bytes()
            bundle_record=files.get(str(path.relative_to(archive)))
            if path.stat().st_size!=row['bytes'] or hashlib.sha256(body).hexdigest()!=row['sha256'] or bundle_record!={'bytes':row['bytes'],'sha256':row['sha256']}:
                raise RuntimeError('Archived receipt checksum is invalid')
            values.append((path.name,_validate_receipt(path.name,body,store.space_id)))
        result[name]=values
    return result


def restore_receipts(store,archive,outboxes):
    archive=Path(archive)
    if archive.is_symlink() or not archive.is_dir() or set(OUTBOX_NAMES)-set(outboxes):
        raise RuntimeError('Receipt restore layout is invalid')
    receipts=_preflight_receipts(store,archive)
    copied={name:_copy_receipts(receipts[name],outboxes[name]) for name in OUTBOX_NAMES}
    # These functions only submit already-hashed receipts. They never call a provider.
    saved={'response-outbox':drain_outbox(store,outboxes['response-outbox']),
           'question-outbox':drain_all_question_outbox(store,outboxes['question-outbox'])}
    return {'copied':copied,'persisted':saved,'model_calls':0}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',help='unpacked backup directory containing both receipt directories')
    parser.add_argument('--env-file',default=str(ROOT/'.local/service.env'))
    args=parser.parse_args(argv);cfg=env_file(args.env_file)
    required=('SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','MEMORY_JOURNAL_TOKEN','MEMORY_SPACE_ID')
    if any(not cfg.get(key) for key in required):raise RuntimeError('Scoped gateway configuration is incomplete')
    store=GatewayJournal(cfg['SUPABASE_URL'],cfg['SUPABASE_PUBLISHABLE_KEY'],cfg['MEMORY_JOURNAL_TOKEN'],cfg['MEMORY_SPACE_ID'])
    print(json.dumps(restore_receipts(store,args.archive,configured_outboxes(cfg)),sort_keys=True))


if __name__=='__main__':main()
