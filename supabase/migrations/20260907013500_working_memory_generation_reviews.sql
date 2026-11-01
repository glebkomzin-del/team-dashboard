-- Explicit, owner-reviewed generation replacement. Original journal entries,
-- archived transcripts, model receipts and personal decisions remain retained.
create table public.wm_generation_reviews (
 space_id uuid not null references public.wm_spaces(id), id uuid not null,
 expected_revision bigint not null check(expected_revision>=0),
 label text not null check(length(trim(label)) between 1 and 200),
 payload jsonb not null check(jsonb_typeof(payload)='object'),
 review_sha256 text not null check(review_sha256 ~ '^[0-9a-f]{64}$'),
 job_id text, job_updated_at timestamptz,
 state text not null default 'pending' check(state in ('pending','accepted','rejected')),
 created_at timestamptz not null default clock_timestamp(),
 decision_command_id uuid, decision_actor_id uuid references auth.users(id),
 decision_reason text, decision_hash text, decision_result jsonb, decided_at timestamptz,
 primary key(space_id,id), foreign key(space_id,job_id) references public.wm_jobs(space_id,id),
 unique(space_id,decision_command_id),
 check((job_id is null)=(job_updated_at is null)),
 check((state='pending' and decision_command_id is null and decision_actor_id is null and decision_hash is null and decision_result is null and decided_at is null)
    or (state!='pending' and decision_command_id is not null and decision_actor_id is not null and decision_reason is not null and decision_hash is not null and decision_result is not null and decision_hash ~ '^[0-9a-f]{64}$'
        and length(trim(decision_reason)) between 1 and 4000 and jsonb_typeof(decision_result)='object' and decided_at is not null))
);
alter table public.wm_generation_reviews enable row level security;
revoke all on public.wm_generation_reviews from public,anon,authenticated,service_role;
grant select on public.wm_generation_reviews to authenticated;
grant select,insert,update on public.wm_generation_reviews to service_role;
create policy wm_generation_owner_read on public.wm_generation_reviews for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_generation_service_access on public.wm_generation_reviews for all to service_role using(true) with check(true);

alter table public.wm_job_decisions drop constraint wm_job_decisions_action_check;
alter table public.wm_job_decisions add constraint wm_job_decisions_action_check check(action in ('retry','archive_only','rebase_prepared','apply_generation'));

alter table public.wm_journal drop constraint wm_journal_kind_check;
alter table public.wm_journal add constraint wm_journal_kind_check check(kind in ('source','human','generation'));
alter table public.wm_journal drop constraint wm_journal_check;
alter table public.wm_journal add constraint wm_journal_check check(
 (kind='source' and source_version is not null and actor_id is null)
 or (kind in ('human','generation') and source_version is null and actor_id is not null));

