"""Provider-free cached replay; stops before the first compact model call."""
import hashlib
import json
import os
from pathlib import Path
import sys


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


class CacheMiss(RuntimeError):pass
class Captured(BaseException):pass


class ReadStore:
    def __init__(self,data):
        self.data=data;self.ids=set(data['indexed_ids']);self.queries=0

    def call(self,op,**fields):
        if op=='search_missing':return [i for i in fields['document_ids'] if i not in self.ids]
        if op=='search_snapshot':
            s=self.data['snapshot']
            if fields['search_snapshot_id']!=s['id'] or fields['document_ids']!=s['document_ids']:
                raise CacheMiss('Existing search snapshot does not match')
            return {'count':len(s['document_ids'])}
        if op=='search_query':
            if fields['search_snapshot_id']!=self.data['snapshot']['id']:raise CacheMiss('Search snapshot changed')
            key=sha(encode([fields['query_text'],fields['query_embedding'],fields['kinds'],fields['match_count']]))
            if key not in self.data['search_results']:raise CacheMiss('Existing search result missing')
            self.queries+=1
            return self.data['search_results'][key]
        # In particular search_put/search_snapshot creation/reservations/receives cannot run.
        raise CacheMiss('Read-only store rejects operation '+op)


class ReplayAPI:
    def __init__(self,data):
        self.data=data;self.store=ReadStore(data);self.responses={};self.used=set();self.override_used=False
        self.primary_responses=[]
        for c in data['calls']:
            if c['response_json'] is None:raise CacheMiss('Unreceived model response')
            if sha(c['request_json'])!=c['request_hash'] or sha(c['response_json'])!=c['response_hash']:raise CacheMiss('Saved model hash mismatch')
            request=json.loads(c['request_json']);response=json.loads(c['response_json'])
            if response.get('stop_reason')!='end_turn':raise CacheMiss('Saved response not complete')
            if c['request_hash'] in self.responses:raise CacheMiss('Duplicate saved request')
            self.responses[c['request_hash']]=(c['call_index'],request,response)
        first=next(c for c in data['calls'] if c['call_index']==2)
        request=json.loads(first['request_json']);self.schema=request['schema']
        if request['max_tokens']!=48000:raise CacheMiss('Expected reviewed 48k response')

    def __call__(self,prompt,model,max_tokens=24000,schema=None):
        value={'model':model,'prompt':prompt,'max_tokens':max_tokens,'schema':self.schema if schema is None else schema,
               'scope':{'mode':'bounded_recovery_generation','job_id':self.data['job']['id'],
                        'pipeline':self.data['pipeline'],'revision':355}}
        if model=='gpt-6.1-sol' and not self.override_used:
            if sha(encode(value))!='825d696d562fc164874de3d44bcd70541c3ab17ac165308f4ef567e5a48a9b59':raise CacheMiss('Original extraction request changed')
            value['max_tokens']=48000;self.override_used=True
        key=sha(encode(value))
        if key not in self.responses:raise CacheMiss('No exact saved model response; no provider exists')
        index,request,response=self.responses[key]
        if request!=value:raise CacheMiss('Saved request content changed')
        self.used.add(index)
        if schema is None:self.primary_responses.append(response)
        return response


