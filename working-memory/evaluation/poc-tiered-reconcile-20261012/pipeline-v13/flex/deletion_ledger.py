"""Independent monotonic restore barrier for original-source deletions."""
import fcntl,json,os,tempfile
from pathlib import Path
from journal_projection import digest
from memory import ValidationError

FORMAT='wm-restore-deletion-ledger-v1'
STATES=('prepared','purging','verified')

def _validate(payload, *, space_id):
    expected=payload.get('ledger_sha256') if isinstance(payload,dict) else None
    if (not isinstance(payload,dict) or payload.get('format')!=FORMAT or payload.get('space_id')!=space_id
        or type(payload.get('minimum_deletion_revision')) is not int or payload['minimum_deletion_revision']<0
        or not isinstance(payload.get('deletions'),list) or expected!=digest({k:v for k,v in payload.items() if k!='ledger_sha256'})):
        raise ValidationError('Invalid external deletion ledger')
    identities={}
    for item in payload['deletions']:
        if (not isinstance(item,dict) or not isinstance(item.get('deletion_id'),str) or not item['deletion_id']
            or not isinstance(item.get('source_id'),str) or not item['source_id'] or item['deletion_id'] in identities
            or ('state' in item and item['state'] not in STATES)):
            raise ValidationError('Invalid external deletion ledger')
        identities[item['deletion_id']]=item
    return identities

def _payload(*, space_id, minimum_deletion_revision, deletions, observed_at):
    if type(minimum_deletion_revision) is not int or minimum_deletion_revision<0:
        raise ValidationError('Invalid restore deletion watermark')
    if not isinstance(deletions,list):raise ValidationError('Invalid restore deletion ledger')
    payload={'format':FORMAT,'space_id':space_id,'minimum_deletion_revision':minimum_deletion_revision,
             'deletions':deletions,'observed_at':observed_at}
    payload['ledger_sha256']=digest(payload);_validate(payload,space_id=space_id)
    return payload

def _assert_monotonic(previous, current, *, space_id):
    old=_validate(previous,space_id=space_id);new=_validate(current,space_id=space_id)
    if current['minimum_deletion_revision']<previous['minimum_deletion_revision']:
        raise ValidationError('Restore deletion watermark must not decrease')
    for deletion_id,old_item in old.items():
        new_item=new.get(deletion_id)
        if new_item is None or new_item['source_id']!=old_item['source_id']:
            raise ValidationError('Existing deletion identity must not disappear')
        old_state,new_state=old_item.get('state'),new_item.get('state')
        if old_state and new_state and STATES.index(new_state)<STATES.index(old_state):
            raise ValidationError('Deletion state must not regress')

def _replace_private(target,payload):
    descriptor,temporary=tempfile.mkstemp(prefix='.'+target.name+'.',suffix='.tmp',dir=target.parent)
    try:
        os.fchmod(descriptor,0o600)
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            descriptor=None;json.dump(payload,stream,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target)
        directory=os.open(target.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if descriptor is not None:os.close(descriptor)
        if os.path.exists(temporary):os.unlink(temporary)

def write(path, *, space_id, minimum_deletion_revision, deletions, observed_at):
    payload=_payload(space_id=space_id,minimum_deletion_revision=minimum_deletion_revision,deletions=deletions,observed_at=observed_at)
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    descriptor=os.open(target.with_name('.'+target.name+'.lock'),os.O_CREAT|os.O_RDWR,0o600)
    try:
        os.fchmod(descriptor,0o600);fcntl.flock(descriptor,fcntl.LOCK_EX)
        if target.exists():_assert_monotonic(read(target,space_id=space_id),payload,space_id=space_id)
        _replace_private(target,payload)
    finally:
        fcntl.flock(descriptor,fcntl.LOCK_UN);os.close(descriptor)
    return payload

def read(path, *, space_id):
    try:payload=json.loads(Path(path).read_text())
    except (OSError,json.JSONDecodeError):raise ValidationError('A current external deletion ledger is required for restore') from None
    _validate(payload,space_id=space_id)
    return payload
