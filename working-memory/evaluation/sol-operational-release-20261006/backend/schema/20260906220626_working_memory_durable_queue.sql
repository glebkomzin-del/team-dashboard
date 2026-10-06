-- Additive future-source queue. Disabled until a reviewed cutover configures it.
-- Original documents and old notes remain independent of model processing.
create table public.wm_processing_config (
  space_id uuid primary key references public.wm_spaces(id),
  enabled boolean not null default false,
  automatic_from date,
  pipeline text,
  budget_micro_usd bigint not null default 0 check(budget_micro_usd>=0),
  check(not enabled or (automatic_from is not null and pipeline is not null and length(pipeline)>0 and budget_micro_usd>0))
);
create table public.wm_jobs (
  space_id uuid not null references public.wm_spaces(id),
  id text not null check(id ~ '^[0-9a-f]{64}$'),
  document_id text not null,
  source_id text not null,
  event_date date not null,
  pipeline text not null,
  state text not null default 'queued' check(state in ('queued','running','prepared','applied','review')),
  reason text,
  expected_revision bigint,
  lease_token uuid,
  lease_until timestamptz,
  attempts integer not null default 0 check(attempts between 0 and 3),
  command_id uuid not null default gen_random_uuid(),
  prepared_payload jsonb,
  applied_revision bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key(space_id,id),
  foreign key(space_id,document_id) references public.wm_archive_documents(space_id,id),
  unique(space_id,command_id)
);
create index wm_jobs_chronology on public.wm_jobs(space_id,event_date,created_at,id) where state!='applied';
create index wm_jobs_document on public.wm_jobs(space_id,document_id);
create table public.wm_model_calls (
  space_id uuid not null,
  job_id text not null,
  call_index integer not null check(call_index between 0 and 15),
  request_json text not null check(jsonb_typeof(request_json::jsonb)='object'),
  request_hash text not null check(request_hash ~ '^[0-9a-f]{64}$'),
  reserved_micro_usd bigint not null check(reserved_micro_usd>0),
  actual_micro_usd bigint check(actual_micro_usd>=0),
  response_json text check(jsonb_typeof(response_json::jsonb)='object'),
  response_hash text check(response_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  received_at timestamptz,
  primary key(space_id,job_id,call_index),
  foreign key(space_id,job_id) references public.wm_jobs(space_id,id),
  check((response_json is null and response_hash is null and received_at is null and actual_micro_usd is null)
     or (response_json is not null and response_hash is not null and received_at is not null))
);
alter table public.wm_processing_config enable row level security;
alter table public.wm_jobs enable row level security;
alter table public.wm_model_calls enable row level security;
revoke all on public.wm_processing_config,public.wm_jobs,public.wm_model_calls from public,anon,authenticated,service_role;
grant select on public.wm_processing_config,public.wm_jobs,public.wm_model_calls to authenticated,service_role;
-- No runtime configuration grant: enabling processing or increasing a budget
-- is an explicit operational action, never a capability of the model/worker.
grant insert,update on public.wm_jobs,public.wm_model_calls to service_role;
create policy wm_config_owner_read on public.wm_processing_config for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_jobs_owner_read on public.wm_jobs for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_calls_owner_read on public.wm_model_calls for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));

create function public.wm_enqueue(p_space_id uuid,p_document_id text,p_pipeline text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare
 s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype;
 d public.wm_archive_documents%rowtype; j public.wm_jobs%rowtype;
 identifier text; why text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
 select * into d from public.wm_archive_documents where space_id=p_space_id and id=p_document_id;
 if not found then raise exception 'Original must be archived first' using errcode='22023'; end if;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if not found or c.automatic_from is null or d.event_date<c.automatic_from then
   return jsonb_build_object('state','archive_only','reason','historical_source_requires_direct_review');
 end if;
 if p_pipeline is null or p_pipeline is distinct from c.pipeline then raise exception 'Pipeline mismatch' using errcode='22023'; end if;
 identifier:=encode(extensions.digest(convert_to(d.source_id||':'||d.body_hash,'UTF8'),'sha256'),'hex');
 select * into j from public.wm_jobs where space_id=p_space_id and id=identifier;
 if found then return to_jsonb(j)||jsonb_build_object('repeated',true); end if;
 if exists(select 1 from public.wm_source_versions where space_id=p_space_id and id=identifier) then
   return jsonb_build_object('state','applied','repeated',true,'id',identifier);
 end if;
 if exists(select 1 from public.wm_archive_documents where space_id=p_space_id and source_id=d.source_id and body_hash!=d.body_hash)
   or exists(select 1 from public.wm_source_versions where space_id=p_space_id and source_id=d.source_id) then
   why:='changed_source_requires_review';
 elsif exists(select 1 from public.wm_source_versions where space_id=p_space_id and event_date>d.event_date)
   or exists(select 1 from public.wm_jobs where space_id=p_space_id and state in ('running','prepared') and event_date>d.event_date) then
   why:='late_source_requires_review';
 end if;
 insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state,reason)
 values(p_space_id,identifier,d.id,d.source_id,d.event_date,p_pipeline,case when why is null then 'queued' else 'review' end,why)
 returning * into j;
 return to_jsonb(j)||jsonb_build_object('repeated',false);
