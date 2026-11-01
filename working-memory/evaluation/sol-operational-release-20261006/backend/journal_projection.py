"""Rebuildable SQLite projection of the authoritative Supabase journal.

Reconstruction consumes saved proposals and explicit human decisions, never a
model API. Semantic drift fails checksum verification rather than silently
changing accepted results after a code upgrade.
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from memory import connect,register,claim,apply,ValidationError,fingerprint
from human_decisions import record

FORMAT='wm-source-batch-v1'
LINK_FORMAT='wm-source-batch-v2'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def verify_source(source):
    required={'id','source_id','content_hash','event_date','title','transcript','observed_at'}
    if not required<=set(source):raise ValidationError('Incomplete pinned source')
    if fingerprint(source['transcript'])!=source['content_hash'] or fingerprint(source['source_id']+':'+source['content_hash'])!=source['id']:
        raise ValidationError('Pinned source checksum mismatch')
    if not datetime.fromisoformat(source['observed_at'].replace('Z','+00:00')).tzinfo:
        raise ValidationError('Source observation time requires a timezone')


def apply_saved(db, source, payload):
    verify_source(source)
    if payload.get('format') not in (FORMAT,LINK_FORMAT) or not isinstance(payload.get('pipeline'),str) or not payload['pipeline']:
        raise ValidationError('Unknown source batch format')
    if payload['format']==FORMAT and 'matter_links' in payload:
        raise ValidationError('Matter links require the explicitly versioned batch format')
    if payload['format']==LINK_FORMAT:
        from matter_links import validate as validate_links
        validate_links(db,source,payload.get('matter_links'))
    job=register(db,source_id=source['source_id'],event_date=source['event_date'],title=source['title'],
                 transcript=source['transcript'],pipeline=payload['pipeline'])
    token=claim(db,job)
    if token is None:raise ValidationError('Source batch was already materialized')
    db.execute('UPDATE source_versions SET observed_at=? WHERE id=?',
               (datetime.fromisoformat(source['observed_at'].replace('Z','+00:00')).timestamp(),source['id']))
    items=apply(db,job,token,payload['proposal'],model='saved-journal:'+payload.get('model','unknown'),
                usage=payload.get('usage',{}),human_guard=payload.get('human_guard','legacy'))
    result_hash=digest(items)
    if payload['format']==LINK_FORMAT:
        from matter_links import record as record_links
        links=record_links(db,source,payload['matter_links'])
        result_hash=digest({'observations':items,'matter_links':links})
    if payload.get('result_sha256') and payload['result_sha256']!=result_hash:
        raise ValidationError('Saved results differ under current rules; explicit projection upgrade required')
    return result_hash


def apply_redacted_saved(db, package):
    """Replay accepted derivations from an attested evidence-only source.

    The sparse buffer is an internal validation surface, never exposed as an
    original.  It contains only retained quotes at their verified offsets and
    filler everywhere else; the original identity/hash remain metadata.
    """
    from original_deletion import verify_redacted_entry
    status=verify_redacted_entry(package)
    source=package['source'];payload=package['retained_payload'];manifest=package['evidence_manifest']
    chars=['\u2591']*manifest['original_characters']
    for item in manifest['entries']:
        for offset,char in enumerate(item['quote'],item['start']):
            if chars[offset] not in ('\u2591',char):raise ValidationError('Overlapping retained evidence differs')
            chars[offset]=char
    transcript=''.join(chars)
    if payload.get('format') not in (FORMAT,LINK_FORMAT) or not isinstance(payload.get('pipeline'),str) or not payload['pipeline']:
        raise ValidationError('Unknown redacted source batch format')
    if payload['format']==LINK_FORMAT:
        from matter_links import validate as validate_links
        validate_links(db,{**source,'transcript':transcript},payload.get('matter_links'))
    from datetime import datetime
    observed=datetime.fromisoformat(source['observed_at'].replace('Z','+00:00')).timestamp()
    job=fingerprint(source['id']+':'+payload['pipeline'])
    db.execute('INSERT INTO source_versions VALUES (?,?,?,?,?,?,?)',
               (source['id'],source['source_id'],source['content_hash'],source['event_date'],observed,source['title'],transcript))
    db.execute("INSERT INTO jobs(id,source_version,pipeline,status) VALUES (?,?,?,'queued')",
               (job,source['id'],payload['pipeline']))
    token=claim(db,job)
    items=apply(db,job,token,payload['proposal'],model='redacted-journal:'+payload.get('model','unknown'),
                usage=payload.get('usage',{}),human_guard=payload.get('human_guard','legacy'))
    result_hash=digest(items)
    if payload['format']==LINK_FORMAT:
        from matter_links import record as record_links
        links=record_links(db,{**source,'transcript':transcript},payload['matter_links'])
        result_hash=digest({'observations':items,'matter_links':links})
    if payload.get('result_sha256')!=result_hash or status['source_version']!=source['id']:
        raise ValidationError('Redacted source results differ under current rules')
    return result_hash


def prepare_source(db, source, proposal, *, pipeline, model, provenance, usage=None, matter_links=None, human_guard='field-v1'):
    """Verify on a disposable copy before proposing any durable append."""
    if human_guard not in ('legacy','field-v1'):raise ValidationError('Unknown human update guard')
    scratch=connect(':memory:')
    try:
        db.backup(scratch)
        from matter_links import setup as setup_links
        setup_links(scratch)
        payload={'format':FORMAT,'pipeline':pipeline,'model':model,'proposal':proposal,
                 'provenance':provenance,'usage':usage or {}}
        # Absence is the immutable legacy wire format.  New batches name their
        # field-specific rule explicitly; old accepted generation packages can
        # therefore still reproduce byte for byte.
        if human_guard!='legacy':payload['human_guard']=human_guard
        if matter_links is not None:
            payload.update(format=LINK_FORMAT,matter_links=matter_links)
        payload['result_sha256']=apply_saved(scratch,source,payload)
        return payload
    finally:scratch.close()


def rebuild(store, destination, *, through=None, _logical_base=None):
    space=store.space()
    ceiling=space['revision'] if through is None else through
    if ceiling>space['revision']:raise ValidationError('Requested future journal revision')
    target=Path(destination);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,path=tempfile.mkstemp(prefix='.'+space['id']+'-projection-',suffix='.sqlite',dir=target.parent)
    os.close(fd)
    db=None
    try:
        db=connect(path)
        from generation_review import logical_entries,verify_generation
        if _logical_base is not None:
            # The existing service verifies the complete transport/binding and
            # returns request-owned RAW entries; still replay every Source/Human.
            from generation_review import _materialize_into
            _materialize_into(db,_logical_base({**space,'revision':ceiling}))
        else:
            entries=list(store.entries(through=ceiling))
            checkpoints=[(index,entry) for index,entry in enumerate(entries) if entry['kind']=='redaction']
            logical=[];start=0
            if checkpoints:
                index,checkpoint=checkpoints[-1]
                from projection_snapshot import apply_snapshot
                if checkpoint['payload'].get('through_revision')!=checkpoint['revision']-1:
                    raise ValidationError('Projection snapshot does not cover the preceding journal boundary')
                apply_snapshot(db,checkpoint['payload']);logical=checkpoint['payload']['logical_basis'];start=index+1
            for entry in entries[start:]:
                if entry['kind']=='source':
                    if not entry['payload'].get('result_sha256'):
                        raise ValidationError('Source batch lacks an accepted result checksum')
                    source=entry.get('source') or store.source(entry['source_version'])
                    if source['id']!=entry['source_version']:raise ValidationError('Journal source reference mismatch')
                    apply_saved(db,source,entry['payload'])
                    logical.extend(logical_entries([{**entry,'source':source}]))
                elif entry['kind']=='human':
                    record(db,command_id=entry['command_id'],actor_id=entry['actor_id'],command=entry['payload'])
                    logical.extend(logical_entries([entry]))
                elif entry['kind']=='generation':
                    generation,logical=verify_generation(logical,entry['payload'],_projection=True,_base_projection=db)
                    try:generation.backup(db)
                    finally:generation.close()
                else:raise ValidationError('Unknown journal entry')
        db.execute('CREATE TABLE projection_cursor (space_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)')
        db.execute('INSERT INTO projection_cursor VALUES (?,?)',(space['id'],ceiling))
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
        db.close();db=None
        os.chmod(path,0o600)
        os.replace(path,target)
        return {'space_id':space['id'],'revision':ceiling,'source':'supabase_journal'}
    finally:
        if db:db.close()
        for suffix in ('','-wal','-shm'):
            try:Path(path+suffix).unlink()
            except FileNotFoundError:pass
