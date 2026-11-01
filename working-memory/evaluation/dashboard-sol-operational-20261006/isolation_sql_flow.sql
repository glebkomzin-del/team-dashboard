\set ON_ERROR_STOP on
begin;
insert into auth.users(id) values('00000000-0000-0000-0000-000000000001');
insert into public.wm_spaces(id,owner_id,label,state) values('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','isolated flow','active');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
 values('10000000-0000-0000-0000-000000000001',true,'2026-01-01','test-pipeline',1000000000);
insert into public.wm_archive_documents(space_id,id,source_id,event_date,observed_at,title,body_hash,export_hash,body,export,metadata_json,registered_revision)
select '10000000-0000-0000-0000-000000000001',
 encode(extensions.digest(convert_to('doc-'||tag,'UTF8'),'sha256'),'hex'),
 'source-'||tag, ('2026-10-0'||day)::date,'2026-10-01T00:00:00Z','Meeting '||tag,
 encode(extensions.digest(convert_to('body-'||tag,'UTF8'),'sha256'),'hex'),
 encode(extensions.digest(convert_to('export-'||tag,'UTF8'),'sha256'),'hex'),
 'body-'||tag,'export-'||tag,'{}',day
from (values('A',1),('B',2),('C',3)) x(tag,day);
insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state)
select space_id,encode(extensions.digest(convert_to(source_id||':'||body_hash,'UTF8'),'sha256'),'hex'),
 id,source_id,event_date,'test-pipeline','queued' from public.wm_archive_documents;

do $$
declare sid uuid:='10000000-0000-0000-0000-000000000001';
 ta uuid:='11111111-1111-1111-1111-111111111111';
 tb uuid:='22222222-2222-2222-2222-222222222222';
 tc uuid:='33333333-3333-3333-3333-333333333333';
 a text; b text; c text; bh text; r jsonb;
begin
 select id into a from public.wm_jobs where space_id=sid and source_id='source-A';
 select id into b from public.wm_jobs where space_id=sid and source_id='source-B';
 select id into c from public.wm_jobs where space_id=sid and source_id='source-C';
 select body_hash into bh from public.wm_archive_documents where space_id=sid and source_id='source-B';
 r:=public.wm_claim_job(sid,'test-pipeline',ta);
 if r->>'id' is distinct from a or r->>'state' is distinct from 'running' then raise exception 'A claim failed: %',r; end if;
 r:=public.wm_prepare_job(sid,a,ta,jsonb_build_object('format','wm-source-batch-v1','pipeline','test-pipeline','result_sha256',repeat('a',64)));
 r:=public.wm_publish_job(sid,a,ta);
 if r->>'state' is distinct from 'applied' or (r->>'revision')::bigint is distinct from 1 then raise exception 'A publish failed: %',r; end if;
 r:=public.wm_claim_job(sid,'test-pipeline',tb);
 if r->>'id' is distinct from b or r->>'state' is distinct from 'running' then raise exception 'B claim failed: %',r; end if;
 insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd,
   response_json,response_hash,actual_micro_usd,received_at)
 values(sid,b,0,'{}',encode(extensions.digest(convert_to('{}','UTF8'),'sha256'),'hex'),1000,'{}',encode(extensions.digest(convert_to('{}','UTF8'),'sha256'),'hex'),900,clock_timestamp());
 r:=public.wm_isolate_failed_job(sid,b,tb,'validation_failed',bh);
 if r->>'isolated' is distinct from 'true' or not public.wm_job_isolation_valid(sid,b) then raise exception 'B isolation failed: %',r; end if;
 r:=public.wm_processing_status(sid);
 if (r->>'isolated_count')::integer is distinct from 1 or not exists(select 1 from jsonb_array_elements(r->'jobs') x where x->>'id'=b and x->>'technical_isolation'='true') then
  raise exception 'Isolation not visible: %',r; end if;
 -- A later guarded deployment retargets only unpaid C. Paid B keeps its
 -- immutable old pipeline and still has a valid isolation proof.
 update public.wm_processing_config set pipeline='next-pipeline' where space_id=sid;
 update public.wm_jobs set pipeline='next-pipeline' where space_id=sid and id=c and state='queued';
 if not public.wm_job_isolation_valid(sid,b)
   or (select pipeline from public.wm_jobs where space_id=sid and id=b) is distinct from 'test-pipeline' then
   raise exception 'Paid B isolation was invalidated or retargeted by new generation'; end if;
 r:=public.wm_claim_job(sid,'next-pipeline',tc);
 if r->>'id' is distinct from c or r->>'state' is distinct from 'running' then raise exception 'C claim bypass failed: %',r; end if;
 r:=public.wm_prepare_job(sid,c,tc,jsonb_build_object('format','wm-source-batch-v1','pipeline','next-pipeline','result_sha256',repeat('c',64)));
 r:=public.wm_publish_job(sid,c,tc);
 if r->>'state' is distinct from 'applied' or (r->>'revision')::bigint is distinct from 2 then raise exception 'C publish bypass failed: %',r; end if;
 if (select state from public.wm_jobs where space_id=sid and id=b) is distinct from 'review'
   or exists(select 1 from public.wm_source_versions where space_id=sid and id=b)
   or (select count(*) from public.wm_journal where space_id=sid) is distinct from 2 then
  raise exception 'B was falsely applied or journal history changed'; end if;
 raise notice 'A_APPLIED_B_ISOLATED_C_APPLIED_PASS';
end $$;
rollback;