def run(data):
    private=Path(data['private']).resolve();private.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Imports are denied explicitly, in addition to the OS audit barrier below.
    class NoProvider:
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0] in ('openai_provider','openai','anthropic'):raise ImportError('Provider import forbidden in capture')
    sys.meta_path.insert(0,NoProvider())
    for key in list(os.environ):
        if key.startswith(('OPENAI_','ANTHROPIC_','SUPABASE_')) or key=='MEMORY_JOURNAL_TOKEN':os.environ.pop(key)
    def audit(event,args):
        if event.startswith('socket.') or event in ('subprocess.Popen','os.system'):raise RuntimeError('Capture forbids network and subprocesses')
        if event=='open':
            path,mode,flags=args
            if isinstance(path,(str,bytes)) and (flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
                if not Path(path).resolve().is_relative_to(private):raise RuntimeError('Capture write outside owned private directory')
    sys.addaudithook(audit)
    sys.path.insert(0,'/app');sys.dont_write_bytecode=True
    import hybrid_pipeline as hp
    import processor
    import future_summary
    from generation_review import _logical_entries,materialize
    from memory import connect
    import sqlite3
    assert processor.PROMPT_VERSION=='v11' and data['space']['revision']==355
    assert data['job']['id']=='9266439fe8c4bb320db97d2a4bb1c4f16b5badb43f9bebf51c2f2191df6a61f7'
    doc=data['document'];assert sha(doc['body'])==doc['body_hash']
    # Only run-output paths change; the prompt rules retain their actual runtime bytes.
    evaluation=private/'evaluation';evaluation.mkdir(exist_ok=True)
    (evaluation/'prompt-v9.txt').write_bytes(Path('/app/evaluation/prompt-v9.txt').read_bytes())
    hp.ROOT=private
    binding=sha(encode([data['entries'],doc['event_date']]))
    dbpath=private/'historical.sqlite';receipt=private/'historical-receipt.json'
    if dbpath.exists() and receipt.exists():
        saved=json.loads(receipt.read_text())
        assert saved['binding']==binding and saved['sha256']==hashlib.sha256(dbpath.read_bytes()).hexdigest()
        db=connect(':memory:');source=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True);source.backup(db);source.close()
    else:
        base,_=_logical_entries(data['entries'])
        at=next((i for i,e in enumerate(base) if e['kind']=='source' and e['source']['event_date']>doc['event_date']),len(base))
        db,_=materialize(base[:at]);saved=sqlite3.connect(dbpath);db.backup(saved);saved.close()
        receipt.write_text(encode({'binding':binding,'sha256':hashlib.sha256(dbpath.read_bytes()).hexdigest()}))
    api=ReplayAPI(data)
    archive=private.parent/'archive.sqlite';assert archive.is_file()
    meeting={'id':data['job']['id'],'source_id':doc['source_id'],'title':doc['title'],'meeting_date':doc['event_date'],
             'observed_at':doc['observed_at'],'raw_transcript':doc['body']}
    counts={};original_guard=hp.context_exceeds_budget
    def profile(frame,event,arg):
        if event=='call' and frame.f_code.co_name=='run' and Path(frame.f_code.co_filename).name=='compact_reconcile.py':
            v=frame.f_locals
            counts.update(observations=len(v['raw']['observations']),work=len(v['work']),hits=len(v['hits']),query_hits=len(v['query_hits']))
    def capture(name,prompt,schema,max_tokens,model,compact=False):
        if name!='compact-0':return original_guard(name,prompt,schema,max_tokens,model,compact)
        serialized=json.dumps(schema,ensure_ascii=False)
        total=len(prompt.encode())+len(serialized.encode())+4096+max_tokens
        result={'phase':'captured','name':name,'job':data['job']['id'],'revision':355,'prompt_sha256':sha(prompt),
                'schema_sha256':sha(serialized),'prompt_chars':len(prompt),'prompt_utf8_bytes':len(prompt.encode()),
                'schema_utf8_bytes':len(serialized.encode()),'max_output_tokens':max_tokens,'framing_tokens':4096,
                'conservative_total_tokens':total,'limit':1050000,'guard_rejected':original_guard(name,prompt,schema,max_tokens,model,compact),
                'search_snapshot_id':data['snapshot']['id'],'cached_model_responses':len(api.used),'search_queries':api.store.queries,**counts}
        (private/'compact-prompt.json').write_text(encode({'prompt':prompt,'schema':schema,'max_tokens':max_tokens,'model':model}))
        (private/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        assert result['guard_rejected'] and total>1050000 and api.override_used
        print(json.dumps(result),flush=True)
        raise Captured()
    hp.context_exceeds_budget=capture;sys.setprofile(profile)
    try:
        processor.process(db,meeting,'gpt-6.1-sol',api=api,pipeline=data['pipeline'],archive_db=str(archive),
                          extra_instruction=future_summary.INSTRUCTION,extraction_recovery=True)
        raise RuntimeError('Capture stage was not reached')
    except Captured:pass
    finally:sys.setprofile(None);db.close()


if __name__=='__main__':
    try:run(json.loads(Path(sys.argv[1]).read_text()))
    except Exception as error:
        print(json.dumps({'phase':'stopped_safely','error_type':type(error).__name__,'error':str(error) if isinstance(error,CacheMiss) else 'Offline capture failed; no provider exists'}),flush=True)
        raise
