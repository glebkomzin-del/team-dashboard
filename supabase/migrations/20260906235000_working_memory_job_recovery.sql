-- Explicit owner recovery. No budget changes, no discarded responses, no model calls.
alter table public.wm_jobs drop constraint wm_jobs_state_check;
alter table public.wm_jobs add constraint wm_jobs_state_check check(state in ('queued','running','prepared','applied','review','archived'));
create table public.wm_job_decisions (
 space_id uuid not null references public.wm_spaces(id), command_id uuid not null,
 job_id text not null, actor_id uuid not null references auth.users(id),
 action text not null check(action in ('retry','archive_only','rebase_prepared')),
 reason text not null check(length(trim(reason)) between 1 and 4000),
 request jsonb not null, previous_job jsonb not null, result jsonb not null,
 recorded_at timestamptz not null default now(),
 primary key(space_id,command_id), foreign key(space_id,job_id) references public.wm_jobs(space_id,id)
);
alter table public.wm_job_decisions enable row level security;
revoke all on public.wm_job_decisions from public,anon,authenticated,service_role;
grant select on public.wm_job_decisions to authenticated,service_role;
grant insert on public.wm_job_decisions to service_role;
create policy wm_job_decisions_owner_read on public.wm_job_decisions for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));

create function public.wm_job_detail(p_space_id uuid,p_job_id text)
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('job',to_jsonb(j),'title',d.title,
  'calls',coalesce((select jsonb_agg(jsonb_build_object('index',c.call_index,'received',c.response_json is not null,
    'reserved_micro_usd',c.reserved_micro_usd,'actual_micro_usd',c.actual_micro_usd) order by c.call_index)
    from public.wm_model_calls c where c.space_id=p_space_id and c.job_id=j.id),'[]'::jsonb),
  'decisions',coalesce((select jsonb_agg(jsonb_build_object('command_id',h.command_id,'action',h.action,'reason',h.reason,'recorded_at',h.recorded_at) order by h.recorded_at)
    from public.wm_job_decisions h where h.space_id=p_space_id and h.job_id=j.id),'[]'::jsonb))
 from public.wm_jobs j join public.wm_archive_documents d on d.space_id=j.space_id and d.id=j.document_id
 where j.space_id=p_space_id and j.id=p_job_id;
$$;

