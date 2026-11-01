begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid,source text,day date,body text) returns text language plpgsql as $$
declare metadata text; hash text; identifier text;
begin
 hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 metadata:=jsonb_build_object('source_id',source,'event_date',day,'title','Call reference fixture',
  'body_sha256',hash,'export_sha256',hash,'body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to(source||':'||metadata,'UTF8'),'sha256'),'hex');
 perform public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source,'event_date',day::text,
  'observed_at','2026-09-19T12:00:00Z','title','Call reference fixture','body_hash',hash,'export_hash',hash,
  'body',body,'export',body,'metadata_json',metadata));
 return identifier;
end; $$;
insert into auth.users(id) values('55555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label)
values('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Completed call refs');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
values('66666666-6666-4666-8666-666666666666',true,'2026-09-19','fixture',1000000);
set local role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; snapshot uuid:=gen_random_uuid();
 document text; job jsonb; lease uuid:=gen_random_uuid(); boundary jsonb; rows jsonb;
 completed_ref jsonb; pending_copy jsonb; hydrated jsonb; repeated jsonb;
begin
 document:=pg_temp.doc(s,'synthetic:completed-call-ref','2026-09-19','Gleb: Backup call fixture.');
 job:=public.wm_enqueue(s,document,'fixture');job:=public.wm_claim_job(s,'fixture',lease);
 perform public.wm_reserve_call(s,job->>'id',lease,0,'{"model":"fixture","prompt":"completed large request"}',400000);
 perform public.wm_receive_call(s,job->>'id',lease,0,'{"content":["completed large response"]}',100000);
 repeated:=public.wm_receive_call(s,job->>'id',lease,0,'{"content":["completed large response"]}',100000);
 perform pg_temp.expect((repeated->>'repeated')::boolean,'identical completed receipt is idempotent');
 begin
  perform public.wm_receive_call(s,job->>'id',lease,0,'{"content":["changed response"]}',100000);
  raise exception 'Changed completed response accepted';
 exception when unique_violation then null; end;
 begin
  perform public.wm_receive_call(s,job->>'id',lease,0,'{"content":["completed large response"]}',100001);
  raise exception 'Changed completed cost accepted';
 exception when unique_violation then null; end;
 perform public.wm_reserve_call(s,job->>'id',lease,1,'{"model":"fixture","prompt":"pending request at boundary"}',300000);

 boundary:=public.wm_backup_begin(s,snapshot);
 select record_json::jsonb into completed_ref from public.wm_backup_records
  where snapshot_id=snapshot and kind='call' and (record_json::jsonb->>'call_index')::integer=0;
 select record_json::jsonb into pending_copy from public.wm_backup_records
  where snapshot_id=snapshot and kind='call' and (record_json::jsonb->>'call_index')::integer=1;
 perform pg_temp.expect(completed_ref->>'__completed_call_ref'='v1'
  and completed_ref ?& array['space_id','__completed_call_ref','job_id','call_index','request_hash','response_hash']
  and (completed_ref-array['space_id','__completed_call_ref','job_id','call_index','request_hash','response_hash'])='{}'::jsonb,
  'completed call stored as compact versioned reference');
 perform pg_temp.expect(not completed_ref ? 'request_json' and not completed_ref ? 'response_json',
  'completed boundary record excludes large bodies');
 perform pg_temp.expect(pending_copy ? 'request_json' and pending_copy ? 'response_json'
  and pending_copy->'response_json'='null'::jsonb,'pending call copied in full');

 perform public.wm_receive_call(s,job->>'id',lease,1,'{"content":["response received after boundary"]}',90000);
 rows:=public.wm_backup_page(s,snapshot,0);
 select (value->>'record_json')::jsonb into hydrated from jsonb_array_elements(rows) value
  where value->>'kind'='call' and ((value->>'record_json')::jsonb->>'call_index')::integer=0;
 perform pg_temp.expect(hydrated->>'request_json'='{"model":"fixture","prompt":"completed large request"}'
  and hydrated->>'response_json'='{"content":["completed large response"]}',
  'completed call hydrates exact request and response');
 select (value->>'record_json')::jsonb into hydrated from jsonb_array_elements(rows) value
  where value->>'kind'='call' and ((value->>'record_json')::jsonb->>'call_index')::integer=1;
 perform pg_temp.expect(hydrated->'response_json'='null'::jsonb,'pending call keeps the snapshot boundary despite later receipt');
 perform pg_temp.expect(not exists(select 1 from jsonb_array_elements(rows) value
  where value->>'record_hash'!=encode(extensions.digest(convert_to(value->>'record_json','UTF8'),'sha256'),'hex')),
  'export hashes cover hydrated records');

 begin
  update public.wm_model_calls set response_hash=repeat('0',64)
   where space_id=s and job_id=job->>'id' and call_index=0;
  perform public.wm_backup_page(s,snapshot,0);
  raise exception 'Changed completed call hydrated';
 exception when invalid_parameter_value then null; end;
 begin
  update public.wm_model_calls set response_json='{"content":["tampered without matching hash"]}'
   where space_id=s and job_id=job->>'id' and call_index=0;
  perform public.wm_backup_page(s,snapshot,0);
  raise exception 'Completed call body with stale hash hydrated';
 exception when invalid_parameter_value then null; end;
 perform pg_temp.expect((public.wm_backup_release(s,snapshot)->>'released')::boolean,'snapshot released');
end; $$;
reset role;
rollback;
