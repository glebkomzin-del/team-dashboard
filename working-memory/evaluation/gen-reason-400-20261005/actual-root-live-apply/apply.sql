begin; set local lock_timeout='5s'; set local statement_timeout='90s';
lock table public.wm_spaces, public.wm_processing_config, public.wm_jobs, public.wm_generation_reviews in share row exclusive mode;
do $$ begin
 if not exists(select 1 from public.wm_spaces s join public.wm_processing_config c on c.space_id=s.id where s.id='96a2dc44-9b9e-4644-b236-c5c1956cd39d' and s.revision=224 and c.enabled=false) then raise exception 'wrong revision or claims not paused'; end if;
 if not exists(select 1 from public.wm_generation_reviews g join public.wm_jobs j on j.id=g.job_id and j.space_id=g.space_id where g.id='9ffad67b-7534-4b47-8305-fd7b09609e86' and g.state='pending' and g.expected_revision=224 and g.review_sha256='f6f4e931afdc2797af1fdd8970ac4c8776ce77cb489d56edb040f1f2d7e2504e' and j.state='running' and j.updated_at=g.job_updated_at and j.lease_until<clock_timestamp()) then raise exception 'pending recovery changed'; end if;
 if (select count(*) from public.wm_model_calls where job_id='9db6eb68e9fc5e8e1a54147a3c5c668ab9734ca0b2e3b8f555a4114da8313549')!=4 or (select sum(actual_micro_usd) from public.wm_model_calls where job_id='9db6eb68e9fc5e8e1a54147a3c5c668ab9734ca0b2e3b8f555a4114da8313549')!=34726 then raise exception 'paid ledger changed'; end if;
 if not has_function_privilege('service_role','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE') or has_function_privilege('anon','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE') or has_function_privilege('authenticated','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE') then raise exception 'execution ACL differs'; end if;
end $$;
create temp table wm_reason_guard as select
(select md5(string_agg(to_jsonb(j)::text,E'\n' order by j.id)) from public.wm_jobs j) job_hash,
(select md5(string_agg((to_jsonb(m)-'request_json'-'response_json')::text,E'\n' order by m.space_id,m.job_id,m.call_index)) from public.wm_model_calls m) call_metadata_hash,
(select md5(string_agg(to_jsonb(g)::text,E'\n' order by g.id)) from public.wm_generation_reviews g) reviews_hash,
(select md5(string_agg(to_jsonb(j)::text,E'\n' order by j.space_id,j.revision)) from public.wm_journal j) journal_hash,
(select md5(string_agg(to_jsonb(s)::text,E'\n' order by s.space_id,s.id)) from public.wm_source_versions s) sources_hash;
-- GEN-REASON-400: preserve the optional owner note exactly in request/review.
-- Only the nonempty job-decision audit reason receives a technical fallback.
-- Read-only live baseline (2026-10-05): pg_get_functiondef MD5 0622bb6e1c04dcd75e5e0774ed502337;
-- prosrc MD5 537b2337087c84e8d4ab00d90c66b489. Abort on drift.
do $$
declare f oid;
begin
  f := to_regprocedure('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)');
  if f is null
     or (select md5(pg_get_functiondef(f))) is distinct from '0622bb6e1c04dcd75e5e0774ed502337'
     or (select md5(prosrc) from pg_proc where oid=f) is distinct from '537b2337087c84e8d4ab00d90c66b489'
     or (select prosecdef from pg_proc where oid=f) is distinct from false then
    raise exception 'wm_generation_decide baseline changed; inspect before applying GEN-REASON-400';
  end if;
end;
$$;

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
    values(p_space_id,p_command_id,g.job_id,p_actor_id,'apply_generation',
      case when length(trim(p_reason))=0 then 'Technischer Auditvermerk: Generation uebernommen; keine zusaetzliche Begruendung angegeben' else p_reason end,
      req||jsonb_build_object('job_id',g.job_id,'expected_updated_at',g.job_updated_at),to_jsonb(prior_job),job_result);
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

-- CREATE OR REPLACE preserves the existing function identity and ACL.
-- Do not grant browser roles access to this owner decision endpoint.
do $$
declare f oid;
begin
  f := 'public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure;
  if not has_function_privilege('service_role',f,'EXECUTE')
     or has_function_privilege('anon',f,'EXECUTE')
     or has_function_privilege('authenticated',f,'EXECUTE') then
    raise exception 'wm_generation_decide execution grants changed';
  end if;
end;
$$;

do $$ begin
if (select md5(pg_get_functiondef('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure)))!='52e542324b17616d1f912cb0f3ef14f7' then raise exception 'unexpected applied function'; end if;
if exists(select 1 from wm_reason_guard b where b.job_hash is distinct from (select md5(string_agg(to_jsonb(j)::text,E'\n' order by j.id)) from public.wm_jobs j) or b.call_metadata_hash is distinct from (select md5(string_agg((to_jsonb(m)-'request_json'-'response_json')::text,E'\n' order by m.space_id,m.job_id,m.call_index)) from public.wm_model_calls m) or b.reviews_hash is distinct from (select md5(string_agg(to_jsonb(g)::text,E'\n' order by g.id)) from public.wm_generation_reviews g) or b.journal_hash is distinct from (select md5(string_agg(to_jsonb(j)::text,E'\n' order by j.space_id,j.revision)) from public.wm_journal j) or b.sources_hash is distinct from (select md5(string_agg(to_jsonb(s)::text,E'\n' order by s.space_id,s.id)) from public.wm_source_versions s)) then raise exception 'business rows changed'; end if;
end $$;
select jsonb_build_object('result','GEN_REASON_400_APPLIED_WITH_BUSINESS_ROWS_UNCHANGED','function_md5',md5(pg_get_functiondef('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure)),'revision',224,'job_calls',4,'job_actual_micro_usd',34726,'processing_enabled',false,'migration_tracker_not_rewritten',true);
commit;
