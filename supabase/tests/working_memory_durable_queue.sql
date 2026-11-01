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
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Synthetic queue');
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666667','55555555-5555-4555-8555-555555555555','Synthetic concurrent decision');
insert into public.wm_processing_config(space_id) values('66666666-6666-4666-8666-666666666666');
insert into public.wm_processing_config(space_id) values('66666666-6666-4666-8666-666666666667');
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; d text; r jsonb;
begin
 d:=pg_temp.doc(s,'synthetic:old','2026-06-01','Unchanged historical original.');
 r:=public.wm_enqueue(s,d,'test-v1');
 perform pg_temp.expect(r->>'state'='archive_only','historical source never creates a job');
 perform pg_temp.expect((select count(*)=0 from public.wm_jobs where space_id=s),'no old-stock job');
 perform pg_temp.expect(public.wm_claim_job(s,'test-v1',gen_random_uuid())->>'state'='disabled','default disabled');
end; $$;
update public.wm_processing_config set enabled=true,automatic_from='2026-09-07',pipeline='test-v1',budget_micro_usd=1000000
where space_id in ('66666666-6666-4666-8666-666666666666','66666666-6666-4666-8666-666666666667');
set local role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; d text; r jsonb; j jsonb;
 lease uuid:=gen_random_uuid(); payload jsonb;
begin
 d:=pg_temp.doc(s,'synthetic:one','2026-09-07','Alex: I will send the agenda.');
 j:=public.wm_enqueue(s,d,'test-v1');
 perform pg_temp.expect(j->>'state'='queued','future source queued');
 perform pg_temp.expect((public.wm_enqueue(s,d,'test-v1')->>'repeated')::boolean,'duplicate enqueue is idempotent');
 j:=public.wm_claim_job(s,'test-v1',lease);
 perform pg_temp.expect(j->>'state'='running' and (j->>'expected_revision')::integer=0,'claim pins context');
 perform pg_temp.expect(public.wm_claim_job(s,'test-v1',gen_random_uuid())->>'state'='waiting','other worker cannot overtake');
 r:=public.wm_reserve_call(s,j->>'id',lease,0,'{"model":"synthetic","prompt":"private fictional text"}',800000);
 perform pg_temp.expect((r->>'send')::boolean,'reservation before sending');
 r:=public.wm_reserve_call(s,j->>'id',lease,0,'{"model":"synthetic","prompt":"private fictional text"}',800000);
 perform pg_temp.expect(not (r->>'send')::boolean and r->>'response_json' is null,'unknown call cannot be sent twice');
 perform public.wm_receive_call(s,j->>'id',lease,0,'{"usage_final":true,"content":[]}',200000);
 r:=public.wm_reserve_call(s,j->>'id',lease,0,'{"model":"synthetic","prompt":"private fictional text"}',800000);
 perform pg_temp.expect(not (r->>'send')::boolean and r->>'response_json' is not null,'saved response replay without model');
 r:=public.wm_reserve_call(s,j->>'id',lease,1,'{"model":"synthetic","prompt":"gate"}',900000);
 perform pg_temp.expect(r->>'state'='budget_exceeded','budget holds across calls');
 perform pg_temp.expect((select count(*)=1 from public.wm_model_calls where space_id=s),'budget refusal does not create a reservation');
 begin
   perform public.wm_receive_call(s,j->>'id',lease,0,'{"changed":true}',1);
   raise exception 'FAILED: changed response accepted';
 exception when unique_violation then null; end;
 payload:=jsonb_build_object('format','wm-source-batch-v1','pipeline','test-v1','result_sha256',repeat('a',64),
   'proposal',jsonb_build_object('observations','[]'::jsonb));
 perform public.wm_prepare_job(s,j->>'id',lease,payload);
 r:=public.wm_publish_job(s,j->>'id',lease);
 perform pg_temp.expect(r->>'state'='applied' and (r->>'revision')::integer=1,'publication atomic with journal');
 perform pg_temp.expect((public.wm_publish_job(s,j->>'id',lease)->>'repeated')::boolean,'publication retry same revision');
 perform pg_temp.expect((select count(*)=1 from public.wm_journal where space_id=s),'exactly one journal entry');
 begin
   update public.wm_processing_config set budget_micro_usd=999999999 where space_id=s;
   raise exception 'FAILED: worker increased budget';
 exception when insufficient_privilege then null; end;
