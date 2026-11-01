-- A review action is already an auditable decision. A personal note is useful
-- context, but must not block accepting or rejecting a prepared generation.
do $$
declare constraint_name text;
begin
  select c.conname into constraint_name
  from pg_catalog.pg_constraint c
  where c.conrelid = 'public.wm_generation_reviews'::regclass
    and c.contype = 'c'
    and pg_catalog.pg_get_constraintdef(c.oid) like '%decision_reason%';
  if constraint_name is null then
    raise exception 'Generation review settlement constraint not found';
  end if;
  execute format('alter table public.wm_generation_reviews drop constraint %I', constraint_name);
end;
$$;

alter table public.wm_generation_reviews
  add constraint wm_generation_reviews_settlement_check check(
    (state='pending' and decision_command_id is null and decision_actor_id is null and decision_hash is null and decision_result is null and decided_at is null)
    or (state!='pending' and decision_command_id is not null and decision_actor_id is not null and decision_reason is not null
      and decision_hash is not null and decision_result is not null and decision_hash ~ '^[0-9a-f]{64}$'
      and length(trim(decision_reason)) <= 4000 and jsonb_typeof(decision_result)='object' and decided_at is not null)
  );

create or replace function public.wm_generation_decide(p_space_id uuid,p_review_id uuid,p_actor_id uuid,p_command_id uuid,
 p_expected_revision bigint,p_review_sha256 text,p_action text,p_reason text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; g public.wm_generation_reviews%rowtype; old_source public.wm_source_versions%rowtype; prior_job public.wm_jobs%rowtype;
 source jsonb; req jsonb; request_hash text; result jsonb; job_result jsonb; journal_hash text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 if p_command_id is null or p_action is null or p_action not in ('accept','reject') or p_reason is null or length(trim(p_reason))>4000 then
  raise exception 'Invalid generation decision' using errcode='22023'; end if;
 select * into g from public.wm_generation_reviews where space_id=p_space_id and id=p_review_id for update;
 if not found then raise exception 'Review unavailable' using errcode='22023'; end if;
 req:=jsonb_build_object('review_id',p_review_id,'actor_id',p_actor_id,'command_id',p_command_id,'expected_revision',p_expected_revision,
  'review_sha256',p_review_sha256,'action',p_action,'reason',p_reason);
 request_hash:=encode(extensions.digest(convert_to(req::text,'UTF8'),'sha256'),'hex');
 if g.state!='pending' then
  if g.decision_hash is distinct from request_hash then raise exception 'Review already decided with different content' using errcode='23505'; end if;
  return g.decision_result||jsonb_build_object('repeated',true);
 end if;
 if p_expected_revision is distinct from g.expected_revision or p_review_sha256 is distinct from g.review_sha256 then
  raise exception 'Reviewed generation changed' using errcode='40001'; end if;
 if p_action='accept' then
  if s.revision!=g.expected_revision then raise exception 'Generation base changed' using errcode='40001'; end if;
  if g.job_id is not null then
   select * into prior_job from public.wm_jobs where space_id=p_space_id and id=g.job_id for update;
   if not found or prior_job.updated_at is distinct from g.job_updated_at or prior_job.state in ('applied','archived','queued')
    or (prior_job.state in ('running','prepared') and prior_job.lease_until>clock_timestamp()) then
    raise exception 'Reviewed job changed' using errcode='40001'; end if;
  end if;
  for source in select value from jsonb_array_elements(g.payload->'new_sources') loop
   select * into old_source from public.wm_source_versions where space_id=p_space_id and id=source->>'id';
   if found then
    if old_source.source_id is distinct from source->>'source_id' or old_source.content_hash is distinct from source->>'content_hash'
     or old_source.event_date is distinct from (source->>'event_date')::date or old_source.title is distinct from source->>'title'
     or old_source.transcript is distinct from source->>'transcript' or old_source.observed_at is distinct from (source->>'observed_at')::timestamptz then
     raise exception 'Existing source identity changed' using errcode='23505'; end if;
   else
    insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
    values(p_space_id,source->>'id',source->>'source_id',source->>'content_hash',(source->>'event_date')::date,source->>'title',source->>'transcript',(source->>'observed_at')::timestamptz);
   end if;
  end loop;
  journal_hash:=encode(extensions.digest(convert_to(jsonb_build_object('kind','generation','payload',g.payload,'source',null,'actor_id',p_actor_id)::text,'UTF8'),'sha256'),'hex');
  insert into public.wm_journal(space_id,revision,command_id,request_hash,kind,actor_id,payload)
  values(p_space_id,s.revision+1,p_command_id,journal_hash,'generation',p_actor_id,g.payload);
  update public.wm_spaces set revision=revision+1 where id=p_space_id;
  if g.job_id is not null then
   update public.wm_jobs set state='applied',reason='owner_generation_applied',applied_revision=s.revision+1,updated_at=clock_timestamp()
    where space_id=p_space_id and id=g.job_id;
   job_result:=jsonb_build_object('state','applied','revision',s.revision+1,'generation_review_id',g.id);
   insert into public.wm_job_decisions(space_id,command_id,job_id,actor_id,action,reason,request,previous_job,result)
    values(p_space_id,p_command_id,g.job_id,p_actor_id,'apply_generation',p_reason,req||jsonb_build_object('job_id',g.job_id,'expected_updated_at',g.job_updated_at),to_jsonb(prior_job),job_result);
  end if;
  result:=jsonb_build_object('review_id',p_review_id,'state','accepted','revision',s.revision+1,'command_id',p_command_id,'job',job_result,'repeated',false);
 else
  result:=jsonb_build_object('review_id',p_review_id,'state','rejected','revision',s.revision,'command_id',p_command_id,'repeated',false);
 end if;
 update public.wm_generation_reviews set state=case when p_action='accept' then 'accepted' else 'rejected' end,
  decision_command_id=p_command_id,decision_actor_id=p_actor_id,decision_reason=p_reason,decision_hash=request_hash,
  decision_result=result,decided_at=clock_timestamp() where space_id=p_space_id and id=p_review_id;
 return result;
end; $$;

revoke all on function public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text) from public,anon,authenticated;
grant execute on function public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text) to service_role;
