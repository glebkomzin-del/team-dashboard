-- Redacted, durable diagnostics and bounded recovery for transient worker failures.
create table public.wm_pipeline_recoveries (
 space_id uuid not null references public.wm_spaces(id), job_id text not null, failure_id uuid not null,
 occurred_at timestamptz not null, recorded_at timestamptz not null default clock_timestamp(),
 operation text not null check(operation ~ '^[a-z_]{1,80}$'),
 error_type text not null check(error_type in ('http','network','response_decode')),
 http_status integer check(http_status between 100 and 599), sqlstate text check(sqlstate ~ '^[A-Z0-9]{5}$'),
 gateway_attempts integer not null check(gateway_attempts between 1 and 3),
 recovery_ordinal integer not null check(recovery_ordinal between 1 and 3),
 expected_revision bigint not null check(expected_revision>=0), failed_job_updated_at timestamptz not null,
 next_retry_at timestamptz not null, recovered_at timestamptz, recovered_revision bigint check(recovered_revision>=0),
 primary key(space_id,failure_id), foreign key(space_id,job_id) references public.wm_jobs(space_id,id),
 check((recovered_at is null and recovered_revision is null) or (recovered_at is not null and recovered_revision is not null))
);
alter table public.wm_pipeline_recoveries enable row level security;
revoke all on public.wm_pipeline_recoveries from public,anon,authenticated,service_role;
grant select,insert,update on public.wm_pipeline_recoveries to service_role;
create index wm_pipeline_recoveries_job on public.wm_pipeline_recoveries(space_id,job_id,recorded_at desc);

