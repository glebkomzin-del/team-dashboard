begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;

insert into auth.users(id) values('95555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label)
values('96666666-6666-4666-8666-666666666666','95555555-5555-4555-8555-555555555555','Question call backup references');
set local role service_role;
do $$
declare
 s uuid:='96666666-6666-4666-8666-666666666666'; owner uuid:='95555555-5555-4555-8555-555555555555';
 q uuid:='97777777-7777-4777-8777-777777777777'; pending uuid:='98888888-8888-4888-8888-888888888888';
 redacted uuid:='99999999-9999-4999-8999-999999999999'; snapshot uuid:=gen_random_uuid(); r jsonb; ref jsonb; hydrated jsonb; call_sequence bigint;
 request text:=jsonb_build_object('model','fixture','prompt',repeat('q',800000))::text;
 response text:=jsonb_build_object('content',jsonb_build_array(repeat('r',800000)))::text;
begin
 perform public.wm_question_begin(s,q,owner,'{"question":"large settled receipt"}',0,0,0);
 perform public.wm_question_reserve(s,q,owner,0,request,100,1000);
 perform public.wm_question_receive(s,q,owner,0,response,10);
 perform public.wm_question_complete(s,q,owner,'{"answer":"settled"}');
 perform public.wm_backup_begin(s,snapshot);
 select sequence,record_json::jsonb into call_sequence,ref from public.wm_backup_records where snapshot_id=snapshot and kind='question_call';
 perform pg_temp.expect(ref->>'__completed_question_call_ref'='v1'
  and ref ?& array['space_id','__completed_question_call_ref','question_id','call_index','request_hash','response_hash']
  and (ref-array['space_id','__completed_question_call_ref','question_id','call_index','request_hash','response_hash'])='{}'::jsonb,
  'settled unredacted question call is a compact exact reference');
 select (value->>'record_json')::jsonb into hydrated from jsonb_array_elements(public.wm_backup_page(s,snapshot,call_sequence-1)) value
  where value->>'kind'='question_call';
 perform pg_temp.expect(hydrated->>'request_json'=request and hydrated->>'response_json'=response,
  'question call page hydrates the pinned full bodies');
 update public.wm_question_calls set response_hash=repeat('0',64) where space_id=s and question_id=q and call_index=0;
 begin
  perform public.wm_backup_page(s,snapshot,call_sequence-1);
  raise exception 'FAILED: changed settled question receipt hydrated';
 exception when invalid_parameter_value then null; end;
 update public.wm_question_calls set response_hash=encode(extensions.digest(convert_to(response,'UTF8'),'sha256'),'hex')
  where space_id=s and question_id=q and call_index=0;
 perform public.wm_backup_release(s,snapshot);

 perform public.wm_question_begin(s,pending,owner,'{"question":"pending"}',0,0,0);
 perform public.wm_question_reserve(s,pending,owner,0,'{"model":"fixture","pending":true}',100,1000);
 snapshot:=gen_random_uuid();perform public.wm_backup_begin(s,snapshot);
 select record_json::jsonb into ref from public.wm_backup_records
  where snapshot_id=snapshot and kind='question_call' and (record_json::jsonb->>'question_id')=pending::text;
 perform pg_temp.expect(ref->>'__completed_question_call_ref' is null and ref->>'response_json' is null,
  'pending question call remains a full snapshot record');
 perform public.wm_backup_release(s,snapshot);

 perform public.wm_question_begin(s,redacted,owner,'{"question":"sanitized"}',0,0,0);
 perform public.wm_question_reserve(s,redacted,owner,0,'{"model":"fixture","sanitized":true}',100,1000);
 perform public.wm_question_receive(s,redacted,owner,0,'{"content":["safe replacement"]}',10);
 update public.wm_question_calls set redaction_id=gen_random_uuid(),
  sanitized_request_hash=encode(extensions.digest(convert_to(request_json,'UTF8'),'sha256'),'hex'),
  sanitized_response_hash=encode(extensions.digest(convert_to(response_json,'UTF8'),'sha256'),'hex')
  where space_id=s and question_id=redacted and call_index=0;
 snapshot:=gen_random_uuid();perform public.wm_backup_begin(s,snapshot);
 select record_json::jsonb into ref from public.wm_backup_records
  where snapshot_id=snapshot and kind='question_call' and (record_json::jsonb->>'question_id')=redacted::text;
 perform pg_temp.expect(ref->>'__completed_question_call_ref' is null and ref->>'redaction_id' is not null
  and ref->>'sanitized_request_hash'=encode(extensions.digest(convert_to(ref->>'request_json','UTF8'),'sha256'),'hex')
  and ref->>'sanitized_response_hash'=encode(extensions.digest(convert_to(ref->>'response_json','UTF8'),'sha256'),'hex'),
  'sanitized receipt stays full with hashes for its replacement bodies');
 perform public.wm_backup_release(s,snapshot);
end; $$;
reset role;
rollback;
