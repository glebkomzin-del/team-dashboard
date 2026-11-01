-- Metadata-only accounting for paid calls completed outside wm_model_calls
-- during a reviewed recovery. Request and response bodies stay in their
-- original protected receipt bundle; this table stores hashes, usage and cost.
create table public.wm_generation_recovery_calls (
  space_id uuid not null,
  review_id uuid not null,
  job_id text not null,
  call_index integer not null check(call_index between 0 and 31),
  request_hash text not null check(request_hash ~ '^[0-9a-f]{64}$'),
  response_hash text not null check(response_hash ~ '^[0-9a-f]{64}$'),
  model text not null check(length(model) between 1 and 200),
  usage jsonb not null check(jsonb_typeof(usage)='object'),
  reserved_micro_usd bigint not null check(reserved_micro_usd>0),
  actual_micro_usd bigint not null check(actual_micro_usd>=0),
  provider_input_tokens bigint not null check(provider_input_tokens>=0),
  review_sha256 text not null check(review_sha256 ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz not null default clock_timestamp(),
  primary key(space_id,job_id,call_index,request_hash,response_hash),
  foreign key(space_id,review_id) references public.wm_generation_reviews(space_id,id),
  foreign key(space_id,job_id) references public.wm_jobs(space_id,id)
);
create index wm_generation_recovery_calls_review on public.wm_generation_recovery_calls(space_id,review_id);
alter table public.wm_generation_recovery_calls enable row level security;
revoke all on public.wm_generation_recovery_calls from public,anon,authenticated,service_role;
grant select on public.wm_generation_recovery_calls to authenticated,service_role;
create policy wm_generation_recovery_calls_owner_read on public.wm_generation_recovery_calls for select to authenticated
  using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));

do $$
declare
  g public.wm_generation_reviews%rowtype;
  provenance jsonb;
  receipt jsonb;
  usage_block jsonb;
  central public.wm_model_calls%rowtype;
  existing public.wm_generation_recovery_calls%rowtype;
  blocks integer;
  usage_blocks integer;
  receipt_count integer;
  call_index_value integer;
  actual_value bigint;
  reserved_value bigint;
  input_value bigint;
  declared_total bigint;
  receipt_total bigint;
  seen_indices integer[];
