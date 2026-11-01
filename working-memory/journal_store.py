"""Supabase is authoritative; projection files are disposable local caches.

The server key belongs only in the private process environment. No browser or
model receives it. Failed HTTP calls never include provider bodies in errors.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID


class JournalUnavailable(RuntimeError): pass
class RevisionConflict(RuntimeError): pass


def uuid(value):
    return str(UUID(value))


class SupabaseJournal:
    def __init__(self, url, service_key, space_id):
        if not re.fullmatch(r'https://[a-z0-9]+\.supabase\.co', url):
            raise ValueError('Expected the configured HTTPS Supabase project URL')
        if not service_key:
            raise ValueError('Missing server-only Supabase credential')
        self.url, self.key, self.space_id = url, service_key, uuid(space_id)

    def request(self, path, *, data=None):
        body = None if data is None else json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        request = Request(self.url+'/rest/v1/'+path, data=body,
                          headers={'apikey':self.key,'Authorization':'Bearer '+self.key,
                                   'Content-Type':'application/json','Accept':'application/json'})
        try:
            with urlopen(request,timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            # SQLSTATE 40001 maps to HTTP 500 in PostgREST, so inspect the code
            # privately without retaining or exposing the potentially sensitive body.
            try: code=json.loads(error.read(10000)).get('code')
            except (ValueError,AttributeError):code=None
            finally:error.close()
            if code in ('40001','23505'):
                raise RevisionConflict('Refresh and reconcile the changed journal') from None
            raise JournalUnavailable('Supabase journal request failed (HTTP '+str(error.code)+')') from None
        except (URLError,TimeoutError,OSError,ValueError):
            raise JournalUnavailable('Supabase journal temporarily unavailable') from None

    def space(self):
        rows=self.request('wm_spaces?'+urlencode({'id':'eq.'+self.space_id,'select':'id,owner_id,state,revision,archive_revision,label'}))
        if not isinstance(rows,list) or len(rows)!=1:
            raise JournalUnavailable('Configured memory space is unavailable')
        return rows[0]

    def append(self, *, expected_revision, command_id, kind, payload, source=None, actor_id=None):
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError('Expected revision must be a nonnegative integer')
        # The caller must retain this command ID across uncertain network results.
        # A fresh ID after a timeout could apply a human action twice.
        return self.request('rpc/wm_append',data={
            'p_space_id':self.space_id,'p_expected_revision':expected_revision,
            'p_command_id':uuid(command_id),'p_kind':kind,'p_payload':payload,
            'p_source':source,'p_actor_id':uuid(actor_id) if actor_id else None})

    def entries(self, *, after=0, through=None):
        if through is None:through=self.space()['revision']
        if type(after) is not int or type(through) is not int or not 0<=after<=through:
            raise ValueError('Invalid journal bounds')
        result=[];cursor=after
        while cursor<through:
            rows=self.request('wm_journal?'+urlencode({
                'space_id':'eq.'+self.space_id,'and':f'(revision.gt.{cursor},revision.lte.{through})',
                'order':'revision.asc','limit':100,'select':'revision,command_id,request_hash,kind,source_version,actor_id,payload,recorded_at,source:wm_source_versions(*)'}))
            if not isinstance(rows,list) or not rows:
                raise JournalUnavailable('Journal has a missing revision')
            for row in rows:
                if row['revision']!=cursor+1 or row['revision']>through:
                    raise JournalUnavailable('Journal revision sequence is inconsistent')
                cursor=row['revision'];result.append(row)
        return result

    def source(self, version_id):
        if not re.fullmatch('[0-9a-f]{64}',version_id):
            raise ValueError('Invalid source version')
        rows=self.request('wm_source_versions?'+urlencode({
            'space_id':'eq.'+self.space_id,'id':'eq.'+version_id,'select':'*'}))
        if not isinstance(rows,list) or len(rows)!=1:
            raise JournalUnavailable('Pinned source version is unavailable')
        return rows[0]

    def command(self, command_id):
        rows=self.request('wm_journal?'+urlencode({'space_id':'eq.'+self.space_id,
            'command_id':'eq.'+uuid(command_id),'select':'revision,kind,actor_id,payload'}))
        if not isinstance(rows,list) or len(rows)>1:
            raise JournalUnavailable('Invalid command receipt')
        return rows[0] if rows else None

    def archive_put(self,document):
        return self.request('rpc/wm_archive_put',data={'p_space_id':self.space_id,'p_document':document})

    def archive_note_put(self,note):
        return self.request('rpc/wm_archive_note_put',data={'p_space_id':self.space_id,'p_note':note})

    def archive_rows(self,kind,*,through,after=0):
        if kind not in ('documents','notes') or type(through) is not int or type(after) is not int or not 0<=after<=through:
            raise ValueError('Invalid archive bounds')
        cursor=after
        while cursor<through:
            rows=self.request('wm_archive_'+kind+'?'+urlencode({'space_id':'eq.'+self.space_id,
                'and':f'(registered_revision.gt.{cursor},registered_revision.lte.{through})',
                'order':'registered_revision.asc','limit':10 if kind=='documents' else 50,'select':'*'}))
            if not isinstance(rows,list):raise JournalUnavailable('Invalid archive page')
            if not rows:return
            for row in rows:
                revision=row.get('registered_revision')
                if type(revision) is not int or not cursor<revision<=through or row.get('space_id')!=self.space_id:
                    raise JournalUnavailable('Archive snapshot inconsistent')
                cursor=revision;yield row
