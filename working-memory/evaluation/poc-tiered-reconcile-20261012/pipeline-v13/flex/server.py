"""Private HTTP adapter for n8n. Durable intake, one chronological worker, bounded requests."""
import sqlite3
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import re
import sys
import traceback
from urllib.error import HTTPError
from pathlib import Path
import threading
import time
from urllib.parse import urlparse,parse_qs
from review_api import open_readonly,review
from access import authenticate,AuthUnavailable
import archive_index
from memory import connect,register,overview,ValidationError,ReplayRequired
from processor import process,pipeline_version,DEFAULT_MODEL
from service_worker import Worker,policy
from journal_store import SupabaseJournal,JournalUnavailable,RevisionConflict
from journal_service import JournalService
from gateway_journal import GatewayJournal,TransientGateway
from canonical_archive import meeting_display_title,summaries as archive_summaries
from canonical_archive import verify_document
from drive_intake import persist_original
from canonical_worker import CanonicalWorker,pipeline_version as canonical_pipeline
from call_budget import BudgetExceeded
from durable_calls import OutcomeUnknown
from qa_service import AnswerUnverified,CompletionUnknown
from memory_chat import ConversationNotFound
from question_jobs import QuestionCapacity,QuestionJobs
from deletion_jobs import DeletionCapacity,DeletionJobs

DB=os.environ.get('MEMORY_DB','.local/service.sqlite')
TOKEN=os.environ.get('MEMORY_API_TOKEN','')
MODEL=os.environ.get('MEMORY_MODEL',DEFAULT_MODEL)
READ_ONLY=os.environ.get('MEMORY_READ_ONLY','0')=='1'
STOP=threading.Event()
ARCHIVE_DB=os.environ.get('MEMORY_ARCHIVE_DB','')
SUPABASE_URL=os.environ.get('SUPABASE_URL','')
SUPABASE_PUBLISHABLE_KEY=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
ALLOWED_USERS=tuple(filter(None,os.environ.get('MEMORY_ALLOWED_USERS','').split(',')))
MODE=os.environ.get('MEMORY_MODE','isolated-preview')
WORKER_STATUS={'state':'disabled' if READ_ONLY else 'starting'}
AUTOMATIC_ENABLED=os.environ.get('MEMORY_AUTOMATIC_ENABLED','0')=='1'
INTAKE_ENABLED=os.environ.get('MEMORY_INTAKE_ENABLED','0')=='1'
QA_ENABLED=os.environ.get('MEMORY_QA_ENABLED','0')=='1'
ORIGINAL_DELETION_ENABLED=os.environ.get('MEMORY_ORIGINAL_DELETION_ENABLED','0')=='1'
JOURNAL=None
QUESTION_SERVICE=None
CONVERSATIONS=None
QUESTION_JOBS=QuestionJobs()
DELETION_JOBS=DeletionJobs()

def question_budget(value):
    text=value.strip().lower()
    if text=='unlimited':return None
    try:budget=int(text)
    except ValueError:raise ValueError('Set MEMORY_QA_BUDGET_MICRO_USD to unlimited or a positive integer') from None
    if budget<=0:raise ValueError('Set MEMORY_QA_BUDGET_MICRO_USD to unlimited or a positive integer')
    return budget

def ready():
    connections=[]
    try:
        if not READ_ONLY and WORKER_STATUS['state']=='unavailable':return False
        if JOURNAL:
            space=JOURNAL.store.space()
            return space['state'] in ('draft','active') and type(space.get('archive_revision')) is int
        db=open_readonly(DB);connections.append(db)
        db.execute('SELECT id FROM source_versions LIMIT 1').fetchone()
        if ARCHIVE_DB:
            archive=archive_index.connect(ARCHIVE_DB,readonly=True);connections.append(archive)
            archive.execute('SELECT id FROM documents LIMIT 1').fetchone()
        return True
    except (JournalUnavailable,sqlite3.Error,OSError,ValueError): return False
    finally:
        for connection in connections: connection.close()

def retry_transient(db,now):
    # Bounded retries for transport/rate/server failures only; never retry semantic rejection blindly.
    rows=db.execute("SELECT j.id,j.error,j.attempts,MAX(r.created_at) AS last_attempt FROM jobs j LEFT JOIN runs r ON r.job_id=j.id WHERE j.status='failed' AND j.attempts<3 GROUP BY j.id").fetchall()
    for row in rows:
        if not re.search(r'HTTP (429|5\d\d)|TimeoutError|URLError',row['error'] or ''):continue
        if row['last_attempt'] is None or now-row['last_attempt']<30*2**max(0,row['attempts']-1):continue
        db.execute("UPDATE jobs SET status='queued' WHERE id=? AND status='failed'",(row['id'],))

