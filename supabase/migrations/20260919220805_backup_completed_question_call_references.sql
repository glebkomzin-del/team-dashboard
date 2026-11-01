-- Full completed question-provider receipts can dominate the short backup
-- snapshot transaction. Pin only an unredacted, immutable identity there and
-- hydrate its bodies sequentially in wm_backup_page. Pending and redacted
-- receipts remain complete snapshot records: a raw hash reference must never
-- be used after sanitization.
create or replace function public.wm_backup_completed_call_hydrate(p_space_id uuid,p_ref jsonb)
returns text language plpgsql stable security invoker set search_path='' as $$
declare body text; ref_call_index integer;
begin
 if p_ref is null or jsonb_typeof(p_ref)!='object'
   or not (p_ref ?& array['space_id','__completed_call_ref','job_id','call_index','request_hash','response_hash'])
   or (p_ref-array['space_id','__completed_call_ref','job_id','call_index','request_hash','response_hash'])!='{}'::jsonb
   or p_ref->>'__completed_call_ref' is distinct from 'v1'
   or p_ref->>'space_id' is distinct from p_space_id::text
   or coalesce(p_ref->>'job_id','') !~ '^[0-9a-f]{64}$'
   or jsonb_typeof(p_ref->'call_index') is distinct from 'number'
   or coalesce(p_ref->>'call_index','') !~ '^[0-9]+$'
   or coalesce(p_ref->>'request_hash','') !~ '^[0-9a-f]{64}$'
   or coalesce(p_ref->>'response_hash','') !~ '^[0-9a-f]{64}$' then
  raise exception 'Invalid completed call backup reference' using errcode='22023';
 end if;
 begin ref_call_index:=(p_ref->>'call_index')::integer;
 exception when numeric_value_out_of_range then raise exception 'Invalid completed call backup reference' using errcode='22023'; end;
 select to_jsonb(c)::text into body from public.wm_model_calls c
 where c.space_id=p_space_id and c.job_id=p_ref->>'job_id' and c.call_index=ref_call_index
   and c.redaction_id is null and c.request_json is not null and c.response_json is not null
   and c.request_hash=p_ref->>'request_hash' and c.response_hash=p_ref->>'response_hash'
   and encode(extensions.digest(convert_to(c.request_json,'UTF8'),'sha256'),'hex')=p_ref->>'request_hash'
   and encode(extensions.digest(convert_to(c.response_json,'UTF8'),'sha256'),'hex')=p_ref->>'response_hash';
 if body is null then raise exception 'Pinned completed call is unavailable or changed' using errcode='22023'; end if;
 return body;
end; $$;

create function public.wm_backup_completed_question_call_hydrate(p_space_id uuid,p_ref jsonb)
returns text language plpgsql stable security invoker set search_path='' as $$
declare body text; ref_call_index integer;
begin
 if p_ref is null or jsonb_typeof(p_ref)!='object'
   or not (p_ref ?& array['space_id','__completed_question_call_ref','question_id','call_index','request_hash','response_hash'])
   or (p_ref-array['space_id','__completed_question_call_ref','question_id','call_index','request_hash','response_hash'])!='{}'::jsonb
   or p_ref->>'__completed_question_call_ref' is distinct from 'v1'
   or p_ref->>'space_id' is distinct from p_space_id::text
   or coalesce(p_ref->>'question_id','') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
   or jsonb_typeof(p_ref->'call_index') is distinct from 'number'
   or coalesce(p_ref->>'call_index','') !~ '^[0-9]+$'
   or coalesce(p_ref->>'request_hash','') !~ '^[0-9a-f]{64}$'
   or coalesce(p_ref->>'response_hash','') !~ '^[0-9a-f]{64}$' then
  raise exception 'Invalid completed question call backup reference' using errcode='22023';
 end if;
 begin ref_call_index:=(p_ref->>'call_index')::integer;
 exception when numeric_value_out_of_range then raise exception 'Invalid completed question call backup reference' using errcode='22023'; end;
 select to_jsonb(c)::text into body from public.wm_question_calls c
 where c.space_id=p_space_id and c.question_id=(p_ref->>'question_id')::uuid and c.call_index=ref_call_index
   and c.redaction_id is null and c.request_json is not null and c.response_json is not null
   and c.request_hash=p_ref->>'request_hash' and c.response_hash=p_ref->>'response_hash'
   and encode(extensions.digest(convert_to(c.request_json,'UTF8'),'sha256'),'hex')=p_ref->>'request_hash'
   and encode(extensions.digest(convert_to(c.response_json,'UTF8'),'sha256'),'hex')=p_ref->>'response_hash';
 if body is null then raise exception 'Pinned completed question call is unavailable or changed' using errcode='22023'; end if;
 return body;
