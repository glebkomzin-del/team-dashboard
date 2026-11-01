"""Actual worker/gateway/SQL/projection control flow with fixture model outputs.

The only HTTP listener is local Deno, which runs the real Edge handler against
an isolated PostgreSQL Unix socket. No production env or provider transport.
"""
import contextlib,json,os,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch

CANDIDATE=Path('/private/tmp/dashboard-sol-operational-20261006/candidate')
sys.path.insert(0,str(CANDIDATE))
import processor
from archive_index import connect as archive_connect
from canonical_worker import CanonicalWorker,pipeline_version
from durable_calls import encode,sha
from gateway_journal import GatewayJournal
from journal_projection import rebuild
from memory import ValidationError,apply,claim,connect,register

SOCKET='/private/tmp/dashboard-sol-operational-20261006/pg-test/socket'
DB=os.environ.get('TEST_DB','isolated17');SPACE='10000000-0000-0000-0000-000000000001';OWNER='00000000-0000-0000-0000-000000000001'
def q(v):return "'"+str(v).replace("'","''")+"'"
def sql(statement):
    run=subprocess.run(['psql','-h',SOCKET,'-p','55442','-d',DB,'-XAt','-v','ON_ERROR_STOP=1','-c',statement],
        text=True,capture_output=True,check=True)
    return run.stdout.strip()

processor.PROMPT_VERSION='v11'
pipeline=pipeline_version('gpt-6.1-sol')
sql(f"insert into auth.users(id) values({q(OWNER)})")
sql(f"insert into public.wm_spaces(id,owner_id,label,state,archive_revision) values({q(SPACE)},{q(OWNER)},'worker flow','active',3)")
sql(f"insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd) values({q(SPACE)},true,'2026-01-01',{q(pipeline)},100000000)")
ids=[]
for index,label in enumerate('ABC',1):
    source=f'synthetic:gateway-{label}'
    body=f'00:00 Alice: Bericht {label} enthält zwei Filialen.'
    digest=sha(body);day=f'2026-10-0{index}'
    meta=encode({'source_id':source,'event_date':day,'title':f'Synthetisches Meeting {label}',
        'body_sha256':digest,'export_sha256':digest,'body_offset_characters':0})
    doc=sha(source+':'+meta);job=sha(source+':'+digest);ids.append(job)
    sql(f"insert into public.wm_archive_documents(space_id,id,source_id,event_date,observed_at,title,body_hash,export_hash,body,export,metadata_json,registered_revision) values({q(SPACE)},{q(doc)},{q(source)},{q(day)},{q(day+'T00:00:00Z')},{q('Synthetisches Meeting '+label)},{q(digest)},{q(digest)},{q(body)},{q(body)},{q(meta)},{index})")
    sql(f"insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state) values({q(SPACE)},{q(job)},{q(doc)},{q(source)},{q(day)},{q(pipeline)},'queued')")

store=GatewayJournal('http://api-gw:8000','disposable-public-key','c'*64,SPACE)
store.url='http://127.0.0.1:18098'
sent=[]
with tempfile.TemporaryDirectory(prefix='gateway-worker-',dir='/private/tmp/dashboard-sol-operational-20261006') as tmp:
    class Service:
        cache=Path(tmp)
        store=store
        def privacy_reader(self):return contextlib.nullcontext()
        @contextlib.contextmanager
        def archive_projection(self,identity):
            archive=archive_connect(Path(tmp)/'archive.sqlite')
            try:yield archive,0
            finally:archive.close()
    def api(prompt,model,*,max_tokens,schema):
        sent.append(model)
        label='ABC'[len(sent)-1]
        text=f'Bericht {label} enthält zwei Filialen.'
        proposal={'coverage_notes':[],
            'meeting_summary':[{'text':text,'evidence_ids':['U0001']}],
            'meeting_display_title':{'text':f'Bericht {label} mit zwei Filialen','evidence_ids':['U0001']},
            'observations':[{'matter':f'Bericht {label}','matter_id':None,'kind':'fact','title':'Berichtsumfang',
                'claim':text,'owner':None,'commitment_strength':'not_applicable','due_text':None,
                'update_target':None,'update':'none','uncertainty':None,'required_review':False,
                'evidence_ids':['U0001'],'action_uncertainty':None,'condition_text':None,
                'work_state':'not_applicable','state_evidence_ids':[]}]}
        return {'content':[{'type':'text','text':json.dumps(proposal)}],
            'stop_reason':'end_turn','terminal_status':'completed','requested_service_tier':'default',
            'returned_service_tier':'default','usage_final':True,
            'usage':{'input_tokens':100,'output_tokens':100},'elapsed_seconds':0.01}
    def fixture_process(db,meeting,model,*,api,pipeline,**kwargs):
        api('Offline fixture based on current original '+meeting['source_id'],model,max_tokens=100)
        if meeting['source_id'].endswith('-B'):
            raise ValidationError('Synthetic source-specific validation failure after one saved response')
        label=meeting['source_id'][-1]
        text=f'Bericht {label} enthält zwei Filialen.'
        proposal={'coverage_notes':[],
            'observations':[{'matter':f'Bericht {label}','matter_id':None,'kind':'fact','title':'Berichtsumfang',
                'claim':text,'owner':None,'commitment_strength':'not_applicable','due_text':None,
                'update_target':None,'update':'none','uncertainty':None,'required_review':False,
                'evidence_ids':['U0001'],'action_uncertainty':None,'condition_text':None,
                'quotes':[meeting['raw_transcript']],
                'work_state':'not_applicable','state_evidence_ids':[]}]}
        jid=register(db,source_id=meeting['source_id'],event_date=meeting['meeting_date'],
            title=meeting['title'],transcript=meeting['raw_transcript'],pipeline=pipeline)
        token=claim(db,jid)
        apply(db,jid,token,proposal,model=model,usage={'fixture':True})
        return {'status':'applied','job':jid}
    worker=CanonicalWorker(Service(),'gpt-6.1-sol',api=api)
    assert worker.pipeline==pipeline
    with patch.object(processor,'process',side_effect=fixture_process):
        a=worker.step();b=worker.step();c=worker.step()
    assert a['state']=='applied' and a['revision']==1,a
    assert b['state']=='review' and b['technical_isolation'] is True,b
    assert c['state']=='applied' and c['revision']==2,c
    assert sent==['gpt-6.1-sol']*3 and sql(f"select public.wm_job_isolation_valid({q(SPACE)},{q(ids[1])})")=='t'
    assert sql(f"select count(*) from public.wm_model_calls where space_id={q(SPACE)}")=='3'
    restored=Path(tmp)/'final.sqlite';rebuild(store,restored)
    db=connect(restored)
    try:
        count=db.execute('select count(*) from observations').fetchone()[0]
        work=db.execute('select count(*) from work_events').fetchone()[0]
    finally:db.close()
    assert count==2 and work==0,(count,work)
    assert sql(f"select count(*) from public.wm_source_versions where space_id={q(SPACE)}")=='2'
    assert worker.step()['state']=='idle' and len(sent)==3
    print(json.dumps({'actual_worker_gateway_sql_projection':True,'A':'applied','B':'review_isolated',
        'C':'applied','stored_model_responses':3,'projection_observations':count,'work_events':work,
        'extra_provider_calls':0},sort_keys=True))