end; $$;

create function public.wm_claim_job(p_space_id uuid,p_pipeline text,p_lease_token uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype; j public.wm_jobs%rowtype;
begin
 if p_lease_token is null then raise exception 'Lease token required' using errcode='22023'; end if;
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if not found or not c.enabled then return jsonb_build_object('state','disabled'); end if;
 if p_pipeline is distinct from c.pipeline then return jsonb_build_object('state','paused','reason','pipeline_changed'); end if;
 select * into j from public.wm_jobs where space_id=p_space_id and state!='applied'
 order by event_date,created_at,id limit 1 for update;
 if not found then return jsonb_build_object('state','idle'); end if;
 if j.state='review' then return jsonb_build_object('state','paused','reason',j.reason,'job_id',j.id); end if;
 if j.pipeline is distinct from c.pipeline or j.event_date<c.automatic_from then
   return jsonb_build_object('state','paused','reason','job_policy_changed','job_id',j.id);
 end if;
 if j.lease_until>clock_timestamp() then
   if j.lease_token=p_lease_token then return to_jsonb(j); end if;
   return jsonb_build_object('state','waiting','reason','earlier_job_leased','job_id',j.id);
 end if;
 if exists(select 1 from public.wm_model_calls where space_id=p_space_id and job_id=j.id and response_json is null) then
   update public.wm_jobs set state='review',reason='provider_outcome_unknown',updated_at=now() where space_id=p_space_id and id=j.id;
   return jsonb_build_object('state','paused','reason','provider_outcome_unknown','job_id',j.id);
 end if;
 if j.attempts>=3 then return jsonb_build_object('state','paused','reason','attempt_limit','job_id',j.id); end if;
 if j.expected_revision is not null and j.expected_revision!=s.revision then
   update public.wm_jobs set state='review',reason='context_changed',updated_at=now() where space_id=p_space_id and id=j.id;
   return jsonb_build_object('state','paused','reason','context_changed','job_id',j.id);
 end if;
 update public.wm_jobs set state=case when prepared_payload is null then 'running' else 'prepared' end,
   expected_revision=coalesce(expected_revision,s.revision),lease_token=p_lease_token,
   lease_until=clock_timestamp()+interval '10 minutes',attempts=attempts+1,updated_at=now()
 where space_id=p_space_id and id=j.id returning * into j;
 return to_jsonb(j);
end; $$;

create function public.wm_reserve_call(p_space_id uuid,p_job_id text,p_lease_token uuid,
 p_call_index integer,p_request_json text,p_reserved_micro_usd bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
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
 if p_call_index is null or p_call_index<0 or p_call_index>15 or p_request_json is null
   or jsonb_typeof(p_request_json::jsonb)!='object' or p_reserved_micro_usd is null or p_reserved_micro_usd<=0 then
   raise exception 'Invalid call reservation' using errcode='22023';
 end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into r from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and call_index=p_call_index;
 if found then
   if r.request_hash!=h or r.reserved_micro_usd!=p_reserved_micro_usd then raise exception 'Call identity changed' using errcode='23505'; end if;
   -- A replay may consume an existing response, but must never send an unresolved call twice.
   return to_jsonb(r)||jsonb_build_object('send',false);
 end if;
 if p_call_index!=(select count(*) from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id)
   or exists(select 1 from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and response_json is null) then
   raise exception 'Previous call unresolved or missing' using errcode='22023';
 end if;
 select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) into total from public.wm_model_calls where space_id=p_space_id;
 if total+p_reserved_micro_usd>c.budget_micro_usd then
   return jsonb_build_object('send',false,'state','budget_exceeded','accounted_micro_usd',total);
 end if;
 insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd)
 values(p_space_id,p_job_id,p_call_index,p_request_json,h,p_reserved_micro_usd) returning * into r;
 update public.wm_jobs set lease_until=clock_timestamp()+interval '10 minutes',updated_at=now() where space_id=p_space_id and id=p_job_id;
 return to_jsonb(r)||jsonb_build_object('send',true);