create function public.wm_pause_transport_job(p_space_id uuid,p_job_id text,p_lease_token uuid,p_failure_id uuid,p_diagnostic jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare j public.wm_jobs%rowtype; prior public.wm_pipeline_recoveries%rowtype;
 occurred timestamptz; paused_at timestamptz:=clock_timestamp(); ordinal integer; next_retry timestamptz;
begin
 if p_job_id is null or p_job_id !~ '^[0-9a-f]{64}$' or p_lease_token is null or p_failure_id is null
    or jsonb_typeof(p_diagnostic)!='object' or not (p_diagnostic ?& array['at','op','type','http_status','sqlstate','attempts'])
    or (p_diagnostic-array['at','op','type','http_status','sqlstate','attempts'])!='{}'::jsonb
    or coalesce(p_diagnostic->>'op','') !~ '^[a-z_]{1,80}$' or p_diagnostic->>'type' not in ('http','network','response_decode')
    or jsonb_typeof(p_diagnostic->'attempts')!='number' or (p_diagnostic->>'attempts') !~ '^[1-3]$'
    or (p_diagnostic->'http_status'!='null'::jsonb and (jsonb_typeof(p_diagnostic->'http_status')!='number' or (p_diagnostic->>'http_status') !~ '^[1-5][0-9]{2}$'))
    or (p_diagnostic->'sqlstate'!='null'::jsonb and coalesce(p_diagnostic->>'sqlstate','') !~ '^[A-Z0-9]{5}$') then
   raise exception 'Invalid redacted transport diagnostic' using errcode='22023'; end if;
 begin occurred:=(p_diagnostic->>'at')::timestamptz;
 exception when invalid_datetime_format then raise exception 'Invalid transport timestamp' using errcode='22023'; end;
 if occurred not between clock_timestamp()-interval '1 day' and clock_timestamp()+interval '5 minutes' then
   raise exception 'Transport timestamp outside accepted window' using errcode='22023'; end if;
 select * into prior from public.wm_pipeline_recoveries where space_id=p_space_id and failure_id=p_failure_id;
 if found then
   if prior.job_id is distinct from p_job_id or prior.operation is distinct from p_diagnostic->>'op' or prior.error_type is distinct from p_diagnostic->>'type' then
     raise exception 'Transport failure identity reused' using errcode='23505'; end if;
   return jsonb_build_object('state','paused','reason','transport_failed','failure_id',prior.failure_id,'next_retry_at',prior.next_retry_at,'repeated',true);
 end if;
 perform 1 from public.wm_spaces where id=p_space_id for update;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 if not found or j.state not in ('running','prepared') or j.lease_token is distinct from p_lease_token then
   raise exception 'Transport pause lease changed' using errcode='40001'; end if;
 select count(*)+1 into ordinal from public.wm_pipeline_recoveries where space_id=p_space_id and job_id=p_job_id and recovered_at is not null;
 next_retry:=greatest(paused_at+case when ordinal=1 then interval '30 seconds' else interval '2 minutes' end,coalesce(j.lease_until,paused_at));
 update public.wm_jobs set state='review',reason='transport_failed',updated_at=paused_at where space_id=p_space_id and id=p_job_id;
 insert into public.wm_pipeline_recoveries(space_id,job_id,failure_id,occurred_at,recorded_at,operation,error_type,http_status,sqlstate,
   gateway_attempts,recovery_ordinal,expected_revision,failed_job_updated_at,next_retry_at)
 values(p_space_id,p_job_id,p_failure_id,occurred,paused_at,p_diagnostic->>'op',p_diagnostic->>'type',nullif(p_diagnostic->>'http_status','')::integer,
   nullif(p_diagnostic->>'sqlstate',''),(p_diagnostic->>'attempts')::integer,ordinal,j.expected_revision,paused_at,next_retry);
 return jsonb_build_object('state','paused','reason','transport_failed','failure_id',p_failure_id,'next_retry_at',next_retry,'repeated',false);
end; $$;

create function public.wm_recover_transport_job(p_space_id uuid,p_job_id text,p_pipeline text,p_failure_id uuid,
 p_expected_revision bigint,p_expected_updated_at timestamptz)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype; j public.wm_jobs%rowtype;
 failure public.wm_pipeline_recoveries%rowtype; earlier boolean;
begin
 if p_job_id is null or p_job_id !~ '^[0-9a-f]{64}$' or p_pipeline is null or p_failure_id is null
    or p_expected_revision is null or p_expected_updated_at is null then raise exception 'Incomplete transport recovery request' using errcode='22023'; end if;
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or s.revision is distinct from p_expected_revision then raise exception 'Transport recovery context changed' using errcode='40001'; end if;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 select * into failure from public.wm_pipeline_recoveries where space_id=p_space_id and job_id=p_job_id and failure_id=p_failure_id for update;
 if not found or j.updated_at is distinct from p_expected_updated_at or failure.failed_job_updated_at is distinct from j.updated_at
    or failure.recovered_at is not null or j.state!='review' or j.reason!='transport_failed' or j.pipeline is distinct from p_pipeline
    or j.expected_revision is distinct from s.revision or failure.expected_revision is distinct from s.revision or j.prepared_payload is not null
    or c.space_id is null or not c.enabled or c.pipeline is distinct from p_pipeline
    or c.automatic_from is null or j.event_date<c.automatic_from then raise exception 'Transport recovery is not safe' using errcode='40001'; end if;
 if clock_timestamp()<failure.next_retry_at then
   return jsonb_build_object('job_id',j.id,'state','paused','reason','transport_retry_backoff','failure_id',failure.failure_id,'next_retry_at',failure.next_retry_at); end if;
 if failure.recovery_ordinal>2 or j.attempts>=3 then
   return jsonb_build_object('job_id',j.id,'state','paused','reason','transport_retry_exhausted','failure_id',failure.failure_id,'next_retry_at',null); end if;
 select exists(select 1 from public.wm_jobs x where x.space_id=p_space_id and x.id!=j.id and x.state not in ('applied','archived')
   and (x.event_date,x.created_at,x.id)<(j.event_date,j.created_at,j.id)) into earlier;
 if earlier or exists(select 1 from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id)
    or not exists(select 1 from public.wm_archive_documents d where d.space_id=p_space_id and d.id=j.document_id and d.source_id=j.source_id and d.redaction_id is null and d.body is not null)
    or exists(select 1 from public.wm_source_deletions d where d.space_id=p_space_id and d.source_id=j.source_id and d.state in ('prepared','purging'))
    or exists(select 1 from public.wm_source_versions where space_id=p_space_id and (source_id=j.source_id or event_date>j.event_date))
    or exists(select 1 from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=j.source_id and d.id!=j.document_id
      and d.redaction_id is null and d.body_hash!=(select body_hash from public.wm_archive_documents where space_id=p_space_id and id=j.document_id)) then
   raise exception 'Transport recovery requires manual review' using errcode='22023'; end if;
 update public.wm_jobs set state='queued',reason=null,expected_revision=null,lease_token=null,lease_until=null,updated_at=clock_timestamp()
  where space_id=p_space_id and id=p_job_id returning * into j;
 update public.wm_pipeline_recoveries set recovered_at=clock_timestamp(),recovered_revision=s.revision where space_id=p_space_id and failure_id=p_failure_id;
 return jsonb_build_object('job_id',j.id,'state',j.state,'recovered',true,'failure_id',p_failure_id,'attempts',j.attempts,'updated_at',j.updated_at);
end; $$;

create or replace function public.wm_job_detail(p_space_id uuid,p_job_id text)
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('job',to_jsonb(j),'title',d.title,
  'calls',coalesce((select jsonb_agg(jsonb_build_object('index',c.call_index,'received',c.response_json is not null,'reserved_micro_usd',c.reserved_micro_usd,'actual_micro_usd',c.actual_micro_usd) order by c.call_index)
    from public.wm_model_calls c where c.space_id=p_space_id and c.job_id=j.id),'[]'::jsonb),
  'decisions',coalesce((select jsonb_agg(jsonb_build_object('command_id',h.command_id,'action',h.action,'reason',h.reason,'recorded_at',h.recorded_at) order by h.recorded_at)
    from public.wm_job_decisions h where h.space_id=p_space_id and h.job_id=j.id),'[]'::jsonb),
  'transport_failures',coalesce((select jsonb_agg(jsonb_build_object('failure_id',r.failure_id,'occurred_at',r.occurred_at,'recorded_at',r.recorded_at,
    'op',r.operation,'type',r.error_type,'http_status',r.http_status,'sqlstate',r.sqlstate,'attempts',r.gateway_attempts,
    'recovery_ordinal',r.recovery_ordinal,'next_retry_at',r.next_retry_at,'recovered_at',r.recovered_at,'recovered_revision',r.recovered_revision) order by r.recorded_at)
    from public.wm_pipeline_recoveries r where r.space_id=p_space_id and r.job_id=j.id),'[]'::jsonb))
 from public.wm_jobs j join public.wm_archive_documents d on d.space_id=j.space_id and d.id=j.document_id
 where j.space_id=p_space_id and j.id=p_job_id;
$$;

revoke all on function public.wm_pause_transport_job(uuid,text,uuid,uuid,jsonb),public.wm_recover_transport_job(uuid,text,text,uuid,bigint,timestamptz) from public,anon,authenticated;
grant execute on function public.wm_pause_transport_job(uuid,text,uuid,uuid,jsonb),public.wm_recover_transport_job(uuid,text,text,uuid,bigint,timestamptz) to service_role;