create function public.wm_generation_stage(p_space_id uuid,p_review_id uuid,p_expected_revision bigint,p_label text,p_payload jsonb,p_job_id text default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; g public.wm_generation_reviews%rowtype; j public.wm_jobs%rowtype;
 source jsonb; source_body_hash text; version_id text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
 if p_review_id is null or p_expected_revision is null or p_expected_revision<0 or p_label is null or length(trim(p_label)) not between 1 and 200
  or p_payload is null or jsonb_typeof(p_payload)!='object' or p_payload->>'format' is distinct from 'wm-generation-review-v1'
  or coalesce(p_payload->>'review_sha256','') !~ '^[0-9a-f]{64}$' or coalesce(p_payload->>'base_sha256','') !~ '^[0-9a-f]{64}$'
  or coalesce(p_payload->>'state_sha256','') !~ '^[0-9a-f]{64}$' or jsonb_typeof(p_payload->'entries') is distinct from 'array'
  or jsonb_typeof(p_payload->'new_sources') is distinct from 'array' or jsonb_typeof(p_payload->'source_reviews') is distinct from 'object'
  or jsonb_typeof(p_payload->'identity_links') is distinct from 'array' or jsonb_typeof(p_payload->'diff') is distinct from 'array'
  or jsonb_typeof(p_payload->'observation_diff') is distinct from 'array'
  or coalesce(length(trim(p_payload->>'reason')),0) not between 1 and 4000 or octet_length(p_payload::text)>3800000 then
  raise exception 'Invalid compiled generation' using errcode='22023'; end if;
 select * into g from public.wm_generation_reviews where space_id=p_space_id and id=p_review_id;
 if found then
  if g.expected_revision is distinct from p_expected_revision or g.payload is distinct from p_payload or g.label is distinct from p_label or g.job_id is distinct from p_job_id then
   raise exception 'Review identity reused' using errcode='23505'; end if;
  return jsonb_build_object('review_id',g.id,'expected_revision',g.expected_revision,'state',g.state,'repeated',true);
 end if;
 if s.revision!=p_expected_revision then raise exception 'Generation base changed' using errcode='40001'; end if;
 if p_job_id is not null then
  select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
  if not found or j.state in ('applied','archived','queued') or (j.state in ('running','prepared') and j.lease_until>clock_timestamp()) then
   raise exception 'Job unavailable for generation review' using errcode='40001'; end if;
  if not (p_payload->'source_reviews' ? j.source_id) then raise exception 'Job is outside reviewed sources' using errcode='22023'; end if;
 end if;
 for source in select value from jsonb_array_elements(p_payload->'new_sources') loop
  if jsonb_typeof(source)!='object' or not (source ?& array['id','source_id','content_hash','event_date','title','transcript','observed_at']) then
   raise exception 'Incomplete generation source' using errcode='22023'; end if;
  source_body_hash:=encode(extensions.digest(convert_to(source->>'transcript','UTF8'),'sha256'),'hex');
  version_id:=encode(extensions.digest(convert_to((source->>'source_id')||':'||source_body_hash,'UTF8'),'sha256'),'hex');
  if source->>'content_hash' is distinct from source_body_hash or source->>'id' is distinct from version_id or not exists(
   select 1 from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=source->>'source_id'
    and d.body_hash=source_body_hash and d.body=source->>'transcript' and d.title=source->>'title' and d.event_date=(source->>'event_date')::date) then
   raise exception 'Generation source is not an archived original' using errcode='22023'; end if;
 end loop;
 insert into public.wm_generation_reviews(space_id,id,expected_revision,label,payload,review_sha256,job_id,job_updated_at)
 values(p_space_id,p_review_id,p_expected_revision,p_label,p_payload,p_payload->>'review_sha256',p_job_id,j.updated_at);
 return jsonb_build_object('review_id',p_review_id,'expected_revision',p_expected_revision,'state','pending','repeated',false);
end; $$;

create function public.wm_generation_decide(p_space_id uuid,p_review_id uuid,p_actor_id uuid,p_command_id uuid,
 p_expected_revision bigint,p_review_sha256 text,p_action text,p_reason text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; g public.wm_generation_reviews%rowtype; old_source public.wm_source_versions%rowtype; prior_job public.wm_jobs%rowtype;
 source jsonb; req jsonb; request_hash text; result jsonb; job_result jsonb; journal_hash text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 if p_command_id is null or p_action is null or p_action not in ('accept','reject') or p_reason is null or length(trim(p_reason)) not between 1 and 4000 then
  raise exception 'Explicit generation decision required' using errcode='22023'; end if;
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
   -- This source was manually reconciled, not merely discarded. Preserve the
   -- original lease and paid reservation so a late response can still settle.
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
revoke all on function public.wm_generation_stage(uuid,uuid,bigint,text,jsonb,text),public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text) from public,anon,authenticated;
grant execute on function public.wm_generation_stage(uuid,uuid,bigint,text,jsonb,text),public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text) to service_role;

-- Include pending, rejected and accepted reviews in the same consistent backup.
alter table public.wm_backup_records drop constraint wm_backup_records_kind_check;
alter table public.wm_backup_records add constraint wm_backup_records_kind_check check(kind in ('config','job','call','job_decision','generation_review'));
create or replace function public.wm_backup_begin(p_space_id uuid,p_snapshot_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; b public.wm_backup_snapshots%rowtype;
begin
 if p_snapshot_id is null then raise exception 'Snapshot identity required' using errcode='22023'; end if;
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found then raise exception 'Space unavailable' using errcode='22023'; end if;
 select * into b from public.wm_backup_snapshots where id=p_snapshot_id;
 if found then
  if b.space_id!=p_space_id then raise exception 'Snapshot identity unavailable' using errcode='42501'; end if;
  return to_jsonb(b)||jsonb_build_object('repeated',true);
 end if;
 insert into public.wm_backup_snapshots(id,space_id,revision,archive_revision,space_json)
 values(p_snapshot_id,p_space_id,s.revision,s.archive_revision,to_jsonb(s));
 insert into public.wm_backup_records(snapshot_id,kind,record_json,record_hash)
 select p_snapshot_id,x.kind,x.body,encode(extensions.digest(convert_to(x.body,'UTF8'),'sha256'),'hex')
 from (
  select 'config' as kind,to_jsonb(c)::text as body from public.wm_processing_config c where c.space_id=p_space_id
  union all select 'job',to_jsonb(j)::text from public.wm_jobs j where j.space_id=p_space_id
  union all select 'call',to_jsonb(c)::text from public.wm_model_calls c where c.space_id=p_space_id
  union all select 'job_decision',to_jsonb(h)::text from public.wm_job_decisions h where h.space_id=p_space_id
  union all select 'generation_review',to_jsonb(g)::text from public.wm_generation_reviews g where g.space_id=p_space_id
 ) x;
 update public.wm_backup_snapshots set record_count=(select count(*) from public.wm_backup_records where snapshot_id=p_snapshot_id)
 where id=p_snapshot_id returning * into b;
 return to_jsonb(b)||jsonb_build_object('repeated',false);
end; $$;