def worker_error(error,attempt):
    """Emit useful code locations without exception text, locals or source data."""
    frames=[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name}
      for frame in traceback.extract_tb(error.__traceback__)[-8:]]
    diagnostic={'component':'canonical_worker','error_type':type(error).__name__,
      'attempt':attempt,'frames':frames}
    if isinstance(error,TransientGateway):
        gateway=getattr(error,'diagnostic',{})
        diagnostic['gateway']={key:gateway.get(key) for key in
          ('op','type','http_status','sqlstate','attempts')}
    elif isinstance(error,HTTPError):
        diagnostic['http_status']=error.code if type(error.code) is int else None
    print(json.dumps(diagnostic,separators=(',',':')),file=sys.stderr,flush=True)
    return diagnostic

def retain_worker_transient(status,recent):
    """Keep a prior transient visible only while the same leased job blocks."""
    if (not recent or not isinstance(status,dict) or status.get('state')!='waiting'
            or status.get('reason')!='earlier_job_leased'
            or not isinstance(status.get('job_id'),str)):
        return status,None
    job_id=status['job_id']
    if recent.get('job_id') not in (None,job_id):return status,None
    recent={**recent,'job_id':job_id}
    return {**status,'previous_transient':recent['diagnostic']},recent

def backup_status(path):
    try:
        if path.stat().st_size>16000:raise ValueError('Oversized backup status')
        value=json.loads(path.read_text())
        if value.get('state') not in ('running','ok','failed'):raise ValueError('Unknown backup state')
        # The UI needs status and times, not private archive paths or runtime details.
        result={k:value.get(k) for k in ('state','started_at','finished_at','last_success_at','last_backup_at')}
        from datetime import datetime,timezone
        last=value.get('last_backup_at') or value.get('last_success_at')
        if last:
            instant=datetime.fromisoformat(last.replace('Z','+00:00'))
            if instant.tzinfo is None:raise ValueError('Backup time needs timezone')
            result['stale']=(datetime.now(timezone.utc)-instant).total_seconds()>36*3600
        return result
    except FileNotFoundError:return {'state':'not_configured'}
    except (OSError,ValueError,AttributeError):return {'state':'unavailable'}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass  # No source text, auth headers or URL parameters in logs.
    def send_json(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def authorized(self):
        self.identity=authenticate(self.headers.get('Authorization',''),service_token=TOKEN,
            supabase_url=SUPABASE_URL,publishable_key=SUPABASE_PUBLISHABLE_KEY,allowed_users=ALLOWED_USERS)
        return self.identity is not None
    def journal_get(self,path,params):
        if path.startswith('/source-edits/jobs/'):
            from source_edit import inspect
            return self.send_json(200,inspect(JOURNAL,self.identity,path.removeprefix('/source-edits/jobs/')))
        if path=='/generation-reviews':
            space=JOURNAL.store.space();JOURNAL.authorize(self.identity,space)
            rows=JOURNAL.store.call('generation_reviews')
            if not isinstance(rows,list):raise JournalUnavailable('Generation list unavailable')
            return self.send_json(200,{'reviews':rows,'revision':space['revision']})
        if path.startswith('/generation-reviews/'):
            from generation_service import inspect
            with JOURNAL.generation_reader():
                return self.send_json(200,inspect(JOURNAL,self.identity,path.removeprefix('/generation-reviews/')))
        if path.startswith('/operations/jobs/'):
            from job_recovery import inspect
            result,_=inspect(JOURNAL,self.identity,path.removeprefix('/operations/jobs/'),params.get('command_id',[''])[0])
            return self.send_json(200,result)
        if path=='/operations':
            space=JOURNAL.store.space();JOURNAL.authorize(self.identity,space)
            return self.send_json(200,{'mode':MODE,'read_only':READ_ONLY,'worker':WORKER_STATUS,
                'model':MODEL,'storage':'supabase','revision':space['revision'],'archive_revision':space['archive_revision'],
                'processing':JOURNAL.store.call('processing_status'),'backup':backup_status(JOURNAL.cache.parent/'backup-status.json'),
                'offserver_backup':backup_status(JOURNAL.cache.parent/'offserver-backup-status.json')})
        if path=='/archive' or path.startswith('/archive/'):
            with JOURNAL.archive_projection(self.identity) as (archive,space):
                if path=='/archive':
                    result=archive_index.catalogue(archive,as_of=params.get('as_of',[None])[0],
                        known_at=params.get('known_at',[None])[0],query=params.get('q',[''])[0],
                        order=params.get('order',['relevance'])[0],
                        limit=int(params.get('limit',['30'])[0]),offset=int(params.get('offset',['0'])[0]))
                    for source in result['sources']:
                        notes=archive_summaries(archive,source['id'])
                        source['summary_available']=bool(notes)
                        if notes:
                            source['summary_title']=notes[0]['title']
                            source['display_title_method']=notes[0]['display_title_method']
                        else:
                            display=meeting_display_title(archive,source['id'])
                            if display:
                                source['summary_title']=display['text']
                                source['display_title_method']=display['method']
                    result.update(storage='supabase',archive_revision=space['archive_revision'])
                else:
                    result=archive_index.original(archive,path.removeprefix('/archive/'))
                    if result:
                        result['summaries']=archive_summaries(archive,result['id'])
                        if result['summaries']:
                            result['summary_title']=result['summaries'][0]['title']
                            result['display_title_method']=result['summaries'][0]['display_title_method']
                        else:
                            display=meeting_display_title(archive,result['id'])
                            if display:
                                result['summary_title']=display['text']
                                result['display_title_method']=display['method']
                return self.send_json(200,result) if result is not None else self.send_json(404,{'error':'Unknown source'})
        with JOURNAL.projection(self.identity) as (db,space):
            if path=='/review':
                result=review(db,params.get('as_of',[None])[0])
                result.update(mode=MODE,revision=space['revision'],can_edit=not READ_ONLY,
                              storage='supabase',space_id=space['id'])
                # Archive totals belong to /archive; opening the working view must
                # never rebuild the full transcript/search archive just to count it.
                result.update(archive_available=True,archive_revision=space['archive_revision'])
                return self.send_json(200,result)
            if path=='/overview':return self.send_json(200,overview(db,params.get('as_of',['9999-12-31'])[0]))
            row=db.execute('SELECT id,title,event_date,content_hash,transcript FROM source_versions WHERE id=?',
                           (path.removeprefix('/sources/'),)).fetchone()
            return self.send_json(200,dict(row)) if row else self.send_json(404,{'error':'Unknown source'})
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/health':
            available=ready()
            return self.send_json(200 if available else 503,{'status':'ok' if available else 'unavailable','mode':MODE})
        try:
            if not self.authorized(): return self.send_json(401,{'error':'Unauthorized'})
        except AuthUnavailable:return self.send_json(503,{'error':'Authentication service unavailable'})
        if JOURNAL and (path=='/conversations' or path.startswith('/conversations/')):
            if not QA_ENABLED or not CONVERSATIONS:return self.send_json(404,{'error':'Not found'})
            if self.identity.get('role')!='owner':return self.send_json(403,{'error':'Conversations require the signed-in owner','code':'access_denied','retryable':False})
            try:
                result=CONVERSATIONS.list(self.identity) if path=='/conversations' else CONVERSATIONS.get(
                    self.identity,path.removeprefix('/conversations/'))
                return self.send_json(200,result)
            except PermissionError:return self.send_json(403,{'error':'Access denied','code':'access_denied','retryable':False})
            except ConversationNotFound:return self.send_json(404,{'error':'Unknown conversation','code':'conversation_not_found','retryable':False})
            except (ValueError,ValidationError):return self.send_json(400,{'error':'Invalid conversation request','code':'invalid_conversation','retryable':False})
            except JournalUnavailable:return self.send_json(503,{'error':'Conversations are temporarily unavailable','code':'conversations_unavailable','retryable':True})
        if JOURNAL and path.startswith('/drive-completion/'):
            if self.identity['role']!='service':return self.send_json(403,{'error':'Drive completion requires service authorization'})
            from drive_completion import completion
            try:return self.send_json(200,completion(JOURNAL.store,path.removeprefix('/drive-completion/')))
            except (ValueError,ValidationError):return self.send_json(400,{'error':'Invalid completion identity'})
            except JournalUnavailable:return self.send_json(503,{'error':'Completion unavailable; do not move the source'})
        if JOURNAL and path=='/drive-manifest':
            if self.identity['role']!='service':return self.send_json(403,{'error':'Drive inventory requires service authorization'})
            try:return self.send_json(200,{'documents':JOURNAL.store.call('drive_manifest')})
            except JournalUnavailable:return self.send_json(503,{'error':'Drive inventory unavailable; do not assume an empty archive'})
        if JOURNAL and path=='/source-deletions':
            if not ORIGINAL_DELETION_ENABLED:return self.send_json(404,{'error':'Not found'})
            if self.identity.get('role')!='owner':return self.send_json(403,{'error':'Original deletion requires the signed-in owner'})
            try:
                from deletion_workflow import status_for_source
                source_id=parse_qs(urlparse(self.path).query).get('source_id',[''])[0]
                return self.send_json(200,{'deletion':status_for_source(JOURNAL,self.identity,source_id)})
            except PermissionError:return self.send_json(403,{'error':'Access denied'})
            except (ValueError,ValidationError):return self.send_json(400,{'error':'Invalid source identity'})
            except JournalUnavailable:return self.send_json(503,{'error':'Deletion status is temporarily unavailable'})
        if JOURNAL and (path in ('/review','/overview','/archive','/operations','/generation-reviews') or path.startswith(('/sources/','/archive/','/operations/jobs/','/generation-reviews/','/source-edits/jobs/'))):
            try:return self.journal_get(path,parse_qs(urlparse(self.path).query))
            except PermissionError:return self.send_json(403,{'error':'Access denied'})
            except RevisionConflict:return self.send_json(409,{'error':'Der Stand hat sich geändert. Bitte erneut laden.'})
            except ValueError:return self.send_json(400,{'error':'Invalid request'})
            except (JournalUnavailable,sqlite3.Error,OSError):return self.send_json(503,{'error':'Working memory temporarily unavailable'})
        if JOURNAL:return self.send_json(404,{'error':'Not found'})
        db=open_readonly(DB) if READ_ONLY else connect(DB)
        try:
            params=parse_qs(urlparse(self.path).query)
            if path=='/operations':
                return self.send_json(200,{'mode':MODE,'read_only':READ_ONLY,'worker':WORKER_STATUS})
            if path=='/review':
                result=review(db,params.get('as_of',[None])[0]);result['mode']=MODE
                if ARCHIVE_DB:
                    archive=archive_index.connect(ARCHIVE_DB,readonly=True)
                    try:
                        result['archive_total']=archive_index.catalogue(archive,as_of=result['as_of'],limit=1)['total']
                        result['archive_available']=True
                    finally: archive.close()
                return self.send_json(200,result)
            if path=='/archive' or path.startswith('/archive/'):
                if not ARCHIVE_DB: return self.send_json(503,{'error':'Archive not configured'})
                archive=archive_index.connect(ARCHIVE_DB,readonly=True)
                try:
                    if path=='/archive':
                        result=archive_index.catalogue(archive,as_of=params.get('as_of',[None])[0],
                            known_at=params.get('known_at',[None])[0],query=params.get('q',[''])[0],
                            order=params.get('order',['relevance'])[0],
                            limit=int(params.get('limit',['30'])[0]),offset=int(params.get('offset',['0'])[0]))
                        for source in result['sources']:
                            display=meeting_display_title(archive,source['id'])
                            source['summary_title']=display['text'] if display else source['title']
                            source['display_title_method']=display['method'] if display else None
                    else: result=archive_index.original(archive,path.removeprefix('/archive/'))
                    if result is not None and path.startswith('/archive/'):
                        display=meeting_display_title(archive,result['id'])
                        result['summary_title']=display['text'] if display else result['title']
                        result['display_title_method']=display['method'] if display else None
                    return self.send_json(200,result) if result is not None else self.send_json(404,{'error':'Unknown source'})
                finally: archive.close()
            if path=='/overview': return self.send_json(200,overview(db,params.get('as_of',['9999-12-31'])[0]))
            if path.startswith('/sources/'):
                sid=path.removeprefix('/sources/')
                row=db.execute('SELECT id,title,event_date,content_hash,transcript FROM source_versions WHERE id=?',(sid,)).fetchone()
                return self.send_json(200,dict(row)) if row else self.send_json(404,{'error':'Unknown source'})
            if path.startswith('/jobs/'):
                row=db.execute('SELECT id,status,attempts,error FROM jobs WHERE id=?',(path.removeprefix('/jobs/'),)).fetchone()
                return self.send_json(200,dict(row)) if row else self.send_json(404,{'error':'Unknown job'})
            return self.send_json(404,{'error':'Not found'})
        except ValueError: self.send_json(400,{'error':'Invalid request parameters'})
        except (sqlite3.Error, OSError): self.send_json(503,{'error':'Data temporarily unavailable'})
        finally: db.close()
    def do_POST(self):
        try:
            if not self.authorized(): return self.send_json(401,{'error':'Unauthorized'})
        except AuthUnavailable:return self.send_json(503,{'error':'Authentication service unavailable'})
        if urlparse(self.path).path=='/conversations':
            if not QA_ENABLED or not CONVERSATIONS:return self.send_json(404,{'error':'Not found'})
            if self.identity.get('role')!='owner':return self.send_json(403,{'error':'Conversations require the signed-in owner','code':'access_denied','retryable':False})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=1000:return self.send_json(413,{'error':'Conversation request outside size bounds','code':'invalid_conversation','retryable':False})
                result=CONVERSATIONS.create(self.identity,json.loads(self.rfile.read(length)))
                return self.send_json(200 if result['repeated'] else 201,result)
            except PermissionError:return self.send_json(403,{'error':'Access denied','code':'access_denied','retryable':False})
            except RevisionConflict:return self.send_json(409,{'error':'Conversation ID conflicts with a prior conversation','code':'conversation_conflict','retryable':False})
            except (ValueError,TypeError,json.JSONDecodeError,ValidationError):return self.send_json(400,{'error':'Invalid conversation request','code':'invalid_conversation','retryable':False})
            except JournalUnavailable:return self.send_json(503,{'error':'Conversations are temporarily unavailable','code':'conversations_unavailable','retryable':True})
        if urlparse(self.path).path=='/questions':
            if not QA_ENABLED:return self.send_json(405,{'error':'Questions are not enabled','code':'questions_disabled','retryable':False})
            if self.identity.get('role')!='owner':return self.send_json(403,{'error':'Questions require the signed-in owner','code':'access_denied','retryable':False})
            if not QUESTION_SERVICE:return self.send_json(503,{'error':'Questions are not configured','code':'questions_unavailable','retryable':True})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=64000:return self.send_json(413,{'error':'Question outside size bounds','code':'invalid_question','retryable':False})
                request=json.loads(self.rfile.read(length))
                # Long-poll below the reverse proxy's 60-second boundary. Cold
                # archive indexing continues in the worker after a 202 response.
                result=QUESTION_JOBS.submit(QUESTION_SERVICE,self.identity,request,wait_seconds=20)
                return self.send_json(202 if result.get('state')=='processing' else 200,result)
            except PermissionError:return self.send_json(403,{'error':'Access denied','code':'access_denied','retryable':False})
            except RevisionConflict:return self.send_json(409,{'error':'Question ID or source context conflicts with a prior request','code':'request_id_conflict','retryable':False})
            except BudgetExceeded:return self.send_json(429,{'error':'Question budget exhausted','code':'question_budget_exceeded','retryable':False})
            except OutcomeUnknown:return self.send_json(503,{'error':'Provider outcome unknown; the same request will not be sent again','code':'provider_outcome_unknown','retryable':False})
            except CompletionUnknown:return self.send_json(503,{'error':'Question receipt is temporarily unavailable','code':'questions_unavailable','retryable':True})
            except QuestionCapacity:return self.send_json(503,{'error':'Question worker capacity is temporarily exhausted','code':'questions_unavailable','retryable':True})
            except AnswerUnverified:return self.send_json(422,{'error':'Answer could not be sufficiently grounded','code':'answer_unverified','retryable':False})
            except (ValueError,TypeError,KeyError,json.JSONDecodeError,ValidationError):return self.send_json(400,{'error':'Invalid or ungrounded question response','code':'invalid_question','retryable':False})
            except (JournalUnavailable,sqlite3.Error,OSError):return self.send_json(503,{'error':'Questions are temporarily unavailable','code':'questions_unavailable','retryable':True})
        if urlparse(self.path).path=='/source-deletions':
            if not ORIGINAL_DELETION_ENABLED:return self.send_json(404,{'error':'Not found'})
            if READ_ONLY:return self.send_json(405,{'error':'Read-only preview'})
            if self.identity.get('role')!='owner':return self.send_json(403,{'error':'Original deletion requires the signed-in owner'})
            if not JOURNAL:return self.send_json(503,{'error':'Durable original deletion is not configured'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=4000:return self.send_json(413,{'error':'Deletion request outside size bounds'})
                request=json.loads(self.rfile.read(length))
                from deletion_workflow import DeletionPending,execute
                result=DELETION_JOBS.submit(execute,JOURNAL,self.identity,request,wait_seconds=20)
                return self.send_json(202 if result.get('state')=='processing' else 200,result)
            except PermissionError:return self.send_json(403,{'error':'Access denied'})
            except RevisionConflict:return self.send_json(409,{'error':'Die Lösch-ID wurde für einen anderen Auftrag verwendet.'})
            except DeletionCapacity:return self.send_json(503,{'error':'Ein anderer Löschvorgang wird gerade abgeschlossen. Bitte diesen Vorgang gleich erneut abfragen.'})
            except DeletionPending:return self.send_json(503,{'error':'Das Original ist aus der aktiven App entfernt. Cache- oder Wiederherstellungsschutz wird noch abgeschlossen; mit derselben Lösch-ID erneut versuchen.'})
            except (ValueError,TypeError,KeyError,json.JSONDecodeError,ValidationError):return self.send_json(400,{'error':'Der Löschauftrag ist unvollständig oder nicht mehr fortsetzbar.'})
            except (JournalUnavailable,sqlite3.Error,OSError):return self.send_json(503,{'error':'Der Löschvorgang ist gespeichert, konnte aber noch nicht abgeschlossen werden. Mit derselben Lösch-ID erneut versuchen.'})
        if READ_ONLY: return self.send_json(405,{'error':'Read-only preview'})
        if urlparse(self.path).path in ('/generation-reviews','/source-edits'):
            if not JOURNAL:return self.send_json(503,{'error':'Durable generation reviews are not configured'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=3_700_000:return self.send_json(413,{'error':'Generation review outside size bounds'})
                request=json.loads(self.rfile.read(length))
                if urlparse(self.path).path=='/source-edits':
                    from source_edit import stage
                else:
                    from generation_service import stage
                with JOURNAL.generation_reader():
                    return self.send_json(200,stage(JOURNAL,self.identity,request))
            except PermissionError:return self.send_json(403,{'error':'Access denied'})
            except RevisionConflict:return self.send_json(409,{'error':'Der Ausgangsstand hat sich geändert. Der Prüfentwurf muss erneut abgeglichen werden.'})
            except (ValueError,TypeError,KeyError):return self.send_json(400,{'error':'Der Prüfentwurf ist unvollständig oder nicht durch archivierte Originale gedeckt.'})
            except (JournalUnavailable,sqlite3.Error,OSError):return self.send_json(503,{'error':'Prüfentwurf kann gerade nicht gespeichert werden. Dieselbe Entwurfs-ID erneut verwenden.'})
        if urlparse(self.path).path in ('/decisions','/operations/decisions','/generation-decisions'):
            if not JOURNAL:return self.send_json(503,{'error':'Durable decisions are not configured'})
            if self.identity['role']!='owner':return self.send_json(403,{'error':'A personal decision requires the signed-in owner'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=64000:return self.send_json(413,{'error':'Decision outside size bounds'})
                request=json.loads(self.rfile.read(length))
                if urlparse(self.path).path=='/operations/decisions':
                    from job_recovery import decide
                    result=decide(JOURNAL,self.identity,request)
                elif urlparse(self.path).path=='/generation-decisions':
                    from generation_service import decide
                    with JOURNAL.generation_reader():
                        return self.send_json(200,decide(JOURNAL,self.identity,request))
                else:result=JOURNAL.decide(self.identity,request)
                return self.send_json(200,result)
            except PermissionError:return self.send_json(403,{'error':'Access denied'})
            except RevisionConflict:return self.send_json(409,{'error':'Der Stand hat sich geändert. Bitte aktualisieren und die Entscheidung erneut prüfen.'})
            except (ValueError,TypeError):return self.send_json(400,{'error':'Die Entscheidung ist unvollständig oder für diesen Eintrag nicht zulässig.'})
            except (JournalUnavailable,sqlite3.Error,OSError):return self.send_json(503,{'error':'Speichern gerade nicht möglich. Erneut versuchen verwendet dieselbe Entscheidungs-ID.'})
        if self.identity['role']!='service': return self.send_json(403,{'error':'Source intake requires service authorization'})
        if JOURNAL and urlparse(self.path).path=='/drive-sources':
            if not INTAKE_ENABLED:return self.send_json(405,{'error':'Source intake is not enabled'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=3_500_000:return self.send_json(413,{'error':'Source outside size bounds'})
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict) or set(data)!={'original'}:raise ValueError('Invalid Drive envelope')
                result=persist_original(JOURNAL.store,data['original'],pipeline=canonical_pipeline(MODEL))
                return self.send_json(200 if result['state'] in ('archive_only','applied') else 202,result)
            except (ValueError,TypeError,KeyError):return self.send_json(400,{'error':'Invalid original or provenance'})
            except RevisionConflict:return self.send_json(409,{'error':'Original identity conflicts with existing source'})
            except JournalUnavailable:return self.send_json(503,{'error':'Source persistence unavailable; retry the identical original'})
        if urlparse(self.path).path!='/sources': return self.send_json(404,{'error':'Not found'})
        if JOURNAL:
            if not INTAKE_ENABLED:return self.send_json(405,{'error':'Source intake is not enabled'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=3_500_000:return self.send_json(413,{'error':'Source outside size bounds'})
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict) or set(data)!={'document'}:raise ValueError('Invalid source envelope')
                document=verify_document(data['document'])
                archive=JOURNAL.store.archive_put(document)
                result=JOURNAL.store.call('enqueue',document_id=document['id'],pipeline=canonical_pipeline(MODEL))
                return self.send_json(200 if result['state'] in ('archive_only','applied') else 202,
                    {'archive':archive,'job_id':result.get('id'),'state':result['state'],'reason':result.get('reason')})
            except (ValueError,TypeError,KeyError):return self.send_json(400,{'error':'Invalid original or provenance'})
            except RevisionConflict:return self.send_json(409,{'error':'Original identity conflicts with existing source'})
            except JournalUnavailable:return self.send_json(503,{'error':'Source persistence unavailable; retry the identical original'})
        if not AUTOMATIC_ENABLED:return self.send_json(405,{'error':'Automatic source intake is not enabled'})
        db=None
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>2_000_000: return self.send_json(413,{'error':'Body size outside bounds'})
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValidationError('Expected JSON object')
            for key in ('source_id','event_date','title','transcript'):
                if not isinstance(data.get(key),str) or not data[key].strip(): raise ValidationError('Missing '+key)
            if len(data['source_id'])>512 or len(data['title'])>1000: raise ValidationError('Metadata too long')
            automatic_start,_=policy(os.environ)
            if data['event_date']<automatic_start:
                return self.send_json(409,{'error':'Historical sources require direct review; automatic processing is disabled for this date'})
            db=connect(DB)
            job=register(db,source_id=data['source_id'],event_date=data['event_date'],title=data['title'],transcript=data['transcript'],pipeline=pipeline_version(MODEL))
            status=db.execute('SELECT status FROM jobs WHERE id=?',(job,)).fetchone()[0]
            self.send_json(200 if status=='applied' else 202,{'job_id':job,'status':status})
        except ReplayRequired as e: self.send_json(409,{'error':str(e)})
        except (ValueError,TypeError) as e: self.send_json(400,{'error':str(e)[:200]})
        finally:
            if db:db.close()

def warm_projections(archive=False):
    # Separate threads/locks keep a large archive rebuild off the review path.
    # Polling also catches changes published by other processes or direct reviews.
    while not STOP.is_set():
        try:JOURNAL.warm_projection(archive=archive)
        except (JournalUnavailable,sqlite3.Error,OSError,ValueError):pass
        STOP.wait(30)

def work():
    global WORKER_STATUS
    if JOURNAL:
        worker=None;failures=0;recent_transient=None
        while not STOP.is_set():
            try:
                if worker is None:worker=CanonicalWorker(JOURNAL,MODEL)
                result=worker.step()
                WORKER_STATUS,recent_transient=retain_worker_transient(result,recent_transient)
                failures=0;delay=5
            except (TransientGateway,OSError) as error:
                failures+=1;delay=min(60,5*2**min(failures-1,4))
                diagnostic=worker_error(error,failures)
                recent_transient={'diagnostic':diagnostic,'job_id':None}
                WORKER_STATUS={'state':'unavailable','reason':'worker_transient','retryable':True,'transient':True,
                  'retry_in_seconds':delay,'error_type':type(error).__name__,'diagnostic':diagnostic}
            except JournalUnavailable as error:
                failures+=1;delay=min(60,5*2**min(failures-1,4))
                WORKER_STATUS={'state':'unavailable','reason':'storage_unavailable','retryable':True,'transient':False,
                  'retry_in_seconds':delay,'error_type':type(error).__name__}
            except Exception as error:
                failures+=1;delay=min(60,5*2**min(failures-1,4));diagnostic=worker_error(error,failures)
                WORKER_STATUS={'state':'unavailable','reason':'unexpected_worker_error','retryable':True,'transient':False,
                  'retry_in_seconds':delay,'error_type':diagnostic['error_type']}
            STOP.wait(delay)
        return
    db=connect(DB)
    worker=None
    try:
        worker=Worker(db,os.environ.get('MEMORY_BUDGET_DB',DB),MODEL,os.environ)
        while not STOP.is_set():
            retry_transient(db,time.time())
            WORKER_STATUS=worker.step()
            STOP.wait(1)
    except Exception as error:
        WORKER_STATUS={'state':'unavailable','reason':type(error).__name__}
    finally:
        if worker:worker.close()
        db.close()

if __name__=='__main__':
    if len(TOKEN)<32: raise SystemExit('Set MEMORY_API_TOKEN (at least 32 characters)')
    if os.environ.get('MEMORY_SPACE_ID'):
        if os.environ.get('MEMORY_JOURNAL_TOKEN'):
            store=GatewayJournal(SUPABASE_URL,SUPABASE_PUBLISHABLE_KEY,os.environ['MEMORY_JOURNAL_TOKEN'],os.environ['MEMORY_SPACE_ID'])
        else:
            store=SupabaseJournal(SUPABASE_URL,os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''),os.environ['MEMORY_SPACE_ID'])
        JOURNAL=JournalService(store,
                               os.environ.get('MEMORY_CACHE_DIR','.local/projections'))
        JOURNAL.register_privacy_cleanup(QUESTION_JOBS.clear_completed)
    if QA_ENABLED:
        if not JOURNAL or not isinstance(JOURNAL.store,GatewayJournal):raise SystemExit('Questions require the scoped canonical journal gateway')
        try:qa_budget=question_budget(os.environ.get('MEMORY_QA_BUDGET_MICRO_USD',''))
        except ValueError as error:raise SystemExit(str(error)) from None
        from openai_provider import MODEL as qa_model,request as provider_request
        from qa_service import QuestionService
        from memory_chat import ConversationService
        CONVERSATIONS=ConversationService(JOURNAL)
        QUESTION_SERVICE=QuestionService(JOURNAL,provider_request,model=qa_model,budget_micro_usd=qa_budget,
            conversations=CONVERSATIONS,
            outbox=os.environ.get('MEMORY_QA_OUTBOX','.local/question-outbox'))
    if ORIGINAL_DELETION_ENABLED:
        if not JOURNAL or READ_ONLY:raise SystemExit('Original deletion requires the writable canonical journal')
        cache_registry=os.environ.get('MEMORY_PROJECTION_CACHE_DIRS','')
        if not cache_registry:raise SystemExit('Original deletion requires an explicit projection cache registry')
        from deletion_workflow import registered_cache_directories,registered_private_outboxes
        cache_directories=registered_cache_directories(JOURNAL,cache_registry)
        JOURNAL.register_private_outbox('question',os.environ.get('MEMORY_QA_OUTBOX','.local/question-outbox'))
        registered_private_outboxes(JOURNAL,cache_registry)
        restore_ledger=Path(os.environ.get('MEMORY_RESTORE_DELETION_LEDGER',''))
        if not restore_ledger.is_absolute() or any(directory==restore_ledger.resolve() or directory in restore_ledger.resolve().parents for directory in cache_directories):
            raise SystemExit('Original deletion requires an external restore ledger outside projection caches')
    if MODE=='production' and not JOURNAL:raise SystemExit('Production requires the canonical Supabase journal')
    if JOURNAL and AUTOMATIC_ENABLED:
        if not os.environ.get('MEMORY_JOURNAL_TOKEN'):raise SystemExit('Canonical worker requires scoped gateway access')
        CanonicalWorker(JOURNAL,MODEL)  # Validate rules before starting intake.
    if not JOURNAL and READ_ONLY: open_readonly(DB).close()
    elif not JOURNAL:
        if AUTOMATIC_ENABLED:policy(os.environ)  # Reject unsafe configuration before opening intake.
        Path(DB).parent.mkdir(parents=True,exist_ok=True);connect(DB).close()
    warmers=[]
    if JOURNAL:
        for archive in (False,True):
            warmer=threading.Thread(target=warm_projections,args=(archive,),daemon=True)
            warmer.start();warmers.append(warmer)
    worker=None
    if not READ_ONLY and AUTOMATIC_ENABLED:
        worker=threading.Thread(target=work,daemon=True);worker.start()
    else:WORKER_STATUS={'state':'disabled'}
    http=ThreadingHTTPServer((os.environ.get('MEMORY_BIND','127.0.0.1'),int(os.environ.get('PORT','8791'))),Handler)
    try:http.serve_forever()
    finally:
        STOP.set();http.server_close()
        if worker:worker.join(timeout=5)
