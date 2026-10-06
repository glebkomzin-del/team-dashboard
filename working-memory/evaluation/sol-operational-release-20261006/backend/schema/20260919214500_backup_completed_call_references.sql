-- Completed model calls are immutable through wm_receive_call.  Pin only their
-- scoped identity and request/response hashes while the snapshot lock is held;
-- hydrate the large request/response bodies later in bounded backup pages.
-- Pending calls stay copied in full because their response may still settle.
create function public.wm_backup_completed_call_hydrate(p_space_id uuid,p_ref jsonb)
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
 exception when numeric_value_out_of_range then
  raise exception 'Invalid completed call backup reference' using errcode='22023';
 end;
 select to_jsonb(c)::text into body from public.wm_model_calls c
 where c.space_id=p_space_id and c.job_id=p_ref->>'job_id' and c.call_index=ref_call_index
   and c.response_json is not null
   and c.request_hash=p_ref->>'request_hash' and c.response_hash=p_ref->>'response_hash'
   and encode(extensions.digest(convert_to(c.request_json,'UTF8'),'sha256'),'hex')=p_ref->>'request_hash'
   and encode(extensions.digest(convert_to(c.response_json,'UTF8'),'sha256'),'hex')=p_ref->>'response_hash';
 if body is null then
  raise exception 'Pinned completed call is unavailable or changed' using errcode='22023';
 end if;
 return body;
end; $$;
revoke all on function public.wm_backup_completed_call_hydrate(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.wm_backup_completed_call_hydrate(uuid,jsonb) to service_role;

do $$ declare definition text; begin
 select pg_get_functiondef('public.wm_receive_call(uuid,text,uuid,integer,text,bigint)'::regprocedure) into definition;
 if position('if r.response_json is not null then' in definition)=0
   or position('r.response_hash!=h' in definition)=0
   or position('r.actual_micro_usd is distinct from p_actual_micro_usd' in definition)=0 then
  raise exception 'Completed model calls are not immutable through wm_receive_call';
 end if;

 select pg_get_functiondef('public.wm_backup_begin(uuid,uuid)'::regprocedure) into definition;
 if position('union all select ''call'',to_jsonb(c)::text from public.wm_model_calls c where c.space_id=p_space_id' in definition)=0 then
  raise exception 'Unexpected backup function: model call branch missing';
 end if;
 execute replace(definition,
  'union all select ''call'',to_jsonb(c)::text from public.wm_model_calls c where c.space_id=p_space_id',
  'union all select ''call'',case when c.response_json is null then to_jsonb(c)::text else
    jsonb_build_object(''space_id'',c.space_id,''__completed_call_ref'',''v1'',''job_id'',c.job_id,
      ''call_index'',c.call_index,''request_hash'',c.request_hash,''response_hash'',c.response_hash)::text end
   from public.wm_model_calls c where c.space_id=p_space_id');

 select pg_get_functiondef('public.wm_backup_page(uuid,uuid,bigint)'::regprocedure) into definition;
 if position('else record_json end record_json from candidates' in definition)=0 then
  raise exception 'Unexpected backup page hydration';
 end if;
 execute replace(definition,'else record_json end record_json from candidates',
  'when kind=''call'' and record_json::jsonb->>''__completed_call_ref''=''v1'' then
    public.wm_backup_completed_call_hydrate(p_space_id,record_json::jsonb)
   else record_json end record_json from candidates');
end $$;