end; $$;

create function public.wm_receive_call(p_space_id uuid,p_job_id text,p_lease_token uuid,
 p_call_index integer,p_response_json text,p_actual_micro_usd bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare j public.wm_jobs%rowtype; r public.wm_model_calls%rowtype; h text;
begin
 perform 1 from public.wm_spaces where id=p_space_id for update;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 -- A late response may settle an expired lease if no other worker owns it.
 if not found or j.lease_token is distinct from p_lease_token then raise exception 'Lease ownership changed' using errcode='40001'; end if;
 if p_response_json is null or jsonb_typeof(p_response_json::jsonb)!='object' or p_actual_micro_usd<0 then
   raise exception 'Invalid response receipt' using errcode='22023'; end if;
 select * into r from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and call_index=p_call_index for update;
 if not found then raise exception 'Call was not reserved' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_response_json,'UTF8'),'sha256'),'hex');
 if r.response_json is not null then
   if r.response_hash!=h or r.actual_micro_usd is distinct from p_actual_micro_usd then raise exception 'Response identity changed' using errcode='23505'; end if;
   return jsonb_build_object('saved',true,'repeated',true);
 end if;
 update public.wm_model_calls set response_json=p_response_json,response_hash=h,actual_micro_usd=p_actual_micro_usd,received_at=now()
 where space_id=p_space_id and job_id=p_job_id and call_index=p_call_index;
 if p_actual_micro_usd>r.reserved_micro_usd then
   update public.wm_jobs set state='review',reason='provider_usage_exceeded_reservation',updated_at=now() where space_id=p_space_id and id=p_job_id;
 end if;
 return jsonb_build_object('saved',true,'repeated',false);
end; $$;

