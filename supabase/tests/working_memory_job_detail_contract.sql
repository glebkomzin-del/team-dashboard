begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid,source text,day date,body text) returns text language plpgsql as $$
declare metadata text; body_hash text; identifier text;
begin
 body_hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 metadata:=jsonb_build_object('source_id',source,'event_date',day,'title','Job detail fixture',
  'body_sha256',body_hash,'export_sha256',body_hash,'body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to(source||':'||metadata,'UTF8'),'sha256'),'hex');
 perform public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source,'event_date',day::text,
  'observed_at','2026-09-20T12:00:00Z','title','Job detail fixture','body_hash',body_hash,
  'export_hash',body_hash,'body',body,'export',body,'metadata_json',metadata));
 return identifier;
end; $$;

insert into auth.users(id) values('a8111111-1111-4111-8111-111111111111');
insert into public.wm_spaces(id,owner_id,label)
 values('b8222222-2222-4222-8222-222222222222','a8111111-1111-4111-8111-111111111111','Job detail contract');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
 values('b8222222-2222-4222-8222-222222222222',true,'2026-09-20','detail-v1',1000000);

set local role service_role;
do $$
declare s uuid:='b8222222-2222-4222-8222-222222222222'; document text; job jsonb; detail jsonb;
 lease uuid:='c8333333-3333-4333-8333-333333333333'; failure uuid:='d8444444-4444-4444-8444-444444444444';
 request text:='{"model":"gpt-5.6-terra","prompt":"synthetic detail","max_tokens":100}'; expected_hash text;
begin
 document:=pg_temp.doc(s,'synthetic:job-detail','2026-09-20','Alex: Synthetic detail.');
 job:=public.wm_enqueue(s,document,'detail-v1');job:=public.wm_claim_job(s,'detail-v1',lease);
 perform public.wm_reserve_call(s,job->>'id',lease,0,request,1000);
 perform public.wm_receive_call(s,job->>'id',lease,0,'{"content":[],"usage_final":true}',800);
 perform public.wm_pause_transport_job(s,job->>'id',lease,failure,
  jsonb_build_object('at',clock_timestamp(),'op','job_detail','type','http','http_status',503,'sqlstate','57014','attempts',3));
 expected_hash:=encode(extensions.digest(convert_to(request,'UTF8'),'sha256'),'hex');
 detail:=public.wm_job_detail(s,job->>'id');
 perform pg_temp.expect(detail->'calls'->0->>'request_hash'=expected_hash,'job detail returns durable request hash');
 perform pg_temp.expect((detail->'calls'->0->>'received')::boolean,'job detail retains received flag');
 perform pg_temp.expect((detail->'calls'->0->>'reserved_micro_usd')::bigint=1000
  and (detail->'calls'->0->>'actual_micro_usd')::bigint=800,'job detail retains cost fields');
 perform pg_temp.expect(detail->'transport_failures'->0->>'failure_id'=failure::text
  and detail->'transport_failures'->0->>'op'='job_detail','job detail retains recovery diagnostics');
end; $$;

do $$
declare definition text:=pg_get_functiondef('public.wm_job_detail(uuid,text)'::regprocedure);
begin
 perform pg_temp.expect(position('''request_hash'',c.request_hash' in definition)>0,'function contract contains request_hash');
 perform pg_temp.expect(position('''transport_failures''' in definition)>0,'function contract contains transport failures');
end $$;
reset role;
rollback;
