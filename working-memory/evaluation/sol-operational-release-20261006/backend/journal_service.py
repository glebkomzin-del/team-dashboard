"""Owner-facing application service over the canonical Supabase journal."""
from contextlib import contextmanager
from datetime import datetime
import os
import json,hashlib,sys
import sqlite3
from zoneinfo import ZoneInfo
from pathlib import Path
import threading
from uuid import UUID

from human_decisions import prepare
from journal_projection import rebuild
from canonical_archive import rebuild_archive
from archive_index import connect as open_archive
from journal_store import RevisionConflict
from generation_review import _logical_entries
from memory import ValidationError
from review_api import open_readonly

# Only fixed process code can certify reuse. Actual bytes are checked again on
# every lookup/admission; a mutable or incomplete runtime disables memoization.
def _generation_binding():
    root=Path(__file__).resolve().parent
    try:
        files=sorted(path for path in root.glob('*.py') if not path.name.startswith('test_'))
        rules=root/'evaluation/source-corrections.json'
        if not rules.is_file() or not files:return None
        identity=[(path.name,hashlib.sha256(path.read_bytes()).hexdigest()) for path in files]
        identity.append(('evaluation/source-corrections.json',hashlib.sha256(rules.read_bytes()).hexdigest()))
        return json.dumps([sys.version,sqlite3.sqlite_version,identity],separators=(',',':')).encode()
    except OSError:return None

_GENERATION_PROCESS_BINDING=_generation_binding()
_GENERATION_PREFIX_CAP=64*1024*1024

def _generation_cache_bytes(value):
    # Exact recursive object sizes for this immutable tuple/bytes/scalar entry.
    return sys.getsizeof(value)+(sum(_generation_cache_bytes(v) for v in value) if isinstance(value,tuple) else 0)

