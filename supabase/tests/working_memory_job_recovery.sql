begin;
create function pg_temp.expect(ok boolean, label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid, source text, day date, body text) returns text language plpgsql as $$
declare m text; h text; identifier text; result jsonb;
begin
 h:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 m:=jsonb_build_object('source_id',source,'event_date',day,'title','Synthetic queue check',
   'body_sha256',h,'export_sha256',h,'body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to(source||':'||m,'UTF8'),'sha256'),'hex');
 result:=public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source,'event_date',day::text,
   'observed_at','2026-09-07T12:00:00Z','title','Synthetic queue check','body_hash',h,'export_hash',h,
   'body',body,'export',body,'metadata_json',m));
 return identifier;
end; $$;
insert into auth.users(id) values('55555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Synthetic recovery');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
values('66666666-6666-4666-8666-666666666666',true,'2026-09-07','test-v1',1000000);
set local role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; owner uuid:='55555555-5555-4555-8555-555555555555';
 d text; j jsonb; r jsonb; rec jsonb; replacement jsonb; prior_payload jsonb; lease uuid:=gen_random_uuid(); command uuid:=gen_random_uuid(); old_time timestamptz;
begin
 d:=pg_temp.doc(s,'synthetic:recovery','2026-09-07','Alex: I will send the agenda.');
 j:=public.wm_enqueue(s,d,'test-v1');j:=public.wm_claim_job(s,'test-v1',lease);
 old_time:=(j->>'updated_at')::timestamptz;
 begin
  perform public.wm_resolve_job(s,owner,command,j->>'id',0,old_time,'archive_only','Not while a worker is running');
  raise exception 'Live worker was interrupted';
 exception when serialization_failure then null; end;
 perform public.wm_reserve_call(s,j->>'id',lease,0,'{"model":"synthetic"}',500000);
 perform public.wm_pause_job(s,j->>'id',lease,'provider_outcome_unknown');
 j:=public.wm_job_detail(s,j->>'id')->'job';old_time:=(j->>'updated_at')::timestamptz;
 begin
  perform public.wm_resolve_job(s,owner,command,j->>'id',0,old_time,'retry','Try again');
  raise exception 'Unknown paid outcome repeated';
 exception when invalid_parameter_value then null; end;
 begin
  perform public.wm_resolve_job(s,gen_random_uuid(),command,j->>'id',0,old_time,'archive_only','Wrong owner');
  raise exception 'Wrong owner allowed';
 exception when insufficient_privilege then null; end;
 r:=public.wm_resolve_job(s,owner,command,j->>'id',0,old_time,'archive_only','Keep the original without adding work');
 perform pg_temp.expect(r->>'state'='archived','explicit archive decision');
 perform pg_temp.expect((public.wm_resolve_job(s,owner,command,j->>'id',0,old_time,'archive_only','Keep the original without adding work')->>'repeated')::boolean,'uncertain save repeats same receipt');
 begin
  perform public.wm_resolve_job(s,owner,command,j->>'id',0,old_time,'archive_only','Different reason');
  raise exception 'Changed decision reused';
 exception when unique_violation then null; end;
 perform pg_temp.expect(public.wm_claim_job(s,'test-v1',gen_random_uuid())->>'state'='idle','archived head does not block');
 perform public.wm_receive_call(s,j->>'id',lease,0,'{"usage":1}',600000);
 perform pg_temp.expect(public.wm_job_detail(s,j->>'id')->'job'->>'state'='archived','late expensive receipt does not resurrect archived job');
 perform pg_temp.expect((public.wm_processing_status(s)->>'accounted_micro_usd')::bigint=600000,'late cost is still accounted');
 perform pg_temp.expect((public.wm_processing_status(s)->>'archived_count')::integer=1,'archive decision remains visible');
 perform pg_temp.expect((select count(*)=1 from public.wm_job_decisions where space_id=s),'one immutable recovery record');
 d:=pg_temp.doc(s,'synthetic:retry','2026-09-08','Alex: Another agenda.');
 j:=public.wm_enqueue(s,d,'test-v1');lease:=gen_random_uuid();j:=public.wm_claim_job(s,'test-v1',lease);
 perform public.wm_pause_job(s,j->>'id',lease,'transport_failed');
 j:=public.wm_job_detail(s,j->>'id')->'job';old_time:=(j->>'updated_at')::timestamptz;
 begin
  perform public.wm_resolve_job(s,owner,gen_random_uuid(),j->>'id',1,old_time,'retry','Stale revision');
  raise exception 'Stale view accepted';
 exception when serialization_failure then null; end;
 r:=public.wm_resolve_job(s,owner,gen_random_uuid(),j->>'id',0,old_time,'retry','No model call was sent');
 perform pg_temp.expect(r->>'state'='queued','clean failed transport can resume');
 j:=public.wm_claim_job(s,'test-v1',gen_random_uuid());
 perform pg_temp.expect(j->>'state'='running' and (j->>'attempts')::integer=1,'new audited retry gets bounded attempts');
 lease:=(j->>'lease_token')::uuid;
 prior_payload:=jsonb_build_object('format','wm-source-batch-v1','pipeline','test-v1','result_sha256',repeat('a',64),'proposal',jsonb_build_object('observations','[]'::jsonb,'coverage_notes','[]'::jsonb));
 perform public.wm_prepare_job(s,j->>'id',lease,prior_payload);
 perform public.wm_pause_job(s,j->>'id',lease,'context_changed');
 perform public.wm_append(s,0,gen_random_uuid(),'human','{"action":"correct","target_id":"synthetic","reason":"Independent owner change"}'::jsonb,null,owner);
 j:=public.wm_job_detail(s,j->>'id')->'job';old_time:=(j->>'updated_at')::timestamptz;
 begin
  perform public.wm_resolve_job(s,owner,gen_random_uuid(),j->>'id',1,old_time,'retry','Cannot silently repin');
  raise exception 'Changed context silently retried';
 exception when invalid_parameter_value then null; end;
 command:=gen_random_uuid();
 replacement:=prior_payload||jsonb_build_object('result_sha256',repeat('b',64),'provenance',jsonb_build_object('owner_id',owner,'owner_recovery_command',command));
 begin
  perform public.wm_resolve_job(s,owner,command,j->>'id',1,old_time,'rebase_prepared','Wrong summary',replacement||jsonb_build_object('archive_note','{"fake":true}'::jsonb));
  raise exception 'Summary replaced during recovery';
 exception when invalid_parameter_value then null; end;
 r:=public.wm_resolve_job(s,owner,command,j->>'id',1,old_time,'rebase_prepared','Reviewed exact saved result',replacement);
 perform pg_temp.expect(r->>'state'='prepared','reviewed result remains prepared');
 perform pg_temp.expect((select previous_job->'prepared_payload'=prior_payload from public.wm_job_decisions where space_id=s and command_id=command),'previous prepared result retained immutably');
 j:=public.wm_claim_job(s,'test-v1',gen_random_uuid());
 perform pg_temp.expect(j->>'state'='prepared' and (j->>'expected_revision')::integer=1,'reviewed result publishes without another model request');

end; $$;
reset role;
set local role authenticated;
do $$ begin
 begin
  perform public.wm_resolve_job('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555',gen_random_uuid(),'x',0,now(),'retry','Bypass gateway');
  raise exception 'Browser can bypass semantic boundary';
 exception when insufficient_privilege then null; end;
end; $$;
reset role;
rollback;
