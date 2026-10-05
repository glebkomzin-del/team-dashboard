-- GENERATED ONLY FROM A FRESH, POSITIVE INVENTORY AFTER MAIN PAUSE/DRAIN.
-- Required psql -v apply=true for a Lead-approved commit; default is rollback.
\set ON_ERROR_STOP on
\if :{?apply}
\else
  \set apply false
\endif
begin isolation level serializable;
create temp table semantic_cutover_result(result jsonb not null) on commit drop;
do $semantic_cutover$
declare
  p jsonb := convert_from(decode('__SNAPSHOT_HEX__','hex'),'UTF8')::jsonb;
  new_pipeline text := '__NEW_PIPELINE__';
  old_pipeline text := 'v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c';
  space uuid := '96a2dc44-9b9e-4644-b236-c5c1956cd39d';
  s public.wm_spaces%rowtype;
  c public.wm_processing_config%rowtype;
  j public.wm_jobs%rowtype;
  ids text[];
  actual_ids text[];
  n integer;
  prior jsonb;
  outcome jsonb;
  request jsonb;
  reason text;
  command_hex text;
  command_id uuid;
  captured_at timestamptz;
begin
  if (p->>'schema_version')::integer is distinct from 1
     or (p->>'space_id')::uuid is distinct from space
     or p->>'pipeline' is distinct from old_pipeline
     or (p->>'enabled')::boolean is distinct from false
     or p->>'queue_all_unstarted' is distinct from 'true'
     or (p->>'running_count')::integer is distinct from 0
     or new_pipeline !~ '^v11:compact1:gate1:gpt-5[.]6-terra:[0-9a-f]{16}:canonical1:[0-9a-f]{16}$'
     or new_pipeline=old_pipeline then
    raise exception 'Cutover snapshot or final pipeline is not eligible' using errcode='22023';
  end if;
  captured_at := (p->>'captured_at')::timestamptz;
  if captured_at is null or captured_at > clock_timestamp()
     or captured_at < clock_timestamp()-interval '5 minutes' then
    raise exception 'Cutover inventory is stale or unknown' using errcode='40001';
  end if;
  if p->>'job_hash' !~ '^[0-9a-f]{64}$' or p->>'call_hash' !~ '^[0-9a-f]{64}$'
     or (p->>'job_count')::integer < 1 or (p->>'call_count')::integer < 0 then
    raise exception 'Cutover fingerprints are missing' using errcode='22023';
  end if;
  select array_agg(x.id order by x.id) into ids
    from jsonb_to_recordset(p->'queued') as x(id text,updated_at timestamptz);
  n := coalesce(array_length(ids,1),0);
  if n=0 or n != jsonb_array_length(p->'queued') or n != (select count(distinct x) from unnest(ids) x) then
    raise exception 'Cutover inventory is empty or duplicated' using errcode='22023';
  end if;

  -- Existing enqueue/claim path locks wm_spaces first. Keep that order.
  select * into s from public.wm_spaces where id=space for update;
  if not found or s.owner_id is distinct from (p->>'owner_id')::uuid
     or s.state::text is distinct from p->>'space_state'
     or s.state='retired' or s.revision is distinct from (p->>'revision')::bigint then
    raise exception 'Space owner/state/revision changed' using errcode='40001';
  end if;
  select * into c from public.wm_processing_config where space_id=space for update;
  if not found or c.pipeline is distinct from old_pipeline or c.enabled is distinct from false
     or c.automatic_from is distinct from (p->>'automatic_from')::date
     or c.budget_micro_usd is distinct from (p->>'budget_micro_usd')::bigint then
    raise exception 'Processing policy changed' using errcode='40001';
  end if;
  perform 1 from public.wm_jobs where space_id=space order by id for update;
  lock table public.wm_model_calls in share mode;
  if (select count(*) from public.wm_jobs where space_id=space) is distinct from (p->>'job_count')::integer
     or (select count(*) from public.wm_model_calls where space_id=space) is distinct from (p->>'call_count')::integer
     or (select count(*) from public.wm_jobs where space_id=space and state='running') != 0
     or (select encode(extensions.digest(convert_to(coalesce(string_agg(to_jsonb(j0)::text,E'\n' order by j0.id),''),'UTF8'),'sha256'),'hex')
         from public.wm_jobs j0 where j0.space_id=space) is distinct from p->>'job_hash'
     or (select encode(extensions.digest(convert_to(coalesce(string_agg(to_jsonb(m)::text,E'\n' order by to_jsonb(m)::text),''),'UTF8'),'sha256'),'hex')
         from public.wm_model_calls m where m.space_id=space) is distinct from p->>'call_hash' then
    raise exception 'Frozen job or paid call history changed' using errcode='40001';
  end if;
  select array_agg(id order by id) into actual_ids from public.wm_jobs where space_id=space and state='queued';
  if actual_ids is distinct from ids then
    raise exception 'Queue membership changed' using errcode='40001';
  end if;
  if (select count(*) from public.wm_jobs j0
        join jsonb_to_recordset(p->'queued') as x(id text,updated_at timestamptz) on x.id=j0.id
        where j0.space_id=space and j0.state='queued' and j0.pipeline=old_pipeline
          and j0.updated_at=x.updated_at and j0.reason is null
          and j0.expected_revision is null and j0.prepared_payload is null
          and j0.lease_token is null and j0.lease_until is null and j0.attempts=0
          and j0.applied_revision is null
          and not exists(select 1 from public.wm_model_calls m where m.space_id=space and m.job_id=j0.id)) != n then
    raise exception 'A queued job is paid, leased, prepared or changed' using errcode='40001';
  end if;
  if not exists(select 1 from pg_catalog.pg_constraint k
      where k.conrelid='public.wm_job_decisions'::regclass and k.conname='wm_job_decisions_action_check'
        and pg_catalog.pg_get_constraintdef(k.oid) like '%pipeline_cutover%') then
    raise exception 'Pipeline cutover audit is unavailable' using errcode='55000';
  end if;
  update public.wm_processing_config set pipeline=new_pipeline where space_id=space;
  reason := format('Geprüfter Semantic-Endstate-Cutover %s auf %s: ausschließlich %s frisch inventarisierte, unbezahlte und ungestartete Queue-Jobs.',old_pipeline,new_pipeline,n);
  for j in select * from public.wm_jobs where space_id=space and id=any(ids) order by id for update loop
    prior := to_jsonb(j);
    command_hex := encode(extensions.digest(convert_to(space::text||':pipeline-cutover:'||new_pipeline||':'||j.id,'UTF8'),'sha256'),'hex');
    command_id := (substr(command_hex,1,8)||'-'||substr(command_hex,9,4)||'-'||substr(command_hex,13,4)||'-'||substr(command_hex,17,4)||'-'||substr(command_hex,21,12))::uuid;
    request := jsonb_build_object('operation','pipeline_cutover','actor_id',s.owner_id,'job_id',j.id,
      'expected_revision',s.revision,'expected_updated_at',j.updated_at,
      'expected_old_pipeline',old_pipeline,'new_pipeline',new_pipeline,
      'expected_policy',jsonb_build_object('enabled',false,'automatic_from',c.automatic_from,'budget_micro_usd',c.budget_micro_usd),
      'expected_job',jsonb_build_object('state','queued','reason',null,'calls',0,'prepared',false,
        'expected_revision',null,'leased',false,'attempts',0,'applied_revision',null));
    update public.wm_jobs set pipeline=new_pipeline,updated_at=clock_timestamp() where space_id=space and id=j.id;
    select jsonb_build_object('job_id',id,'state',state,'pipeline',pipeline,'updated_at',updated_at,
      'revision',s.revision) into outcome from public.wm_jobs where space_id=space and id=j.id;
    insert into public.wm_job_decisions(space_id,command_id,job_id,actor_id,action,reason,request,previous_job,result)
      values(space,command_id,j.id,s.owner_id,'pipeline_cutover',reason,request,prior,outcome);
  end loop;
  if (select (to_jsonb(c1)-'pipeline'-'updated_at') is not distinct from (to_jsonb(c)-'pipeline'-'updated_at')
      from public.wm_processing_config c1 where c1.space_id=space) is not true
     or (select count(*) from public.wm_jobs where space_id=space and id=any(ids) and state='queued'
          and pipeline=new_pipeline and expected_revision is null and prepared_payload is null
          and lease_token is null and lease_until is null and attempts=0) != n
     or (select encode(extensions.digest(convert_to(coalesce(string_agg(to_jsonb(m)::text,E'\n' order by to_jsonb(m)::text),''),'UTF8'),'sha256'),'hex')
         from public.wm_model_calls m where m.space_id=space) is distinct from p->>'call_hash' then
    raise exception 'Cutover postcondition failed' using errcode='40001';
  end if;
  insert into semantic_cutover_result values(jsonb_build_object('result','SEMANTIC_CUTOVER_VALID',
    'space_id',space,'old_pipeline',old_pipeline,'new_pipeline',new_pipeline,
    'retargeted_queued_jobs',n,'paid_call_hash_unchanged',p->>'call_hash'));
end $semantic_cutover$;
table semantic_cutover_result;
\if :apply
  commit;
\else
  rollback;
\endif
