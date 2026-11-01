-- Archive-only originals have no accepted journal source and therefore no
-- evidence package. They still have a live archive body that must be erased,
-- while tasks, knowledge and any accepted source remain untouched.
create or replace function public.wm_source_deletion_inputs(p_space_id uuid,p_source_id text,p_actor_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if not exists(select 1 from public.wm_spaces where id=p_space_id and owner_id=p_actor_id and state!='retired') then
  raise exception 'Owner required' using errcode='42501'; end if;
 select coalesce(jsonb_agg(value order by value->'source'->>'event_date',value->'source'->>'observed_at',value->'source'->>'id'),'[]'::jsonb) into result from (
  select jsonb_build_object('kind','source','source',to_jsonb(v)-'space_id'-'redaction_id','payload',j.payload) value
  from public.wm_source_versions v join public.wm_journal j on j.space_id=v.space_id and j.source_version=v.id and j.kind='source'
  where v.space_id=p_space_id and v.source_id=p_source_id and v.redaction_id is null
  union all
  -- A source accepted through a reviewed generation has no direct source
  -- journal row. Its immutable payload is the generation's `new` entry.
  select jsonb_build_object('kind','source','source',to_jsonb(v)-'space_id'-'redaction_id','payload',entry->'new'->'payload') value
  from public.wm_source_versions v
  join public.wm_journal j on j.space_id=v.space_id and j.kind='generation'
  cross join lateral (
   with recursive unwrapped(payload) as (
    select j.payload
    union all
    select u.payload->'sanitized_payload' from unwrapped u
     where u.payload->>'format'='wm-redacted-generation-v1'
       and jsonb_typeof(u.payload->'sanitized_payload')='object'
   ) select payload from unwrapped
     where payload->>'format' is distinct from 'wm-redacted-generation-v1'
  ) generation_payload
  cross join lateral jsonb_array_elements(generation_payload.payload->'entries') entry
  where v.space_id=p_space_id and v.source_id=p_source_id and v.redaction_id is null
    and entry ? 'new' and entry->'new'->>'kind'='source'
    and entry->'new'->'source'->>'id'=v.id
    and entry->'new'->'source'->>'source_id'=v.source_id
    and entry->'new'->'source'->>'content_hash'=v.content_hash
    and entry->'new'->'payload' is not null
  union all
  select jsonb_build_object('kind','archive_only','source',jsonb_build_object('id',d.id,'source_id',d.source_id,
    'content_hash',d.body_hash,'event_date',d.event_date,'title',d.title,'observed_at',d.observed_at,'transcript',d.body))
  from public.wm_archive_documents d
  where d.space_id=p_space_id and d.source_id=p_source_id and d.redaction_id is null and d.body is not null
 ) inputs;
 return result;
end; $$;

create or replace function public.wm_source_deletion_stage(
 p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_source_id text,p_packages jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; previous public.wm_source_deletions%rowtype; request_hash text; package jsonb;
 expected_versions text[]; supplied_versions text[]; archive_ids text[]; content_hashes text[];
 required constant text[]:=array['archive_documents','archive_notes','source_versions','journal_payloads','generation_payloads','prepared_jobs','model_receipts','question_receipts','search_documents','search_results','local_caches','backup_sets'];
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 if p_deletion_id is null or p_source_id is null or length(p_source_id) not between 1 and 512 or p_packages is null or jsonb_typeof(p_packages)!='array' then raise exception 'Invalid source deletion request' using errcode='22023'; end if;
 request_hash:=encode(extensions.digest(convert_to(jsonb_build_object('actor_id',p_actor_id,'source_id',p_source_id,'packages',p_packages)::text,'UTF8'),'sha256'),'hex');
 select * into previous from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id;
 if found then if previous.request_hash!=request_hash then raise exception 'Deletion identity reused' using errcode='23505'; end if; return jsonb_build_object('deletion_id',previous.id,'state',previous.state,'repeated',true,'active_backup_snapshots',(select count(*) from public.wm_backup_snapshots b where b.space_id=p_space_id)); end if;
 if exists(select 1 from public.wm_source_deletions where space_id=p_space_id and source_id=p_source_id and state in ('prepared','purging')) then raise exception 'Source identity already has an active deletion' using errcode='23505'; end if;
 select coalesce(array_agg(v.id order by v.id),'{}') into expected_versions from public.wm_source_versions v where v.space_id=p_space_id and v.source_id=p_source_id and v.redaction_id is null;
 select coalesce(array_agg(value->'source'->>'id' order by value->'source'->>'id'),'{}') into supplied_versions from jsonb_array_elements(p_packages);
 if cardinality(expected_versions)=0 then
  if cardinality(supplied_versions)<>0 or not exists(select 1 from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id and d.redaction_id is null and d.body is not null) then raise exception 'Archive-only deletion requires its current original and no packages' using errcode='22023'; end if;
 elsif expected_versions is distinct from supplied_versions then raise exception 'Every live source version needs one redaction package' using errcode='22023'; end if;
 for package in select value from jsonb_array_elements(p_packages) loop
  if package->>'format'!='wm-redacted-source-v1' or package->'source'->>'source_id' is distinct from p_source_id
    or encode(extensions.digest(convert_to((package->'source'->>'source_id')||':'||(package->'source'->>'content_hash'),'UTF8'),'sha256'),'hex')!=package->'source'->>'id'
    or exists(select 1 from jsonb_array_elements(package->'evidence_manifest'->'entries') e where encode(extensions.digest(convert_to(e->>'quote','UTF8'),'sha256'),'hex')!=e->>'quote_sha256')
    or not exists(select 1 from public.wm_source_versions v where v.space_id=p_space_id and v.id=package->'source'->>'id' and v.source_id=p_source_id and v.content_hash=package->'source'->>'content_hash' and v.redaction_id is null) then raise exception 'Invalid redaction package' using errcode='22023'; end if;
 end loop;
 if exists(select 1 from public.wm_jobs j where j.space_id=p_space_id and j.source_id=p_source_id and j.state in ('running','prepared')) then raise exception 'Active source job blocks deletion staging' using errcode='40001'; end if;
 update public.wm_jobs set state='archived',reason='source_deleted',lease_token=null,lease_until=null,updated_at=clock_timestamp()
  where space_id=p_space_id and source_id=p_source_id and state in ('queued','review');
 select coalesce(array_agg(d.id order by d.id),'{}') into archive_ids from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id and d.redaction_id is null;
 select coalesce(array_agg(distinct h order by h),'{}') into content_hashes from (select v.content_hash h from public.wm_source_versions v where v.space_id=p_space_id and v.source_id=p_source_id and v.redaction_id is null union select d.body_hash from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id and d.redaction_id is null) hashes;
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=p_space_id returning deletion_revision into s.deletion_revision;
 insert into public.wm_source_deletions(space_id,id,source_id,actor_id,request_hash,ledger_revision,archive_document_ids,original_content_hashes,required_scopes) values(p_space_id,p_deletion_id,p_source_id,p_actor_id,request_hash,s.deletion_revision,archive_ids,content_hashes,required);
 for package in select value from jsonb_array_elements(p_packages) loop insert into public.wm_source_deletion_versions values(p_space_id,p_deletion_id,package->'source'->>'id',package->'source'->>'content_hash',package,encode(extensions.digest(convert_to(package::text,'UTF8'),'sha256'),'hex')); end loop;
 return jsonb_build_object('deletion_id',p_deletion_id,'state','prepared','repeated',false,'processed_versions',cardinality(expected_versions),'archive_documents',cardinality(archive_ids),'active_backup_snapshots',(select count(*) from public.wm_backup_snapshots b where b.space_id=p_space_id));
end; $$;

-- An archive note remains a useful derived record, but it cannot remain an
-- active note once its document is moved into deleted_documents.  Mark it in
-- the same transaction, retain its text, and bind its retained body by hash.
create or replace function public.wm_archive_document_note_redaction()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if old.redaction_id is null and new.redaction_id is not null then
  update public.wm_archive_notes set redaction_id=new.redaction_id,
    sanitized_note_hash=encode(extensions.digest(convert_to(note_json,'UTF8'),'sha256'),'hex')
   where space_id=new.space_id and document_id=new.id and redaction_id is null;
 end if;
 return new;
end; $$;
drop trigger if exists wm_archive_document_note_redaction on public.wm_archive_documents;
create trigger wm_archive_document_note_redaction after update of redaction_id on public.wm_archive_documents
 for each row execute function public.wm_archive_document_note_redaction();

-- Purge/finalize deliberately remain SECURITY INVOKER and are executable only
-- by service_role.  Grant exactly the writes those owner-checked functions
-- perform; archive/original rows remain inaccessible to browser roles.
grant update on public.wm_source_versions,public.wm_journal,public.wm_archive_documents,public.wm_archive_notes,
 public.wm_job_decisions,public.wm_source_deletions to service_role;
grant insert,update,delete on public.wm_source_deletion_plan to service_role;
grant execute on function public.wm_source_deletion_candidate_rows(uuid) to service_role;

-- A document that was redacted can retain its content hash for the deletion
-- ledger, but it can never be scheduled for another model run.  An active
-- deletion also fences a newly arriving enqueue until the deletion finishes.
create or replace function public.wm_enqueue(p_space_id uuid,p_document_id text,p_pipeline text)
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
 if d.redaction_id is not null or d.body is null then
  return jsonb_build_object('state','archive_only','reason','source_deleted','deleted',true);
 end if;
 if exists(select 1 from public.wm_source_deletions x where x.space_id=p_space_id and x.source_id=d.source_id and x.state in ('prepared','purging')) then
  return jsonb_build_object('state','archive_only','reason','source_deletion_in_progress','deleted',false);
 end if;
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

-- Claim holds the same space lock as stage.  The predicate covers the
-- stage-before-claim ordering, while stage rejects an already-running job.
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
 select j0.* into j from public.wm_jobs j0
 join public.wm_archive_documents d on d.space_id=j0.space_id and d.id=j0.document_id
 where j0.space_id=p_space_id and j0.state not in ('applied','archived')
   and d.redaction_id is null and d.body is not null
   and not exists(select 1 from public.wm_source_deletions x where x.space_id=j0.space_id and x.source_id=j0.source_id and x.state in ('prepared','purging'))
 order by j0.event_date,j0.created_at,j0.id limit 1 for update of j0;
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