begin
  for g in select * from public.wm_generation_reviews order by space_id,id for update loop
    if g.payload->>'review_sha256' is distinct from g.review_sha256 then
      raise exception 'Generation review hash metadata changed' using errcode='23514';
    end if;
    blocks:=0;usage_blocks:=0;receipt_count:=0;receipt_total:=0;declared_total:=null;seen_indices:=array[]::integer[];
    for usage_block in select value from jsonb_path_query(g.payload,'lax $.**.usage') as q(value) loop
      if usage_block ? 'recovery_actual_micro_usd' then
        usage_blocks:=usage_blocks+1;
        if jsonb_typeof(usage_block->'recovery_actual_micro_usd')!='number'
           or (usage_block->>'recovery_actual_micro_usd') !~ '^[0-9]+$' then
          raise exception 'Invalid generation recovery usage total' using errcode='23514';
        end if;
        declared_total:=(usage_block->>'recovery_actual_micro_usd')::bigint;
      end if;
    end loop;
    for provenance in select value from jsonb_path_query(g.payload,'lax $.**.provenance') as q(value) loop
      if provenance->>'mode'='bounded_recovery_generation' then
        blocks:=blocks+1;
        if g.job_id is null or provenance->>'job_id' is distinct from g.job_id
           or jsonb_typeof(provenance->'recovery_receipts')!='array'
           or jsonb_array_length(provenance->'recovery_receipts') not between 1 and 32 then
          raise exception 'Invalid generation recovery provenance' using errcode='23514';
        end if;
        for receipt in select value from jsonb_array_elements(provenance->'recovery_receipts') as q(value) loop
          if jsonb_typeof(receipt)!='object'
             or not(receipt ?& array['call_index','request_hash','response_hash','model','usage','reserved_micro_usd','actual_micro_usd','provider_input_tokens'])
             or jsonb_typeof(receipt->'call_index')!='number' or (receipt->>'call_index') !~ '^[0-9]+$'
             or receipt->>'request_hash' !~ '^[0-9a-f]{64}$' or receipt->>'response_hash' !~ '^[0-9a-f]{64}$'
             or coalesce(length(receipt->>'model'),0) not between 1 and 200 or jsonb_typeof(receipt->'usage')!='object'
             or jsonb_typeof(receipt->'reserved_micro_usd')!='number' or (receipt->>'reserved_micro_usd') !~ '^[1-9][0-9]*$'
             or jsonb_typeof(receipt->'actual_micro_usd')!='number' or (receipt->>'actual_micro_usd') !~ '^[0-9]+$'
             or jsonb_typeof(receipt->'provider_input_tokens')!='number' or (receipt->>'provider_input_tokens') !~ '^[0-9]+$' then
            raise exception 'Invalid generation recovery call metadata' using errcode='23514';
          end if;
          call_index_value:=(receipt->>'call_index')::integer;
          reserved_value:=(receipt->>'reserved_micro_usd')::bigint;
          actual_value:=(receipt->>'actual_micro_usd')::bigint;
          input_value:=(receipt->>'provider_input_tokens')::bigint;
          if call_index_value not between 0 and 31 or call_index_value=any(seen_indices) then
            raise exception 'Duplicate or out-of-range generation recovery call' using errcode='23514';
          end if;
          seen_indices:=array_append(seen_indices,call_index_value);
          receipt_count:=receipt_count+1;receipt_total:=receipt_total+actual_value;
          select * into central from public.wm_model_calls where space_id=g.space_id and job_id=g.job_id and call_index=call_index_value;
          if found then
            if central.request_hash is distinct from receipt->>'request_hash'
               or central.response_hash is distinct from receipt->>'response_hash'
               or central.actual_micro_usd is distinct from actual_value then
              raise exception 'Recovery metadata conflicts with a durable model call' using errcode='23514';
            end if;
            continue;
          end if;
          select * into existing from public.wm_generation_recovery_calls
            where space_id=g.space_id and job_id=g.job_id and call_index=call_index_value
              and request_hash=receipt->>'request_hash' and response_hash=receipt->>'response_hash';
          if found then
            if existing.model is distinct from receipt->>'model' or existing.usage is distinct from receipt->'usage'
               or existing.reserved_micro_usd is distinct from reserved_value or existing.actual_micro_usd is distinct from actual_value
               or existing.provider_input_tokens is distinct from input_value then
              raise exception 'Recovery call identity reused with changed accounting' using errcode='23514';
            end if;
          else
            insert into public.wm_generation_recovery_calls(space_id,review_id,job_id,call_index,request_hash,response_hash,
              model,usage,reserved_micro_usd,actual_micro_usd,provider_input_tokens,review_sha256)
            values(g.space_id,g.id,g.job_id,call_index_value,receipt->>'request_hash',receipt->>'response_hash',
              receipt->>'model',receipt->'usage',reserved_value,actual_value,input_value,g.review_sha256);
          end if;
        end loop;
      end if;
    end loop;
    if blocks>0 and (blocks!=1 or usage_blocks!=1 or receipt_count=0 or declared_total is distinct from receipt_total) then
      raise exception 'Generation recovery accounting does not reconcile' using errcode='23514';
    elsif blocks=0 and usage_blocks!=0 then
      raise exception 'Recovery usage exists without recovery provenance' using errcode='23514';
    end if;
  end loop;
end $$;

create or replace function public.wm_reserve_call(
  p_space_id uuid,p_job_id text,p_lease_token uuid,p_call_index integer,p_request_json text,p_reserved_micro_usd bigint)
