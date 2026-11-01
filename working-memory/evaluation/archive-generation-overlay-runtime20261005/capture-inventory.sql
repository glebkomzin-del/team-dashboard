-- Run only after the original Main intake is paused and its positive drain is current.
-- One read-only statement supplies the exact later cutover guard; no content leaves the DB.
\set ON_ERROR_STOP on
select jsonb_build_object(
  'schema_version', 1,
  'captured_at', clock_timestamp(),
  'space_id', s.id,
  'revision', s.revision,
  'owner_id', s.owner_id,
  'space_state', s.state,
  'pipeline', c.pipeline,
  'enabled', c.enabled,
  'automatic_from', c.automatic_from,
  'budget_micro_usd', c.budget_micro_usd,
  'queued', coalesce((select jsonb_agg(jsonb_build_object('id',j.id,'updated_at',j.updated_at) order by j.id)
                      from public.wm_jobs j where j.space_id=s.id and j.state='queued'),'[]'::jsonb),
  'queue_all_unstarted', coalesce((select bool_and(j.reason is null and j.pipeline=c.pipeline
        and j.expected_revision is null and j.prepared_payload is null
        and j.lease_token is null and j.lease_until is null and j.attempts=0
        and j.applied_revision is null and not exists
          (select 1 from public.wm_model_calls m where m.space_id=s.id and m.job_id=j.id))
        from public.wm_jobs j where j.space_id=s.id and j.state='queued'),false),
  'running_count', (select count(*) from public.wm_jobs j where j.space_id=s.id and j.state='running'),
  'job_count', (select count(*) from public.wm_jobs j where j.space_id=s.id),
  'call_count', (select count(*) from public.wm_model_calls m where m.space_id=s.id),
  'job_hash', encode(extensions.digest(convert_to(coalesce((select string_agg(to_jsonb(j)::text,E'\n' order by j.id)
        from public.wm_jobs j where j.space_id=s.id),''),'UTF8'),'sha256'),'hex'),
  'nonqueued_job_hash', encode(extensions.digest(convert_to(coalesce((select string_agg(to_jsonb(j)::text,E'\n' order by j.id)
        from public.wm_jobs j where j.space_id=s.id and j.state!='queued'),''),'UTF8'),'sha256'),'hex'),
  'call_hash', encode(extensions.digest(convert_to(coalesce((select string_agg(to_jsonb(m)::text,E'\n' order by to_jsonb(m)::text)
        from public.wm_model_calls m where m.space_id=s.id),''),'UTF8'),'sha256'),'hex')
) from public.wm_spaces s join public.wm_processing_config c on c.space_id=s.id
where s.id='96a2dc44-9b9e-4644-b236-c5c1956cd39d'::uuid;
