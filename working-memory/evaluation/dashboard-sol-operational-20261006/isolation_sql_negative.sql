\set ON_ERROR_STOP on
begin;
insert into auth.users(id) values('00000000-0000-0000-0000-000000000002');
do $$
declare n integer; sid uuid; b text; c text; bh text; bt uuid; ct uuid; r jsonb; body text; src text;
begin
 for n in 1..10 loop
  sid:=('20000000-0000-0000-0000-'||lpad(n::text,12,'0'))::uuid;
  bt:=('30000000-0000-0000-0000-'||lpad(n::text,12,'0'))::uuid;
  ct:=('40000000-0000-0000-0000-'||lpad(n::text,12,'0'))::uuid;
  insert into public.wm_spaces(id,owner_id,label,state) values(sid,'00000000-0000-0000-0000-000000000002','negative '||n,case when n=1 then 'active' else 'draft' end);
  insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
   values(sid,true,'2026-01-01','test-pipeline',1000000000);
  for src in select x from (values ('B'),('C')) a(x) loop
   body:='body-'||n||'-'||src;
   insert into public.wm_archive_documents(space_id,id,source_id,event_date,observed_at,title,body_hash,export_hash,body,export,metadata_json,registered_revision)
   values(sid,encode(extensions.digest(convert_to('doc-'||n||'-'||src,'UTF8'),'sha256'),'hex'),
    'source-'||n||'-'||src,case when src='B' then '2026-10-02'::date else '2026-10-03'::date end,
    '2026-10-01T00:00:00Z','Meeting '||src,
    encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex'),repeat('e',64),body,'export','{}',1);
  end loop;
  insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state)
   select space_id,encode(extensions.digest(convert_to(source_id||':'||body_hash,'UTF8'),'sha256'),'hex'),
    id,source_id,event_date,'test-pipeline','queued' from public.wm_archive_documents where space_id=sid;
  select id into b from public.wm_jobs where space_id=sid and source_id='source-'||n||'-B';
  select id into c from public.wm_jobs where space_id=sid and source_id='source-'||n||'-C';
  select body_hash into bh from public.wm_archive_documents where space_id=sid and source_id='source-'||n||'-B';
  if n=6 then
   update public.wm_jobs set state='review',reason='human_review' where space_id=sid and id=b;
   r:=public.wm_claim_job(sid,'test-pipeline',ct);
   if r->>'state' is distinct from 'paused' or r->>'job_id' is distinct from b then raise exception 'Unproven review bypass: %',r; end if;
   continue;
  end if;
  r:=public.wm_claim_job(sid,'test-pipeline',bt);
  if r->>'id' is distinct from b then raise exception 'B claim failed n% %',n,r; end if;
  if n=1 then
   r:=public.wm_isolate_failed_job(sid,b,ct,'validation_failed',bh);
   if r->>'isolated' is distinct from 'false' then raise exception 'Wrong owner accepted'; end if;
   r:=public.wm_isolate_failed_job(sid,b,bt,'validation_failed',repeat('a',64));
   if r->>'isolated' is distinct from 'false' then raise exception 'Wrong source hash accepted'; end if;
   update public.wm_spaces set revision=revision+1 where id=sid;
   r:=public.wm_isolate_failed_job(sid,b,bt,'validation_failed',bh);
   if r->>'isolated' is distinct from 'false' then raise exception 'Stale revision accepted'; end if;
   if (select state from public.wm_jobs where space_id=sid and id=b) is distinct from 'running' then raise exception 'Denied isolate mutated state'; end if;
  elsif n=2 then
   insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd)
     values(sid,b,0,'{}',encode(extensions.digest(convert_to('{}','UTF8'),'sha256'),'hex'),1000);
   r:=public.wm_isolate_failed_job(sid,b,bt,'provider_outcome_unknown',bh);
   if r->>'isolated' is distinct from 'true' or not public.wm_job_isolation_valid(sid,b) then raise exception 'Unknown proof failed'; end if;
   r:=public.wm_claim_job(sid,'test-pipeline',ct);
   if r->>'id' is distinct from c then raise exception 'Unknown did not skip'; end if;
   r:=public.wm_receive_call(sid,b,bt,0,'{}',900);
   if r->>'saved' is distinct from 'true' or public.wm_job_isolation_valid(sid,b) then raise exception 'Late receipt not preserved or proof did not invalidate'; end if;
   r:=public.wm_claim_job(sid,'test-pipeline',ct);
   if r->>'state' is distinct from 'paused' or r->>'job_id' is distinct from b then raise exception 'Changed unknown call did not stop chronology: %',r; end if;
  elsif n=3 then
   update public.wm_jobs set attempts=3,lease_until=clock_timestamp()-interval '1 second' where space_id=sid and id=b;
   r:=public.wm_claim_job(sid,'test-pipeline',ct);
   if r->>'technical_isolation' is distinct from 'true' or r->>'reason' is distinct from 'attempt_limit' or not public.wm_job_isolation_valid(sid,b) then
    raise exception 'Attempt proof failed: %',r; end if;
   r:=public.wm_claim_job(sid,'test-pipeline',ct);
   if r->>'id' is distinct from c then raise exception 'Attempt limit did not skip: %',r; end if;
  elsif n=4 then
   r:=public.wm_append(sid,0,gen_random_uuid(),'human',jsonb_build_object('action','note','target_id','source-'||n||'-B','reason','owner context change'),null,'00000000-0000-0000-0000-000000000002');
   update public.wm_jobs set lease_until=clock_timestamp()-interval '1 second' where space_id=sid and id=b;
   r:=public.wm_claim_job(sid,'test-pipeline',ct);
   if r->>'technical_isolation' is distinct from 'true' or r->>'reason' is distinct from 'context_changed' or not public.wm_job_isolation_valid(sid,b) then
    raise exception 'Context proof failed: %',r; end if;
   r:=public.wm_claim_job(sid,'test-pipeline',ct);
   if r->>'id' is distinct from c or (select count(*) from public.wm_journal where space_id=sid and actor_id='00000000-0000-0000-0000-000000000002') is distinct from 1 then
    raise exception 'Human change not preserved: %',r; end if;
  elsif n in (8,9,10) then
   body:=case when n=8 then '{"error":"HTTP 401","usage_final":false,"terminal_status":null,"stop_reason":null}'
     when n=9 then '{"error":"TimeoutError","usage_final":false,"terminal_status":null,"stop_reason":null}'
     else '{"error":"UnrecognizedFailure","usage_final":false,"terminal_status":null,"stop_reason":null}' end;
   insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd,response_json,response_hash,received_at)
    values(sid,b,0,'{}',encode(extensions.digest(convert_to('{}','UTF8'),'sha256'),'hex'),1000,
      body,encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex'),clock_timestamp());
   r:=public.wm_isolate_failed_job(sid,b,bt,'provider_outcome_unknown',bh);
   if n=9 then
    if r->>'isolated' is distinct from 'true' or not public.wm_job_isolation_valid(sid,b) then raise exception 'Lost transport not isolated: %',r; end if;
    r:=public.wm_claim_job(sid,'test-pipeline',ct);
    if r->>'id' is distinct from c then raise exception 'Lost transport blocked unrelated source'; end if;
   else
    if r->>'isolated' is distinct from 'false' then raise exception 'HTTP/unrecognized error incorrectly isolated: %',r; end if;
    r:=public.wm_pause_job(sid,b,bt,'provider_shared_failure');
    if r->>'paused' is distinct from 'true' then raise exception 'Shared provider pause failed'; end if;
    r:=public.wm_processing_status(sid);
    if r->'blocking_job'->>'reason' is distinct from 'provider_shared_failure' or (r->>'isolated_count')::integer is distinct from 0 then
      raise exception 'Shared provider stop not visible: %',r; end if;
    r:=public.wm_claim_job(sid,'test-pipeline',ct);
    if r->>'state' is distinct from 'paused' or r->>'job_id' is distinct from b then raise exception 'Shared provider failure bypassed'; end if;
   end if;
  elsif n in (5,7) then
   insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd,response_json,response_hash,actual_micro_usd,received_at)
    values(sid,b,0,'{}',encode(extensions.digest(convert_to('{}','UTF8'),'sha256'),'hex'),1000,'{}',encode(extensions.digest(convert_to('{}','UTF8'),'sha256'),'hex'),900,clock_timestamp());
   r:=public.wm_isolate_failed_job(sid,b,bt,'validation_failed',bh);
   if r->>'isolated' is distinct from 'true' then raise exception 'Initial proof absent'; end if;
   if n=5 then
    r:=public.wm_claim_job(sid,'test-pipeline',ct);
    if r->>'id' is distinct from c then raise exception 'C claim failed'; end if;
    r:=public.wm_prepare_job(sid,c,ct,jsonb_build_object('format','wm-source-batch-v1','pipeline','test-pipeline','result_sha256',repeat('c',64)));
    update public.wm_model_calls set response_hash=repeat('f',64) where space_id=sid and job_id=b;
    if public.wm_job_isolation_valid(sid,b) then raise exception 'Changed call still valid'; end if;
    r:=public.wm_publish_job(sid,c,ct);
    if r->>'reason' is distinct from 'context_changed' or exists(select 1 from public.wm_source_versions where space_id=sid and id=c) then
     raise exception 'Publish ignored stale call proof: %',r; end if;
   else
    update public.wm_archive_documents set body_hash=repeat('f',64) where space_id=sid and source_id='source-'||n||'-B';
    if public.wm_job_isolation_valid(sid,b) then raise exception 'Changed body still valid'; end if;
    r:=public.wm_claim_job(sid,'test-pipeline',ct);
    if r->>'state' is distinct from 'paused' or r->>'job_id' is distinct from b then raise exception 'Claim ignored stale body proof: %',r; end if;
   end if;
  end if;
 end loop;
 raise notice 'NEGATIVE_PROOFS_UNKNOWN_ATTEMPTS_CONTEXT_HUMAN_SHARED_PASS';
end $$;
rollback;
