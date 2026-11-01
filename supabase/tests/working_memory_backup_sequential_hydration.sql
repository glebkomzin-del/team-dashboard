begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid,source text,day date,body text) returns text language plpgsql as $$
declare metadata text; hash text; identifier text;
begin
 hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 metadata:=jsonb_build_object('source_id',source,'event_date',day,'title','Sequential hydration fixture',
  'body_sha256',hash,'export_sha256',hash,'body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to(source||':'||metadata,'UTF8'),'sha256'),'hex');
 perform public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source,'event_date',day::text,
  'observed_at','2026-09-19T12:00:00Z','title','Sequential hydration fixture','body_hash',hash,
  'export_hash',hash,'body',body,'export',body,'metadata_json',metadata));
 return identifier;
end; $$;
insert into auth.users(id) values('75555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label)
values('76666666-6666-4666-8666-666666666666','75555555-5555-4555-8555-555555555555','Sequential hydration');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
values('76666666-6666-4666-8666-666666666666',true,'2026-09-19','fixture',100000000);
set local role service_role;
do $$
declare
 s uuid:='76666666-6666-4666-8666-666666666666'; snapshot uuid:=gen_random_uuid();
 document text; job jsonb; lease uuid:=gen_random_uuid(); rows jsonb; hydrated jsonb;
 sequence0 bigint; sequence1 bigint; sequence2 bigint; sequence3 bigint; sequence4 bigint; original_hash text;
begin
 document:=pg_temp.doc(s,'synthetic:sequential-hydration','2026-09-19','Backup page fixture.');
 job:=public.wm_enqueue(s,document,'fixture');
 job:=public.wm_claim_job(s,'fixture',lease);
 for i in 0..2 loop
  perform public.wm_reserve_call(s,job->>'id',lease,i,
   jsonb_build_object('model','fixture','prompt',repeat(chr(97+i),600000))::text,1000000);
  perform public.wm_receive_call(s,job->>'id',lease,i,
   jsonb_build_object('content',jsonb_build_array('response-'||i))::text,1000);
 end loop;
 perform public.wm_reserve_call(s,job->>'id',lease,3,
  jsonb_build_object('model','fixture','prompt',repeat('z',3600000))::text,5000000);
 perform public.wm_receive_call(s,job->>'id',lease,3,'{"content":["oversized"]}',1000);
 perform public.wm_reserve_call(s,job->>'id',lease,4,
  jsonb_build_object('model','fixture','prompt',repeat('y',1200000))::text,2000000);
 perform public.wm_receive_call(s,job->>'id',lease,4,'{"content":["single-record page"]}',1000);
 perform public.wm_backup_begin(s,snapshot);

 select sequence into sequence0 from public.wm_backup_records where snapshot_id=snapshot and kind='call'
  and (record_json::jsonb->>'call_index')::integer=0;
 select sequence into sequence1 from public.wm_backup_records where snapshot_id=snapshot and kind='call'
  and (record_json::jsonb->>'call_index')::integer=1;
 select sequence into sequence2 from public.wm_backup_records where snapshot_id=snapshot and kind='call'
  and (record_json::jsonb->>'call_index')::integer=2;
 select sequence into sequence3 from public.wm_backup_records where snapshot_id=snapshot and kind='call'
  and (record_json::jsonb->>'call_index')::integer=3;
 select sequence into sequence4 from public.wm_backup_records where snapshot_id=snapshot and kind='call'
  and (record_json::jsonb->>'call_index')::integer=4;
 perform pg_temp.expect(sequence0<sequence1 and sequence1<sequence2 and sequence2<sequence3 and sequence3<sequence4,
  'call backup records retain call order');

 select response_hash into original_hash from public.wm_model_calls
  where space_id=s and job_id=job->>'id' and call_index=2;
 update public.wm_model_calls set response_hash=repeat('0',64)
  where space_id=s and job_id=job->>'id' and call_index=2;
 rows:=public.wm_backup_page(s,snapshot,sequence0-1);
 perform pg_temp.expect(jsonb_array_length(rows)=1
  and (rows->0->>'kind')='call'
  and ((rows->0->>'record_json')::jsonb->>'call_index')::integer=0,
  'page stops before overflow instead of hydrating all 32 candidates');
 perform pg_temp.expect(octet_length(rows::text)<1000000,'serialized page envelope stays below preferred budget');
 hydrated:=(rows->0->>'record_json')::jsonb;
 perform pg_temp.expect(rows->0->>'record_hash'=encode(
  extensions.digest(convert_to(rows->0->>'record_json','UTF8'),'sha256'),'hex'),
  'sequential hydration preserves the record checksum contract');
 begin
  perform public.wm_backup_page(s,snapshot,sequence0);
  raise exception 'Changed next completed call was skipped';
 exception when invalid_parameter_value then null; end;
 update public.wm_model_calls set response_hash=original_hash
  where space_id=s and job_id=job->>'id' and call_index=2;

 rows:=public.wm_backup_page(s,snapshot,sequence0);
 perform pg_temp.expect(jsonb_array_length(rows)=1
  and ((rows->0->>'record_json')::jsonb->>'call_index')::integer=1,
  'cursor continues with the first record excluded by the prior byte budget');
 begin
 perform public.wm_backup_page(s,snapshot,sequence3-1);
  raise exception 'Oversized single backup record crossed the hard transport limit';
 exception when invalid_parameter_value then null; end;
 rows:=public.wm_backup_page(s,snapshot,sequence4-1);
 perform pg_temp.expect(jsonb_array_length(rows)=1
  and octet_length(rows::text)>=1000000 and octet_length(rows::text)<3500000,
  'one record above the preferred page budget is returned alone below the hard limit');
end; $$;
reset role;
rollback;
