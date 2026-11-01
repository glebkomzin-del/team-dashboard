begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid,source text,day date,body text) returns text language plpgsql as $$
declare metadata text; body_hash text; identifier text;
begin
 body_hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 metadata:=jsonb_build_object('source_id',source,'event_date',day,'title','Pipeline recovery fixture',
  'body_sha256',body_hash,'export_sha256',body_hash,'body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to(source||':'||metadata,'UTF8'),'sha256'),'hex');
 perform public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source,'event_date',day::text,
  'observed_at','2026-09-20T12:00:00Z','title','Pipeline recovery fixture','body_hash',body_hash,
  'export_hash',body_hash,'body',body,'export',body,'metadata_json',metadata));
 return identifier;
end; $$;
insert into auth.users(id) values('95555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label) values('96666666-6666-4666-8666-666666666666','95555555-5555-4555-8555-555555555555','Pipeline recovery');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
 values('96666666-6666-4666-8666-666666666666',true,'2026-09-20','pipeline-v1',1000000);
set local role service_role;
do $$
declare s uuid:='96666666-6666-4666-8666-666666666666'; document text; job jsonb; paused jsonb; recovered jsonb;
 lease uuid:=gen_random_uuid(); failure uuid:=gen_random_uuid(); diag jsonb;
begin
 diag:=jsonb_build_object('at',clock_timestamp(),'op','archive_document','type','http','http_status',503,'sqlstate','57014','attempts',3);
 document:=pg_temp.doc(s,'synthetic:pipeline-recovery','2026-09-20','Alex: Send the report.');
 job:=public.wm_enqueue(s,document,'pipeline-v1');job:=public.wm_claim_job(s,'pipeline-v1',lease);
 paused:=public.wm_pause_transport_job(s,job->>'id',lease,failure,diag);
 job:=public.wm_job_detail(s,job->>'id')->'job';
 recovered:=public.wm_recover_transport_job(s,job->>'id','pipeline-v1',failure,0,(job->>'updated_at')::timestamptz);
 perform pg_temp.expect(recovered->>'reason'='transport_retry_backoff','active lease and backoff prevent immediate recovery');
 update public.wm_jobs set lease_until=clock_timestamp()-interval '1 second' where space_id=s and id=job->>'id';
 update public.wm_pipeline_recoveries set next_retry_at=clock_timestamp()-interval '1 second' where space_id=s and failure_id=failure;
 recovered:=public.wm_recover_transport_job(s,job->>'id','pipeline-v1',failure,0,(job->>'updated_at')::timestamptz);
 perform pg_temp.expect(recovered->>'state'='queued' and (recovered->>'attempts')::integer=1,'safe failure requeued without resetting attempt history');
 perform pg_temp.expect((select recovered_at is not null and recovery_ordinal=1 from public.wm_pipeline_recoveries where space_id=s and failure_id=failure),'requeue audited');
 job:=public.wm_claim_job(s,'pipeline-v1',gen_random_uuid());lease:=(job->>'lease_token')::uuid;
 perform public.wm_reserve_call(s,job->>'id',lease,0,'{"model":"synthetic"}',1000);
 failure:=gen_random_uuid();perform public.wm_pause_transport_job(s,job->>'id',lease,failure,diag);
 job:=public.wm_job_detail(s,job->>'id')->'job';
 update public.wm_jobs set lease_until=clock_timestamp()-interval '1 second' where space_id=s and id=job->>'id';
 update public.wm_pipeline_recoveries set next_retry_at=clock_timestamp()-interval '1 second' where space_id=s and failure_id=failure;
 begin
  perform public.wm_recover_transport_job(s,job->>'id','pipeline-v1',failure,0,(job->>'updated_at')::timestamptz);
  raise exception 'Reserved model call was retried';
 exception when invalid_parameter_value then null; end;
 perform pg_temp.expect((public.wm_job_detail(s,job->>'id')->'transport_failures'->-1->>'op')='archive_document','redacted diagnostic is durable');
end; $$;
reset role;
set local role authenticated;
do $$ begin
 begin perform public.wm_recover_transport_job('96666666-6666-4666-8666-666666666666',repeat('a',64),'pipeline-v1',gen_random_uuid(),0,now());
  raise exception 'Browser bypassed recovery gateway'; exception when insufficient_privilege then null; end;
end; $$;
reset role;
rollback;