def _generation_bytes(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()

def business_date(instant=None):
    zone=ZoneInfo(os.environ.get('MEMORY_TIME_ZONE','Europe/Berlin'))
    if instant is not None and instant.tzinfo is None:raise ValidationError('Decision time requires timezone')
    return (instant.astimezone(zone) if instant is not None else datetime.now(zone)).date().isoformat()


class JournalService:
    def __init__(self, store, cache_directory):
        self.store=store
        self.cache=Path(cache_directory)
        self.lock=threading.RLock()
        self.projection_lock=threading.Lock()
        self.archive_lock=threading.Lock()
        self.cache_condition=threading.Condition()
        self.cache_readers=0
        self.cache_maintenance=False
        self.privacy_condition=threading.Condition()
        self.privacy_readers=0
        self.privacy_maintenance=False
        self.privacy_cleanups=[]
        self.private_outboxes=[]
        self.generation_prefix_lock=threading.Lock()
        self.generation_prefix=None
        self.generation_privacy=threading.local()
        self.register_privacy_cleanup(self._clear_generation_prefix)

    @contextmanager
    def generation_reader(self):
        # Generation routes hold this through response serialization. Core
        # calls in the same thread borrow that real reader, never enter the
        # non-reentrant privacy_reader twice while maintenance is waiting.
        depth=getattr(self.generation_privacy,'depth',0)
        if depth:
            self.generation_privacy.depth=depth+1
            try:yield
            finally:self.generation_privacy.depth=depth
        else:
            with self.privacy_reader():
                self.generation_privacy.depth=1
                try:yield
                finally:self.generation_privacy.depth=0

    def _clear_generation_prefix(self):
        with self.generation_prefix_lock:self.generation_prefix=None

    def generation_base(self,space):
        # _scope has already fetched and authorized this space. No auth, review,
        # CAS, archive, config or cost result is memoized here.
        with self.generation_reader():
            entries=self.store.entries(through=space['revision'])
            epoch=space.get('deletion_revision')
            binding=_generation_binding()
            supported=(type(epoch) is int and epoch>=0 and isinstance(space.get('id'),str)
                       and binding is not None and binding==_GENERATION_PROCESS_BINDING)
            if not supported:
                self._clear_generation_prefix()
                return _logical_entries(entries)[0]
            if len(entries)!=space['revision'] or any(type(e.get('revision')) is not int or e['revision']!=n for n,e in enumerate(entries,1)):
                raise ValidationError('Generation needs the full contiguous journal')
            with self.generation_prefix_lock:
                # A cold request may have occupied this lock for a long time.
                # Re-read authority/rules after waiting, before any lookup.
                current=self.store.space()
                if current.get('id')!=space['id']:
                    self.generation_prefix=None
                    raise ValidationError('Generation space changed')
                if type(current.get('deletion_revision')) is int and current['deletion_revision']!=epoch:
                    self.generation_prefix=None
                    raise RevisionConflict('Generation deletion boundary changed')
                if type(current.get('deletion_revision')) is not int or _generation_binding()!=binding:
                    self.generation_prefix=None
                    return _logical_entries(entries)[0]
                cached=self.generation_prefix;seed=None;offset=0
                if cached is not None:
                    scope,prior_binding,count,inputs,outputs,input_hash,output_hash=cached
                    if (scope==(space['id'],epoch) and prior_binding==binding and type(count) is int
                        and 0<count<=len(entries) and isinstance(inputs,bytes) and isinstance(outputs,bytes)
                        and _generation_cache_bytes(cached)<=_GENERATION_PREFIX_CAP
                        and hashlib.sha256(inputs).digest()==input_hash
                        and hashlib.sha256(outputs).digest()==output_hash
                        and not any(e.get('kind')=='redaction' for e in entries[count:])
                        and _generation_bytes(entries[:count])==inputs):
                        seed=json.loads(outputs);offset=count
                    else:self.generation_prefix=None
                logical,certified=_logical_entries(entries[offset:],_seed=seed)
                if certified is not None:
                    count,raw=certified;count+=offset
                    inputs=_generation_bytes(entries[:count]);outputs=_generation_bytes(raw)
                    # Recheck the actual rules and authoritative deletion epoch
                    # after cold proof, before atomically publishing any bytes.
                    current=self.store.space()
                    candidate=((space['id'],epoch),binding,count,inputs,outputs,hashlib.sha256(inputs).digest(),hashlib.sha256(outputs).digest())
                    if (current.get('id')==space['id'] and type(current.get('deletion_revision')) is int
                        and current['deletion_revision']==epoch and _generation_binding()==binding
                        and _generation_cache_bytes(candidate)<=_GENERATION_PREFIX_CAP):
                        self.generation_prefix=candidate
                    else:self.generation_prefix=None
                return logical

    @contextmanager
    def cache_reader(self):
        """Keep privacy maintenance from unlinking a cache still being read."""
        with self.cache_condition:
            while self.cache_maintenance:self.cache_condition.wait()
            self.cache_readers+=1
        try:yield
        finally:
            with self.cache_condition:
                self.cache_readers-=1
                if not self.cache_readers:self.cache_condition.notify_all()

    @contextmanager
    def exclusive_cache_maintenance(self):
        """Drain active readers and block new ones during cache invalidation."""
        with self.cache_condition:
            while self.cache_maintenance:self.cache_condition.wait()
            self.cache_maintenance=True
            while self.cache_readers:self.cache_condition.wait()
        try:yield
        finally:
            with self.cache_condition:
                self.cache_maintenance=False
                self.cache_condition.notify_all()

    @contextmanager
    def privacy_reader(self):
        """Keep deletion from overtaking work that may hold original text."""
        with self.privacy_condition:
            while self.privacy_maintenance:self.privacy_condition.wait()
            self.privacy_readers+=1
        try:yield
        finally:
            with self.privacy_condition:
                self.privacy_readers-=1
                if not self.privacy_readers:self.privacy_condition.notify_all()

    @contextmanager
    def exclusive_privacy_maintenance(self):
        """Drain source-consuming work and block new work through one purge."""
        with self.privacy_condition:
            while self.privacy_maintenance:self.privacy_condition.wait()
            self.privacy_maintenance=True
            while self.privacy_readers:self.privacy_condition.wait()
        try:yield
        finally:
            with self.privacy_condition:
                self.privacy_maintenance=False
                self.privacy_condition.notify_all()

    def register_privacy_cleanup(self,callback):
        if not callable(callback):raise ValueError('Privacy cleanup must be callable')
        with self.privacy_condition:
            if callback not in self.privacy_cleanups:self.privacy_cleanups.append(callback)

    def register_private_outbox(self,kind,path):
        if kind not in ('model','question'):raise ValueError('Unknown private outbox kind')
        value=(kind,Path(path))
        if value not in self.private_outboxes:self.private_outboxes.append(value)

    def clear_private_runtime(self):
        """Clear completed in-memory responses while deletion owns the barrier."""
        with self.privacy_condition:
            if not self.privacy_maintenance:raise RuntimeError('Privacy cleanup requires exclusive maintenance')
            callbacks=tuple(self.privacy_cleanups)
        for callback in callbacks:callback()

    def authorize(self, identity, space):
        if identity.get('role')!='owner' or identity.get('id')!=space['owner_id']:
            raise PermissionError('This account cannot access the selected working memory')

    def prune(self, directory, space_id, current):
        # Finalized snapshots use DELETE journal mode, so an open POSIX reader
        # remains valid after unlink and no shared WAL sidecars can be reused.
        candidates=[]
        for path in directory.glob(space_id+'-*.sqlite'):
            version=path.stem.removeprefix(space_id+'-')
            parts=version.split('-')
            if all(part.isdigit() for part in parts) and len(parts) in (1,2) and not path.is_symlink():
                candidates.append((tuple(map(int,parts[::-1])),path))
        for _,path in sorted(candidates,reverse=True)[3:]:
            if path!=current:
                try:path.unlink()
                except OSError:pass  # Cache retention failure cannot undo a completed owner response.

    def _open_projection(self, space, *, archive=False):
        directory=self.cache/'archive' if archive else self.cache
        revision=space['archive_revision' if archive else 'revision']
        target=directory/(f"{space['id']}-{revision}-{space['revision']}.sqlite" if archive else f"{space['id']}-{revision}.sqlite")
        lock=self.archive_lock if archive else self.projection_lock
        opener=open_archive if archive else open_readonly
        def open_target():
            return opener(target,readonly=True) if archive else opener(target)
        # Existing immutable files remain readable while a newer revision builds.
        # Opening under the build lock also protects against concurrent pruning.
        if not lock.acquire(blocking=False):
            try:
                db=open_target()
                return db
            except (OSError, sqlite3.OperationalError):
                lock.acquire()
        try:
            if not target.exists():
                builder=rebuild_archive if archive else rebuild
                # Preserve the original checkpoint/table replay for every
                # deletion boundary or unknown epoch; only the intact scope
                # can reuse this service's existing full RAW certificate.
                epoch=space.get('deletion_revision')
                logical_base=(self.generation_base if type(epoch) is int and epoch==0
                              and getattr(self.generation_privacy,'depth',0)>0 else None)
                reuse={} if logical_base is None else {'_logical_base':logical_base}
                if archive:builder(self.store,target,through=revision,journal_through=space['revision'],**reuse)
                else:builder(self.store,target,through=revision,**reuse)
            db=open_target()
            self.prune(directory,space['id'],target)
            return db
        finally:
            lock.release()

    @contextmanager
    def archive_projection(self, identity):
        with self.cache_reader():
            space=self.store.space();self.authorize(identity,space)
            db=self._open_projection(space,archive=True)
            try:
                cursor=db.execute('SELECT space_id,revision FROM archive_cursor').fetchone()
                if tuple(cursor)!=(space['id'],space['archive_revision']):raise ValidationError('Archive cache cursor mismatch')
                yield db,space
            finally:db.close()

    @contextmanager
    def projection(self, identity):
        with self.cache_reader():
            space=self.store.space();self.authorize(identity,space)
            db=self._open_projection(space)
            try:
                cursor=db.execute('SELECT space_id,revision FROM projection_cursor').fetchone()
                if tuple(cursor)!=(space['id'],space['revision']):raise ValidationError('Cache cursor mismatch')
                yield db,space
            finally:db.close()

    @contextmanager
    def question_projections(self, identity, *, revision, archive_revision):
        """Open one owner-authorized, revision-pinned work/archive view."""
        with self.cache_reader():
            space=self.store.space();self.authorize(identity,space)
            if not (0<=revision<=space['revision'] and 0<=archive_revision<=space['archive_revision']):
                raise RevisionConflict('The pinned question revision is unavailable')
            pinned={**space,'revision':revision,'archive_revision':archive_revision}
            work=self._open_projection(pinned);archive=None
            try:
                archive=self._open_projection(pinned,archive=True)
                cursor=work.execute('SELECT space_id,revision FROM projection_cursor').fetchone()
                archive_cursor=archive.execute('SELECT space_id,revision FROM archive_cursor').fetchone()
                if tuple(cursor)!=(space['id'],revision) or tuple(archive_cursor)!=(space['id'],archive_revision):
                    raise ValidationError('Question projection cursor mismatch')
                yield work,archive,pinned
            finally:
                work.close()
                if archive is not None:archive.close()

    def warm_projection(self, *, archive=False):
        """Prepare the latest immutable revision without waiting for a page visit."""
        space=self.store.space()
        identity={'role':'owner','id':space['owner_id']}
        projection=self.archive_projection if archive else self.projection
        # Enter privacy before the cache reader, preserving deletion's lock
        # order. Existing purge calls own maintenance and keep the old path.
        if type(space.get('deletion_revision')) is int and space['deletion_revision']==0 and not self.privacy_maintenance:
            with self.generation_reader(),projection(identity):pass
        else:
            with projection(identity):pass

    def decide(self, identity, request):
        keys={'command_id','expected_revision','action','target_id','reason','patch'}
        if not isinstance(request,dict) or set(request)-{'feedback_kind'}!=keys:
            raise ValidationError('Invalid decision request')
        command_id=str(UUID(request['command_id']))
        if type(request['expected_revision']) is not int or request['expected_revision']<0:
            raise ValidationError('Invalid expected revision')
        content={key:request[key] for key in ('action','target_id','reason','patch')}
        if 'feedback_kind' in request:content['feedback_kind']=request['feedback_kind']
        with self.lock:
            space=self.store.space();self.authorize(identity,space)
            previous=self.store.command(command_id)
            if previous:
                if previous['kind']!='human' or previous['actor_id']!=identity['id'] or any(previous['payload'].get(k)!=v for k,v in content.items()):
                    raise RevisionConflict('Decision ID reused with different content')
                return {'revision':previous['revision'],'repeated':True}
            if request['expected_revision']!=space['revision']:
                raise RevisionConflict('The working memory changed; refresh before deciding')
            command={**content,'event_date':business_date()}
            with self.projection(identity) as (db,current):
                if current['revision']!=request['expected_revision']:
                    raise RevisionConflict('The working memory changed; refresh before deciding')
                prepare(db,command)
            # A concurrent writer on another process is checked by the RPC lock.
            return self.store.append(expected_revision=request['expected_revision'],command_id=command_id,
                kind='human',payload=command,actor_id=identity['id'])
