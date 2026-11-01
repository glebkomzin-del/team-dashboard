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
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Synthetic backup');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
values('66666666-6666-4666-8666-666666666666',true,'2026-09-07','fixture',1000000);
set local role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; snapshot uuid:=gen_random_uuid();
 d text; j jsonb; b jsonb; rows jsonb; row jsonb; cursor bigint:=0; count integer:=0; lease uuid:=gen_random_uuid();
begin
 d:=pg_temp.doc(s,'synthetic:backup','2026-09-07','Alice: Original retained.');
 j:=public.wm_enqueue(s,d,'fixture');j:=public.wm_claim_job(s,'fixture',lease);
 perform public.wm_reserve_call(s,j->>'id',lease,0,'{"model":"synthetic","prompt":"Full original with Unicode: ä and 🧾"}',500000);
 b:=public.wm_backup_begin(s,snapshot);
 perform pg_temp.expect((b->>'record_count')::integer=3,'config job and call snapshotted');
 perform pg_temp.expect((b->>'archive_revision')::integer=1 and (b->>'revision')::integer=0,'immutable archives and journal pinned');
 perform public.wm_receive_call(s,j->>'id',lease,0,'{"content":["Complete response"]}',100000);
 perform pg_temp.expect(public.wm_backup_begin(s,snapshot)->>'record_count'=b->>'record_count','same snapshot identity reused');
 loop
  rows:=public.wm_backup_page(s,snapshot,cursor);exit when jsonb_array_length(rows)=0;
  perform pg_temp.expect(jsonb_array_length(rows) between 1 and 32,'bounded nonempty page');
  for row in select value from jsonb_array_elements(rows) loop
   perform pg_temp.expect((row->>'sequence')::bigint>cursor,'page cursor advances');
   cursor:=(row->>'sequence')::bigint;count:=count+1;
   perform pg_temp.expect(row->>'record_hash'=encode(extensions.digest(convert_to(row->>'record_json','UTF8'),'sha256'),'hex'),'exact serialized record checksum');
   if row->>'kind'='call' then
    perform pg_temp.expect((row->>'record_json')::jsonb->>'response_json' is null,'later receipt cannot change pinned backup');
    perform pg_temp.expect(position('ä and 🧾' in row->>'record_json')>0,'full Unicode request retained');
   end if;
  end loop;
 end loop;
 perform pg_temp.expect(count=3,'complete snapshot pages');
 begin
  perform public.wm_backup_page('66666666-6666-4666-8666-666666666667',snapshot,0);
  raise exception 'Cross-space snapshot read';
 exception when invalid_parameter_value then null; end;
 perform pg_temp.expect((public.wm_backup_release(s,snapshot)->>'released')::boolean,'temporary snapshot released');
 perform pg_temp.expect((select count(*)=0 from public.wm_backup_records where snapshot_id=snapshot),'temporary records removed');
 perform pg_temp.expect((select count(*)=1 from public.wm_jobs where space_id=s),'source queue retained');
 perform pg_temp.expect((select response_json is not null from public.wm_model_calls where space_id=s),'received answer retained');
end; $$;
reset role;
set local role authenticated;
do $$ begin
 begin
  perform public.wm_backup_begin('66666666-6666-4666-8666-666666666666',gen_random_uuid());
  raise exception 'Browser can make internal backup snapshots';
 exception when insufficient_privilege then null; end;
 begin
  perform 1 from public.wm_backup_records;
  raise exception 'Browser can read internal backup records';
 exception when insufficient_privilege then null; end;
end; $$;
reset role;
rollback;
