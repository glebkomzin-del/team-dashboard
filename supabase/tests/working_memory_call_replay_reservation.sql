begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid,source text,day date,body text) returns text language plpgsql as $$
declare metadata text; body_hash text; identifier text;
begin
 body_hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 metadata:=jsonb_build_object('source_id',source,'event_date',day,'title','Call replay fixture',
  'body_sha256',body_hash,'export_sha256',body_hash,'body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to(source||':'||metadata,'UTF8'),'sha256'),'hex');
 perform public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source,'event_date',day::text,
  'observed_at','2026-09-20T12:00:00Z','title','Call replay fixture','body_hash',body_hash,
  'export_hash',body_hash,'body',body,'export',body,'metadata_json',metadata));
 return identifier;
end; $$;

insert into auth.users(id) values('a7111111-1111-4111-8111-111111111111');
insert into public.wm_spaces(id,owner_id,label)
 values('b7222222-2222-4222-8222-222222222222','a7111111-1111-4111-8111-111111111111','Call replay reservation');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
 values('b7222222-2222-4222-8222-222222222222',true,'2026-09-20','replay-v1',1000000);

set local role service_role;
do $$
declare s uuid:='b7222222-2222-4222-8222-222222222222'; document text; job jsonb; replay jsonb;
 lease uuid:='c7333333-3333-4333-8333-333333333333';
 request0 text:='{"model":"gpt-5.6-terra","max_tokens":100,"prompt":"synthetic","schema":{"type":"object"}}';
 request1 text:='{"model":"gpt-5.6-terra","max_tokens":100,"prompt":"unknown","schema":{"type":"object"}}';
begin
 document:=pg_temp.doc(s,'synthetic:call-replay','2026-09-20','Alex: Send the synthetic report.');
 job:=public.wm_enqueue(s,document,'replay-v1');job:=public.wm_claim_job(s,'replay-v1',lease);
 perform public.wm_reserve_call(s,job->>'id',lease,0,request0,1000);
 perform public.wm_receive_call(s,job->>'id',lease,0,'{"content":[],"usage_final":true}',800);

 replay:=public.wm_reserve_call(s,job->>'id',lease,0,request0,9000);
 perform pg_temp.expect(not (replay->>'send')::boolean and replay->>'response_json' is not null,
  'completed call replays without provider send');
 perform pg_temp.expect((replay->>'reserved_micro_usd')::bigint=1000 and (replay->>'actual_micro_usd')::bigint=800,
  'stored reservation and actual cost remain authoritative');
 perform pg_temp.expect((select reserved_micro_usd=1000 and actual_micro_usd=800 from public.wm_model_calls
  where space_id=s and job_id=job->>'id' and call_index=0),'replay does not mutate cost record');

 perform public.wm_reserve_call(s,job->>'id',lease,1,request1,2000);
 replay:=public.wm_reserve_call(s,job->>'id',lease,1,request1,7000);
 perform pg_temp.expect(not (replay->>'send')::boolean and replay->>'response_json' is null,
  'unknown response is never authorized for a second send');
 perform pg_temp.expect((replay->>'reserved_micro_usd')::bigint=2000,
  'unknown call retains its original reservation');

 begin
  perform public.wm_reserve_call(s,job->>'id',lease,0,
   '{"model":"gpt-5.6-terra","max_tokens":100,"prompt":"changed","schema":{"type":"object"}}',9000);
  raise exception 'Changed request reused an existing call slot';
 exception when unique_violation then null; end;
 perform pg_temp.expect((select count(*)=2 from public.wm_model_calls where space_id=s and job_id=job->>'id'),
  'replay creates no additional call record');
end; $$;

do $$
declare definition text:=pg_get_functiondef('public.wm_reserve_call(uuid,text,uuid,integer,text,bigint)'::regprocedure);
begin
 perform pg_temp.expect(position('r.request_json is distinct from p_request_json' in definition)>0,
  'existing call identity includes exact request text');
 perform pg_temp.expect(position('r.request_hash!=h' in definition)>0,
  'existing call identity retains request hash');
 perform pg_temp.expect(position('r.reserved_micro_usd!=p_reserved_micro_usd' in definition)=0,
  'recomputed estimate is not replay identity');
end $$;
reset role;
rollback;