create function public.wm_resolve_job(p_space_id uuid,p_actor_id uuid,p_command_id uuid,p_job_id text,
 p_expected_revision bigint,p_expected_updated_at timestamptz,p_action text,p_reason text,p_payload jsonb default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; j public.wm_jobs%rowtype; c public.wm_processing_config%rowtype;
 h public.wm_job_decisions%rowtype; req jsonb; result jsonb; previous jsonb; calls integer; unknown_calls integer;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 if p_command_id is null or p_action is null or p_action not in ('retry','archive_only','rebase_prepared')
   or p_reason is null or length(trim(p_reason)) not between 1 and 4000 or p_expected_updated_at is null then
   raise exception 'Incomplete recovery decision' using errcode='22023'; end if;
 req:=jsonb_build_object('actor_id',p_actor_id,'job_id',p_job_id,'expected_revision',p_expected_revision,
   'expected_updated_at',p_expected_updated_at,'action',p_action,'reason',p_reason,'payload',p_payload);
 select * into h from public.wm_job_decisions where space_id=p_space_id and command_id=p_command_id;
 if found then
   if h.request is distinct from req then raise exception 'Decision identity changed' using errcode='23505'; end if;
   return h.result||jsonb_build_object('repeated',true);
 end if;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 if not found then raise exception 'Job unavailable' using errcode='22023'; end if;
 if p_expected_revision is distinct from s.revision or p_expected_updated_at is distinct from j.updated_at then
   raise exception 'Recovery view changed' using errcode='40001'; end if;
 if j.state in ('applied','archived','queued') or (j.state in ('running','prepared') and j.lease_until>clock_timestamp()) then
   raise exception 'Job is not available for owner recovery' using errcode='40001'; end if;
 previous:=to_jsonb(j);
 select count(*),count(*) filter(where response_json is null) into calls,unknown_calls
 from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id;
 if p_action='archive_only' then
   if p_payload is not null then raise exception 'Archive decision cannot modify a result' using errcode='22023'; end if;
   -- Preserve lease ownership so a late response can still settle its reservation.
   update public.wm_jobs set state='archived',reason='owner_archive_only',updated_at=clock_timestamp()
    where space_id=p_space_id and id=p_job_id;
 else
   select * into c from public.wm_processing_config where space_id=p_space_id;
   if not found or c.automatic_from is null or j.event_date<c.automatic_from or j.pipeline is distinct from c.pipeline
     or exists(select 1 from public.wm_source_versions where space_id=p_space_id and (source_id=j.source_id or event_date>j.event_date))
     or exists(select 1 from public.wm_archive_documents where space_id=p_space_id and source_id=j.source_id and id!=j.document_id
          and body_hash!=(select body_hash from public.wm_archive_documents where space_id=p_space_id and id=j.document_id)) then
     raise exception 'Changed, historical or late source needs explicit generation review' using errcode='22023'; end if;
   if unknown_calls>0 then raise exception 'Unknown provider outcome cannot be repeated' using errcode='22023'; end if;
   if p_action='retry' then
     if p_payload is not null then raise exception 'Retry cannot replace the saved result' using errcode='22023'; end if;
     if (calls>0 or j.prepared_payload is not null) and j.expected_revision is distinct from s.revision then
       raise exception 'Saved result needs review against the changed context' using errcode='22023'; end if;
     if j.reason='validation_failed' and j.prepared_payload is null then
       raise exception 'Invalid saved output needs explicit content review' using errcode='22023'; end if;
   else
     if j.prepared_payload is null or p_payload is null or p_payload->>'format' is distinct from 'wm-source-batch-v1'
       or p_payload->>'pipeline' is distinct from j.pipeline or coalesce(p_payload->>'result_sha256','') !~ '^[0-9a-f]{64}$'
       or p_payload->'archive_note' is distinct from j.prepared_payload->'archive_note'
       or p_payload->'provenance'->>'owner_recovery_command' is distinct from p_command_id::text
       or p_payload->'provenance'->>'owner_id' is distinct from p_actor_id::text then
       raise exception 'Incomplete reviewed saved result' using errcode='22023'; end if;
   end if;
   update public.wm_jobs set state=case when prepared_payload is null then 'queued' else 'prepared' end,
     prepared_payload=case when p_action='rebase_prepared' then p_payload else prepared_payload end,
     expected_revision=case when prepared_payload is null and calls=0 then null else s.revision end,
     reason=null,lease_token=null,lease_until=null,attempts=0,updated_at=clock_timestamp()
   where space_id=p_space_id and id=p_job_id;
 end if;
 select jsonb_build_object('job_id',id,'state',state,'updated_at',updated_at,'revision',s.revision,'repeated',false)
 into result from public.wm_jobs where space_id=p_space_id and id=p_job_id;
 insert into public.wm_job_decisions(space_id,command_id,job_id,actor_id,action,reason,request,previous_job,result)
 values(p_space_id,p_command_id,p_job_id,p_actor_id,p_action,p_reason,req,previous,result);
 return result;
end; $$;
revoke all on function public.wm_job_detail(uuid,text),public.wm_resolve_job(uuid,uuid,uuid,text,bigint,timestamptz,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.wm_job_detail(uuid,text),public.wm_resolve_job(uuid,uuid,uuid,text,bigint,timestamptz,text,text,jsonb) to service_role;

create or replace function public.wm_claim_job(p_space_id uuid,p_pipeline text,p_lease_token uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype; j public.wm_jobs%rowtype;
begin
 if p_lease_token is null then raise exception 'Lease token required' using errcode='22023'; end if;
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if not found or not c.enabled then return jsonb_build_object('state','disabled'); end if;
 if p_pipeline is distinct from c.pipeline then return jsonb_build_object('state','paused','reason','pipeline_changed'); end if;
 select * into j from public.wm_jobs where space_id=p_space_id and state not in ('applied','archived')
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
 if j.attempts>=3 then
   update public.wm_jobs set state='review',reason='attempt_limit',updated_at=clock_timestamp() where space_id=p_space_id and id=j.id;
   return jsonb_build_object('state','paused','reason','attempt_limit','job_id',j.id);
 end if;
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

create or replace function public.wm_publish_job(p_space_id uuid,p_job_id text,p_lease_token uuid)
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
   or exists(select 1 from public.wm_jobs where space_id=p_space_id and state not in ('applied','archived') and event_date<j.event_date)
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

create or replace function public.wm_receive_call(p_space_id uuid,p_job_id text,p_lease_token uuid,
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
 if p_actual_micro_usd>r.reserved_micro_usd and j.state not in ('applied','archived') then
   update public.wm_jobs set state='review',reason='provider_usage_exceeded_reservation',updated_at=now() where space_id=p_space_id and id=p_job_id;
 end if;
 return jsonb_build_object('saved',true,'repeated',false);
end; $$;

create or replace function public.wm_processing_status(p_space_id uuid)
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('config',(select to_jsonb(c) from public.wm_processing_config c where c.space_id=p_space_id),
   'accounted_micro_usd',(select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) from public.wm_model_calls where space_id=p_space_id),
   'pending_count',(select count(*) from public.wm_jobs where space_id=p_space_id and state not in ('applied','archived')),
   'archived_count',(select count(*) from public.wm_jobs where space_id=p_space_id and state='archived'),
   'jobs',coalesce((select jsonb_agg(row_to_json(j)) from (select j.id,j.document_id,j.source_id,j.event_date,d.title,j.state,j.reason,j.attempts,j.expected_revision,j.applied_revision,j.updated_at,j.lease_until
      from public.wm_jobs j join public.wm_archive_documents d on d.space_id=j.space_id and d.id=j.document_id
      where j.space_id=p_space_id and j.state not in ('applied','archived') order by j.event_date,j.created_at,j.id limit 100) j),'[]'::jsonb));
$$;

drop index public.wm_jobs_chronology;
create index wm_jobs_chronology on public.wm_jobs(space_id,event_date,created_at,id) where state not in ('applied','archived');