end; $$;
revoke all on function public.wm_backup_completed_question_call_hydrate(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.wm_backup_completed_question_call_hydrate(uuid,jsonb) to service_role;

do $$ declare definition text; begin
 select pg_get_functiondef('public.wm_receive_call(uuid,text,uuid,integer,text,bigint)'::regprocedure) into definition;
 if position('if r.response_json is not null then' in definition)=0 or position('r.response_hash!=h' in definition)=0 then
  raise exception 'Completed model calls are not immutable through wm_receive_call'; end if;
 select pg_get_functiondef('public.wm_question_receive(uuid,uuid,uuid,integer,text,bigint)'::regprocedure) into definition;
 if position('if r.response_json is not null then' in definition)=0 or position('r.response_hash!=h' in definition)=0 then
  raise exception 'Completed question calls are not immutable through wm_question_receive'; end if;

 select pg_get_functiondef('public.wm_backup_begin(uuid,uuid)'::regprocedure) into definition;
 if position('case when c.response_json is null then to_jsonb(c)::text else' in definition)=0
    or position('union all select ''question_call'',to_jsonb(qc)::text from public.wm_question_calls qc where qc.space_id=p_space_id' in definition)=0 then
  raise exception 'Unexpected backup function: completed call branches missing'; end if;
 definition:=replace(definition,
  'case when c.response_json is null then to_jsonb(c)::text else',
  'case when c.response_json is null or c.redaction_id is not null then to_jsonb(c)::text else');
 definition:=replace(definition,
  'union all select ''question_call'',to_jsonb(qc)::text from public.wm_question_calls qc where qc.space_id=p_space_id',
  $branch$union all select 'question_call',case when qc.response_json is null or qc.redaction_id is not null then to_jsonb(qc)::text else
   jsonb_build_object('space_id',qc.space_id,'__completed_question_call_ref','v1','question_id',qc.question_id,
    'call_index',qc.call_index,'request_hash',qc.request_hash,'response_hash',qc.response_hash)::text end
   from public.wm_question_calls qc where qc.space_id=p_space_id$branch$);
 execute definition;
end $$;

create or replace function public.wm_backup_page(
 p_space_id uuid,p_snapshot_id uuid,p_after bigint
)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare candidate record; hydrated text; item jsonb; page jsonb:='[]'::jsonb; prospective jsonb;
 count integer:=0; wire_bytes bigint;
begin
 if p_after is null or p_after<0 or not exists(select 1 from public.wm_backup_snapshots where id=p_snapshot_id and space_id=p_space_id) then
  raise exception 'Snapshot unavailable' using errcode='22023'; end if;
 for candidate in select sequence,kind,record_json from public.wm_backup_records
  where snapshot_id=p_snapshot_id and sequence>p_after order by sequence limit 32 loop
  hydrated:=case
   when candidate.kind='search_document' and candidate.record_json::jsonb ? '__search_document_ref' then
    (select (to_jsonb(d)-'fts')::text from public.wm_search_documents d where d.space_id=p_space_id and d.id=candidate.record_json::jsonb->>'__search_document_ref')
   when candidate.kind='search_result' and candidate.record_json::jsonb ? '__search_result_ref' then
    (select to_jsonb(r)::text from public.wm_search_results r where r.space_id=p_space_id and r.snapshot_id=candidate.record_json::jsonb->>'snapshot_id' and r.query_hash=candidate.record_json::jsonb->>'__search_result_ref')
   when candidate.kind='search_snapshot' and candidate.record_json::jsonb ? '__search_snapshot_ref' then
    (select to_jsonb(ss)::text from public.wm_search_snapshots ss where ss.space_id=p_space_id and ss.id=candidate.record_json::jsonb->>'__search_snapshot_ref')
   when candidate.kind='call' and candidate.record_json::jsonb->>'__completed_call_ref'='v1' then
    public.wm_backup_completed_call_hydrate(p_space_id,candidate.record_json::jsonb)
   when candidate.kind='question_call' and candidate.record_json::jsonb->>'__completed_question_call_ref'='v1' then
    public.wm_backup_completed_question_call_hydrate(p_space_id,candidate.record_json::jsonb)
   else candidate.record_json
  end;
  if hydrated is null then raise exception 'Pinned backup record is unavailable or changed' using errcode='22023'; end if;
  item:=jsonb_build_object('sequence',candidate.sequence,'kind',candidate.kind,'record_json',hydrated,
   'record_hash',encode(extensions.digest(convert_to(hydrated,'UTF8'),'sha256'),'hex'));
  prospective:=page||jsonb_build_array(item);wire_bytes:=octet_length(prospective::text);
  if octet_length(jsonb_build_array(item)::text)>3500000 then raise exception 'Backup record exceeds transport limit' using errcode='22023'; end if;
  if count>0 and wire_bytes>=1000000 then exit; end if;
  page:=prospective;count:=count+1;
  if wire_bytes>=1000000 then exit; end if;
 end loop;
 return page;
end $$;
