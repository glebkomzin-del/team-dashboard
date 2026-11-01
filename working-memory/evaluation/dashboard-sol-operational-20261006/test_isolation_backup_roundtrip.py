"""Disposable PostgreSQL canonical backup/restore of a real technical audit."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
from uuid import uuid4

CANDIDATE=Path('/private/tmp/dashboard-sol-operational-20261006/candidate')
sys.path.insert(0,str(CANDIDATE))
from canonical_backup import export,verify
from canonical_restore import generate
from deletion_ledger import write as write_ledger
from durable_calls import encode,sha

SOCKET='/private/tmp/dashboard-sol-operational-20261006/pg-test/socket'
SPACE='10000000-0000-0000-0000-000000000001'
OWNER='00000000-0000-0000-0000-000000000001'
DB=os.environ.get('TEST_SOURCE_DB','isolated6')
TARGET=os.environ.get('TEST_TARGET_DB','isolated8')
def quoted(v):return "'"+str(v).replace("'","''")+"'"
def query(sql,db=DB):
    run=subprocess.run(['psql','-h',SOCKET,'-p','55442','-d',db,'-XAt','-v','ON_ERROR_STOP=1','-c',sql],
        text=True,capture_output=True,check=True)
    output=run.stdout.strip()
    if output in ('t','f'):return output=='t'
    if not output or output.startswith(('INSERT ','UPDATE ','DELETE ')):return None
    try:return json.loads(output)
    except json.JSONDecodeError:return output

class Store:
    space_id=SPACE
    def call(self,op,**fields):
        names={'backup_begin':'wm_backup_begin','backup_page':'wm_backup_page','backup_release':'wm_backup_release'}
        args={'p_space_id':SPACE,**{'p_'+k:v for k,v in fields.items()}}
        values=','.join(f'{k}=>{quoted(v)}' for k,v in args.items())
        return query(f'select to_jsonb(public.{names[op]}({values}))')
    def space(self):return query(f'select to_jsonb(s) from public.wm_spaces s where id={quoted(SPACE)}')
    def entries(self,*,through):return [] if through==0 else query(f'select coalesce(jsonb_agg(to_jsonb(j)) ,\'[]\'::jsonb) from public.wm_journal j where space_id={quoted(SPACE)} and revision<={through}')
    def archive_rows(self,kind,*,through):
        table={'documents':'wm_archive_documents','notes':'wm_archive_notes'}[kind]
        return query(f"select coalesce(jsonb_agg(to_jsonb(x) order by registered_revision),'[]'::jsonb) from public.{table} x where space_id={quoted(SPACE)} and registered_revision<={through}")

body='00:00 Bob: Der Bericht enthält zwei Filialen.'
source='synthetic:technical-isolation'
bodyhash=sha(body)
meta=encode({'source_id':source,'event_date':'2026-10-06','title':'Synthetisches Meeting',
    'body_sha256':bodyhash,'export_sha256':bodyhash,'body_offset_characters':0})
doc=sha(source+':'+meta);job=sha(source+':'+bodyhash)
request=encode({'model':'gpt-6.1-sol','prompt':'fixture','max_tokens':100,'schema':{},
                'transport':{'reasoning_effort':'medium','service_tier':'default'}})
response=encode({'content':[{'type':'text','text':'{}'}],'stop_reason':'end_turn',
                 'usage_final':True,'usage':{'input_tokens':1,'output_tokens':1}})
query(f"insert into auth.users(id) values({quoted(OWNER)})")
query(f"insert into public.wm_spaces(id,owner_id,label,state,archive_revision) values({quoted(SPACE)},{quoted(OWNER)},'synthetic','active',1)")
query(f"insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd) values({quoted(SPACE)},true,'2026-01-01','test-pipeline',1000000)")
query(f"insert into public.wm_archive_documents(space_id,id,source_id,event_date,observed_at,title,body_hash,export_hash,body,export,metadata_json,registered_revision) values({quoted(SPACE)},{quoted(doc)},{quoted(source)},'2026-10-06','2026-10-06T00:00:00Z','Synthetisches Meeting',{quoted(bodyhash)},{quoted(bodyhash)},{quoted(body)},{quoted(body)},{quoted(meta)},1)")
query(f"insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state) values({quoted(SPACE)},{quoted(job)},{quoted(doc)},{quoted(source)},'2026-10-06','test-pipeline','queued')")
lease=str(uuid4())
claimed=query(f"select public.wm_claim_job({quoted(SPACE)},'test-pipeline',{quoted(lease)})")
assert claimed['id']==job and claimed['state']=='running'
late=os.environ.get('TEST_LATE_RECEIPT')=='1'
if late:
    query(f"insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd) values({quoted(SPACE)},{quoted(job)},0,{quoted(request)},{quoted(sha(request))},1000)")
else:
    query(f"insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd,response_json,response_hash,actual_micro_usd,received_at) values({quoted(SPACE)},{quoted(job)},0,{quoted(request)},{quoted(sha(request))},1000,{quoted(response)},{quoted(sha(response))},900,clock_timestamp())")
reason='provider_outcome_unknown' if late else 'validation_failed'
isolated=query(f"select public.wm_isolate_failed_job({quoted(SPACE)},{quoted(job)},{quoted(lease)},{quoted(reason)},{quoted(bodyhash)})")
assert isolated['isolated'] is True
assert query(f"select public.wm_job_isolation_valid({quoted(SPACE)},{quoted(job)})") is True
archived=os.environ.get('TEST_ARCHIVE_OWNER')=='1'
if archived:
    stamp=query(f"select to_jsonb(updated_at) from public.wm_jobs where space_id={quoted(SPACE)} and id={quoted(job)}")
    command=str(uuid4())
    recovered=query(f"select public.wm_resolve_job({quoted(SPACE)},{quoted(OWNER)},{quoted(command)},"
      f"{quoted(job)},0,{quoted(stamp)}::timestamptz,'archive_only','Synthetisch bestätigte Ownerentscheidung',null)")
    assert recovered['state']=='archived'
    assert query(f"select public.wm_job_isolation_valid({quoted(SPACE)},{quoted(job)})") is False
if late:
    received=query(f"select public.wm_receive_call({quoted(SPACE)},{quoted(job)},{quoted(lease)},0,{quoted(response)},900)")
    assert received['saved'] is True
    assert query(f"select public.wm_job_isolation_valid({quoted(SPACE)},{quoted(job)})") is False

with tempfile.TemporaryDirectory(prefix='isolated-audit-',dir='/private/tmp/dashboard-sol-operational-20261006') as tmp:
    folder=Path(tmp)/'backup'
    receipt=export(Store(),folder)
    assert receipt['verified'] is True and receipt['queue_records']['job_isolation']==1
    assert verify(folder)['verified'] is True
    ledger=Path(tmp)/'deletion-ledger.json'
    write_ledger(ledger,space_id=SPACE,minimum_deletion_revision=0,deletions=[],observed_at='2026-10-06T00:00:00Z')
    plan=Path(tmp)/'restore.sql'
    restored=generate(folder,plan,restore_ledger=ledger)
    assert restored['tables']['wm_job_isolations']==1
    sql=plan.read_text()
    assert "INSERT INTO public.wm_job_isolations" in sql and 'Restore verification failed: wm_job_isolations' in sql
    query(f"insert into auth.users(id) values({quoted(OWNER)})",TARGET)
    applied=subprocess.run(['psql','-h',SOCKET,'-p','55442','-d',TARGET,'-X','-v','ON_ERROR_STOP=1','-f',str(plan)],
        text=True,capture_output=True)
    if applied.returncode:raise AssertionError(applied.stderr[-1500:])
    assert query(f"select public.wm_job_isolation_valid({quoted(SPACE)},{quoted(job)})",TARGET) is (not archived and not late)
    assert query(f"select state from public.wm_jobs where id={quoted(job)}",TARGET)==('archived' if archived else 'review')
    assert query(f"select count(*) from public.wm_model_calls where job_id={quoted(job)}",TARGET)==1
    if late:
        assert query(f"select to_jsonb(c) from public.wm_model_calls c where job_id={quoted(job)}",TARGET)==query(f"select to_jsonb(c) from public.wm_model_calls c where job_id={quoted(job)}")
        assert query(f"select to_jsonb(a) from public.wm_job_isolations a where job_id={quoted(job)}",TARGET)==query(f"select to_jsonb(a) from public.wm_job_isolations a where job_id={quoted(job)}")
    if archived:
        assert query(f"select count(*) from public.wm_job_decisions where job_id={quoted(job)}",TARGET)==1
        assert query(f"select count(*) from public.wm_job_isolations where job_id={quoted(job)}",TARGET)==1
        assert query(f"select public.wm_job_isolation_valid({quoted(SPACE)},{quoted(job)})",TARGET) is False
        print(json.dumps({'backup_verified':True,'owner_archive_only':True,'historical_audit_retained':True,
            'late_receipt':late,'active_skip_false':True,'restore_sql_sha256':restored['sql_sha256']},sort_keys=True))
        raise SystemExit(0)
    query(f"update public.wm_processing_config set enabled=true where space_id={quoted(SPACE)}",TARGET)
    if late:
        blocked=query(f"select public.wm_claim_job({quoted(SPACE)},'test-pipeline',{quoted(str(uuid4()))})",TARGET)
        assert blocked['state']=='paused' and blocked['job_id']==job and blocked['reason']=='provider_outcome_unknown'
        print(json.dumps({'backup_verified':True,'late_receipt':True,'historical_audit_retained':True,
            'active_skip_false':True,'claim_paused_on_B':True,'restore_sql_sha256':restored['sql_sha256']},sort_keys=True))
        raise SystemExit(0)
    csource='synthetic:later-valid';cbody='00:00 Cara: Der neue Bericht bleibt gültig.';chash=sha(cbody)
    cmeta=encode({'source_id':csource,'event_date':'2026-10-07','title':'Späteres synthetisches Meeting',
        'body_sha256':chash,'export_sha256':chash,'body_offset_characters':0})
    cdoc=sha(csource+':'+cmeta);cjob=sha(csource+':'+chash);clease=str(uuid4())
    query(f"update public.wm_spaces set archive_revision=2 where id={quoted(SPACE)}",TARGET)
    query(f"insert into public.wm_archive_documents(space_id,id,source_id,event_date,observed_at,title,body_hash,export_hash,body,export,metadata_json,registered_revision) values({quoted(SPACE)},{quoted(cdoc)},{quoted(csource)},'2026-10-07','2026-10-07T00:00:00Z','Späteres synthetisches Meeting',{quoted(chash)},{quoted(chash)},{quoted(cbody)},{quoted(cbody)},{quoted(cmeta)},2)",TARGET)
    query(f"insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state) values({quoted(SPACE)},{quoted(cjob)},{quoted(cdoc)},{quoted(csource)},'2026-10-07','test-pipeline','queued')",TARGET)
    claimed=query(f"select public.wm_claim_job({quoted(SPACE)},'test-pipeline',{quoted(clease)})",TARGET)
    assert claimed['id']==cjob and claimed['state']=='running'
    payload=encode({'format':'wm-source-batch-v1','pipeline':'test-pipeline','result_sha256':'c'*64})
    query(f"select public.wm_prepare_job({quoted(SPACE)},{quoted(cjob)},{quoted(clease)},{quoted(payload)}::jsonb)",TARGET)
    published=query(f"select public.wm_publish_job({quoted(SPACE)},{quoted(cjob)},{quoted(clease)})",TARGET)
    assert published['state']=='applied' and published['revision']==1
    assert query(f"select state from public.wm_jobs where id={quoted(job)}",TARGET)=='review'
    query(f"delete from public.wm_job_isolations where space_id={quoted(SPACE)} and job_id={quoted(job)}",TARGET)
    denied=query(f"select public.wm_claim_job({quoted(SPACE)},'test-pipeline',{quoted(str(uuid4()))})",TARGET)
    assert denied['job_id']==job and denied['state']=='paused' and denied['reason']=='validation_failed'
    print(json.dumps({'backup_verified':True,'job_isolation_records':1,'restore_sql_sha256':restored['sql_sha256'],
        'archive_originals':receipt['documents'],'model_calls':receipt['queue_records']['call'],
        'canonical_data_restore_applied':True,'later_job_after_restore':'applied',
        'missing_audit_denied':True},sort_keys=True))