returns jsonb language plpgsql set search_path to '' as $function$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype; j public.wm_jobs%rowtype;
 r public.wm_model_calls%rowtype; h text; total bigint;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if not found or not c.enabled then raise exception 'Processing disabled' using errcode='22023'; end if;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 if not found or j.state!='running' or j.lease_token is distinct from p_lease_token or j.lease_until<=clock_timestamp()
   or j.pipeline is distinct from c.pipeline or j.event_date<c.automatic_from or j.expected_revision!=s.revision then
   raise exception 'Job lease or context no longer valid' using errcode='40001';
 end if;
 if p_call_index is null or p_call_index<0 or p_call_index>31 or p_request_json is null
   or jsonb_typeof(p_request_json::jsonb)!='object' or p_reserved_micro_usd is null or p_reserved_micro_usd<=0 then
   raise exception 'Invalid call reservation' using errcode='22023';
 end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into r from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and call_index=p_call_index;
 if found then
   if r.request_hash!=h or r.reserved_micro_usd!=p_reserved_micro_usd then raise exception 'Call identity changed' using errcode='23505'; end if;
   return to_jsonb(r)||jsonb_build_object('send',false);
 end if;
 if p_call_index!=(select count(*) from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id)
   or exists(select 1 from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and response_json is null) then
   raise exception 'Previous call unresolved or missing' using errcode='22023';
 end if;
 select coalesce((select sum(coalesce(actual_micro_usd,reserved_micro_usd)) from public.wm_model_calls where space_id=p_space_id),0)
      +coalesce((select sum(x.actual_micro_usd) from public.wm_generation_recovery_calls x where x.space_id=p_space_id and not exists(
        select 1 from public.wm_model_calls m where m.space_id=x.space_id and m.job_id=x.job_id and m.call_index=x.call_index
          and m.request_hash=x.request_hash and m.response_hash=x.response_hash and m.actual_micro_usd=x.actual_micro_usd)),0) into total;
 if c.budget_micro_usd is not null and total+p_reserved_micro_usd>c.budget_micro_usd then
   return jsonb_build_object('send',false,'state','budget_exceeded','accounted_micro_usd',total);
 end if;
 insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd)
 values(p_space_id,p_job_id,p_call_index,p_request_json,h,p_reserved_micro_usd) returning * into r;
 update public.wm_jobs set lease_until=clock_timestamp()+interval '10 minutes',updated_at=now() where space_id=p_space_id and id=p_job_id;
 return to_jsonb(r)||jsonb_build_object('send',true);
end; $function$;

create or replace function public.wm_processing_status(p_space_id uuid)
returns jsonb language sql stable security invoker set search_path='' as $$
 with durable as (select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) total
   from public.wm_model_calls where space_id=p_space_id),
 recovery as (select coalesce(sum(x.actual_micro_usd),0) total from public.wm_generation_recovery_calls x
   where x.space_id=p_space_id and not exists(select 1 from public.wm_model_calls m
     where m.space_id=x.space_id and m.job_id=x.job_id and m.call_index=x.call_index
       and m.request_hash=x.request_hash and m.response_hash=x.response_hash and m.actual_micro_usd=x.actual_micro_usd))
 select jsonb_build_object('config',(select to_jsonb(c) from public.wm_processing_config c where c.space_id=p_space_id),
   'durable_call_accounted_micro_usd',durable.total,'recovery_accounted_micro_usd',recovery.total,
   'accounted_micro_usd',durable.total+recovery.total,
   'pending_count',(select count(*) from public.wm_jobs where space_id=p_space_id and state not in ('applied','archived')),
   'archived_count',(select count(*) from public.wm_jobs where space_id=p_space_id and state='archived'),
   'jobs',coalesce((select jsonb_agg(row_to_json(j)) from (select j.id,j.document_id,j.source_id,j.event_date,d.title,j.state,j.reason,j.attempts,j.expected_revision,j.applied_revision,j.updated_at,j.lease_until
      from public.wm_jobs j join public.wm_archive_documents d on d.space_id=j.space_id and d.id=j.document_id
      where j.space_id=p_space_id and j.state not in ('applied','archived') order by j.event_date,j.created_at,j.id limit 100) j),'[]'::jsonb))
 from durable,recovery;
$$;