end; $$;
reset role;
-- A user decision while the model runs fences its saved result at publication.
do $$
declare s uuid:='66666666-6666-4666-8666-666666666667'; d text; j jsonb; lease uuid:=gen_random_uuid(); p jsonb;
begin
 d:=pg_temp.doc(s,'synthetic:concurrent','2026-09-07','A fictional new source.');
 perform public.wm_enqueue(s,d,'test-v1');j:=public.wm_claim_job(s,'test-v1',lease);
 p:=jsonb_build_object('format','wm-source-batch-v1','pipeline','test-v1','result_sha256',repeat('b',64),
   'proposal',jsonb_build_object('observations','[]'::jsonb));
 perform public.wm_prepare_job(s,j->>'id',lease,p);
 perform public.wm_append(s,0,gen_random_uuid(),'human','{"action":"correct","target_id":"synthetic","reason":"Synthetic concurrent edit"}',null,'55555555-5555-4555-8555-555555555555');
 perform pg_temp.expect(public.wm_publish_job(s,j->>'id',lease)->>'reason'='context_changed','human decision fences model publication');
 perform pg_temp.expect((select count(*)=0 from public.wm_source_versions where space_id=s),'conflict does not publish source');
 perform pg_temp.expect((select prepared_payload=p from public.wm_jobs where space_id=s and id=j->>'id'),'paid prepared result retained on conflict');
end; $$;
-- Crash after a reservation: the next worker pauses, retaining full reserve.
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; j jsonb; lease uuid:=gen_random_uuid(); d text;
begin
 d:=pg_temp.doc(s,'synthetic:two','2026-09-08','Later original.');
 perform public.wm_enqueue(s,d,'test-v1');
 j:=public.wm_claim_job(s,'test-v1',lease);
 perform public.wm_reserve_call(s,j->>'id',lease,0,'{"prompt":"crash"}',500000);
 update public.wm_jobs set lease_until=now()-interval '1 second' where space_id=s and id=j->>'id';
 perform pg_temp.expect(public.wm_claim_job(s,'test-v1',gen_random_uuid())->>'reason'='provider_outcome_unknown','crash pauses without repeat');
 perform pg_temp.expect((select sum(coalesce(actual_micro_usd,reserved_micro_usd))=700000 from public.wm_model_calls where space_id=s),'unknown usage remains charged');
 d:=pg_temp.doc(s,'synthetic:three','2026-09-09','Still later original.');
 perform public.wm_enqueue(s,d,'test-v1');
 perform pg_temp.expect(public.wm_claim_job(s,'test-v1',gen_random_uuid())->>'reason'='provider_outcome_unknown','later meeting cannot skip failed predecessor');
 d:=pg_temp.doc(s,'synthetic:one','2026-09-07','Changed original.');
 perform pg_temp.expect(public.wm_enqueue(s,d,'test-v1')->>'reason'='changed_source_requires_review','changed original is reviewed');
end; $$;
set local role authenticated;
select set_config('request.jwt.claim.sub','77777777-7777-4777-8777-777777777777',true);
select pg_temp.expect((select count(*)=0 from public.wm_jobs),'other owner cannot read jobs');
select pg_temp.expect((select count(*)=0 from public.wm_model_calls),'other owner cannot read private calls');
do $$ begin
 begin
   perform public.wm_claim_job('66666666-6666-4666-8666-666666666666','test-v1',gen_random_uuid());
   raise exception 'FAILED: browser claimed work';
 exception when insufficient_privilege then null; end;
end; $$;
reset role;
rollback;