create function public.wm_prepare_job(p_space_id uuid,p_job_id text,p_lease_token uuid,p_payload jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare j public.wm_jobs%rowtype;
begin
 perform 1 from public.wm_spaces where id=p_space_id for update;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 if not found or j.lease_token is distinct from p_lease_token or j.lease_until<=clock_timestamp() or j.state not in ('running','prepared') then
   raise exception 'Invalid job lease' using errcode='40001'; end if;
 if p_payload is null or p_payload->>'format' is distinct from 'wm-source-batch-v1'
   or p_payload->>'pipeline' is distinct from j.pipeline or coalesce(p_payload->>'result_sha256','') !~ '^[0-9a-f]{64}$'
   or exists(select 1 from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and response_json is null) then
   raise exception 'Incomplete prepared result' using errcode='22023'; end if;
 if j.prepared_payload is not null and j.prepared_payload is distinct from p_payload then raise exception 'Prepared result changed' using errcode='23505'; end if;
 update public.wm_jobs set state='prepared',prepared_payload=p_payload,updated_at=now() where space_id=p_space_id and id=p_job_id;
 return jsonb_build_object('saved',true);
end; $$;

create function public.wm_publish_job(p_space_id uuid,p_job_id text,p_lease_token uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype;
 j public.wm_jobs%rowtype; d public.wm_archive_documents%rowtype; result jsonb;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 if not found then raise exception 'Job unavailable' using errcode='22023'; end if;
 if j.state='applied' then return jsonb_build_object('state','applied','revision',j.applied_revision,'repeated',true); end if;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if not found or not c.enabled or s.state='retired' then raise exception 'Processing disabled' using errcode='22023'; end if;
 if j.state!='prepared' or j.lease_token is distinct from p_lease_token or j.lease_until<=clock_timestamp()
   or j.pipeline is distinct from c.pipeline or j.event_date<c.automatic_from then
   raise exception 'Invalid prepared job lease' using errcode='40001'; end if;
 if s.revision!=j.expected_revision
   or exists(select 1 from public.wm_jobs where space_id=p_space_id and state!='applied' and event_date<j.event_date)
   or exists(select 1 from public.wm_jobs where space_id=p_space_id and state='review' and source_id=j.source_id) then
   update public.wm_jobs set state='review',reason='context_changed',updated_at=now() where space_id=p_space_id and id=p_job_id;
   return jsonb_build_object('state','review','reason','context_changed');
 end if;
 select * into d from public.wm_archive_documents where space_id=p_space_id and id=j.document_id;
 if j.prepared_payload ? 'archive_note' then
   if j.prepared_payload->'archive_note'->>'document_id' is distinct from d.id
     or j.prepared_payload->'archive_note'->>'origin' is distinct from 'source_summary'
     or j.prepared_payload->'archive_note'->>'origin_id' is distinct from j.id then
     raise exception 'Prepared summary source mismatch' using errcode='22023';
   end if;
   perform public.wm_archive_note_put(p_space_id,j.prepared_payload->'archive_note');
 end if;
 result:=public.wm_append(p_space_id,j.expected_revision,j.command_id,'source',j.prepared_payload,
   jsonb_build_object('id',j.id,'source_id',d.source_id,'content_hash',d.body_hash,'event_date',d.event_date,
     'title',d.title,'transcript',d.body,'observed_at',d.observed_at),null);
 update public.wm_jobs set state='applied',applied_revision=(result->>'revision')::bigint,updated_at=now()
 where space_id=p_space_id and id=p_job_id;
 return result||jsonb_build_object('state','applied');
end; $$;

create function public.wm_pause_job(p_space_id uuid,p_job_id text,p_lease_token uuid,p_reason text)
returns jsonb language plpgsql security invoker set search_path='' as $$
begin
 if p_reason is null or p_reason not in ('validation_failed','budget_exceeded','provider_outcome_unknown','transport_failed','context_changed','pipeline_changed') then
   raise exception 'Invalid operational reason' using errcode='22023'; end if;
 perform 1 from public.wm_spaces where id=p_space_id for update;
 update public.wm_jobs set state='review',reason=p_reason,updated_at=now()
 where space_id=p_space_id and id=p_job_id and lease_token=p_lease_token and state in ('running','prepared');
 return jsonb_build_object('paused',found);
end; $$;

revoke all on function public.wm_enqueue(uuid,text,text),public.wm_claim_job(uuid,text,uuid),
 public.wm_reserve_call(uuid,text,uuid,integer,text,bigint),public.wm_receive_call(uuid,text,uuid,integer,text,bigint),
 public.wm_prepare_job(uuid,text,uuid,jsonb),public.wm_publish_job(uuid,text,uuid),public.wm_pause_job(uuid,text,uuid,text)
 from public,anon,authenticated;
grant execute on function public.wm_enqueue(uuid,text,text),public.wm_claim_job(uuid,text,uuid),
 public.wm_reserve_call(uuid,text,uuid,integer,text,bigint),public.wm_receive_call(uuid,text,uuid,integer,text,bigint),
 public.wm_prepare_job(uuid,text,uuid,jsonb),public.wm_publish_job(uuid,text,uuid),public.wm_pause_job(uuid,text,uuid,text)
 to service_role;

create function public.wm_processing_status(p_space_id uuid)
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('config',(select to_jsonb(c) from public.wm_processing_config c where c.space_id=p_space_id),
   'accounted_micro_usd',(select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) from public.wm_model_calls where space_id=p_space_id),
   'pending_count',(select count(*) from public.wm_jobs where space_id=p_space_id and state!='applied'),
   'jobs',coalesce((select jsonb_agg(row_to_json(j)) from (select id,document_id,source_id,event_date,state,reason,attempts,expected_revision,applied_revision,updated_at
      from public.wm_jobs where space_id=p_space_id and state!='applied' order by event_date,created_at,id limit 100) j),'[]'::jsonb));
$$;
revoke all on function public.wm_processing_status(uuid) from public,anon,authenticated;
grant execute on function public.wm_processing_status(uuid) to service_role;
