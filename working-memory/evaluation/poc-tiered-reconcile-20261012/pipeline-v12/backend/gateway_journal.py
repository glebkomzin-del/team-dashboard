"""Narrow Supabase Edge gateway client; no database-wide key on this server."""
from datetime import datetime,timezone
import gzip,json,re,time
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from journal_store import JournalUnavailable,RevisionConflict,uuid

class GatewayFailure(JournalUnavailable):
    """Redacted, structured gateway failure safe to expose in worker status."""
    def __init__(self,op,error_type,*,http_status=None,sqlstate=None):
        self.diagnostic={'at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            'op':op,'type':error_type,'http_status':http_status,'sqlstate':sqlstate}
        super().__init__('Journal gateway temporarily unavailable')

class TransientGateway(GatewayFailure): pass

# These operations are content-addressed and idempotent. Model reservations,
# publication, journal appends and user decisions deliberately stay single-shot.
RETRYABLE_SEARCH = {'search_missing','search_cached','search_put','search_snapshot','search_query'}
RETRYABLE_PINNED_READS = {'backup_page','entries','archive_documents','archive_notes'}
RETRYABLE_PIPELINE_READS = {'space','archive_document','processing_status','job_detail'}

class GatewayJournal:
    def __init__(self,url,publishable_key,token,space_id):
        if (not re.fullmatch(r'https://[a-z0-9]+\.supabase\.co',url) and url not in ('https://178-105-167-26.nip.io/supabase','http://api-gw:8000')) or not re.fullmatch('[0-9a-f]{64}',token):
            raise ValueError('Invalid gateway configuration')
        if not publishable_key:raise ValueError('Missing public project key')
        self.url=url+'/functions/v1/working-memory-journal'
        self.key,self.token,self.space_id=publishable_key,token,uuid(space_id)
    def call(self,op,**fields):
        attempts=3 if op in RETRYABLE_SEARCH | RETRYABLE_PINNED_READS | RETRYABLE_PIPELINE_READS else 1
        for attempt in range(attempts):
            try:return self._call_once(op,**fields)
            except TransientGateway as error:
                error.diagnostic['attempts']=attempt+1
                if attempt+1==attempts:raise
                time.sleep(.5*(attempt+1))

    def _call_once(self,op,**fields):
        req=Request(self.url,data=json.dumps({'op':op,'space_id':self.space_id,**fields},ensure_ascii=False,allow_nan=False).encode(),
            headers={'apikey':self.key,'Authorization':'Bearer '+self.key,'X-Memory-Token':self.token,'Content-Type':'application/json','Accept-Encoding':'gzip'})
        try:
            with urlopen(req,timeout=35) as response:
                if getattr(response,'headers',{}).get('Content-Encoding','').lower()=='gzip':
                    with gzip.GzipFile(fileobj=response) as decoded:return json.load(decoded)
                return json.load(response)
        except HTTPError as error:
            status=error.code;sqlstate=None
            try:
                if error.headers.get('Content-Encoding','').lower()=='gzip':
                    with gzip.GzipFile(fileobj=error) as decoded:code=json.load(decoded).get('code','')
                else:code=json.load(error).get('code','')
                if re.fullmatch('[A-Z0-9]{5}',code):sqlstate=code
            except (ValueError,AttributeError,TypeError,OSError,EOFError):pass
            finally:error.close()
            if status==409:raise RevisionConflict('Refresh and reconcile the changed journal') from None
            if status==400:raise ValueError('Invalid journal request') from None
            error_class=TransientGateway if status in (429,500,502,503,504) else GatewayFailure
            raise error_class(op,'http',http_status=status,sqlstate=sqlstate) from None
        except (URLError,TimeoutError,OSError):raise TransientGateway(op,'network') from None
        except ValueError:raise TransientGateway(op,'response_decode') from None
    def space(self):return self.call('space')
    def source(self,version_id):
        if not re.fullmatch('[0-9a-f]{64}',version_id):raise ValueError('Invalid source version')
        return self.call('source',version_id=version_id)
    def command(self,command_id):return self.call('command',command_id=uuid(command_id))
    def append(self,*,expected_revision,command_id,kind,payload,source=None,actor_id=None):
        return self.call('append',expected_revision=expected_revision,command_id=uuid(command_id),kind=kind,
                         payload=payload,source=source,actor_id=uuid(actor_id) if actor_id else None)
    def entries(self,*,after=0,through=None):
        if through is None:through=self.space()['revision']
        if type(after) is not int or type(through) is not int or not 0<=after<=through:raise ValueError('Invalid journal bounds')
        rows=[];cursor=after
        while cursor<through:
            batch=self.call('entries',after=cursor,through=through)
            if not isinstance(batch,list) or not batch:raise JournalUnavailable('Journal revision missing')
            for row in batch:
                if row['revision']!=cursor+1 or row['revision']>through:raise JournalUnavailable('Journal revisions inconsistent')
                cursor=row['revision'];rows.append(row)
        return rows

    def archive_put(self,document):
        return self.call('archive_put',document=document)
    def archive_note_put(self,note):
        return self.call('archive_note_put',note=note)
    def archive_rows(self,kind,*,through,after=0):
        if kind not in ('documents','notes') or type(through) is not int or type(after) is not int or not 0<=after<=through:
            raise ValueError('Invalid archive bounds')
        cursor=after
        while cursor<through:
            rows=self.call('archive_'+kind,after=cursor,through=through)
            if not isinstance(rows,list):raise JournalUnavailable('Invalid archive page')
            if not rows:return
            for row in rows:
                revision=row.get('registered_revision')
                if type(revision) is not int or not cursor<revision<=through or row.get('space_id')!=self.space_id:
                    raise JournalUnavailable('Archive snapshot inconsistent')
                cursor=revision
                yield row
