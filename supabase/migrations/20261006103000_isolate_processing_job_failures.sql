-- Technical quarantine is evidence-bound review, never applied/archive or an owner decision.
-- A missing, stale, or changed proof retains the existing global chronology fence.
create table public.wm_job_isolations (
  space_id uuid not null,
  job_id text not null,
  source_id text not null,
  body_hash text not null check (body_hash ~ '^[0-9a-f]{64}$'),
  pipeline text not null,
  expected_revision bigint not null,
  reason text not null check (reason in ('validation_failed','provider_outcome_unknown','context_changed','attempt_limit')),
  observed_revision bigint not null,
  prepared_hash text not null check (prepared_hash ~ '^[0-9a-f]{64}$'),
  call_count integer not null check (call_count >= 0),
  call_evidence_hash text not null check (call_evidence_hash ~ '^[0-9a-f]{64}$'),
  job_updated_at timestamptz not null,
  isolated_at timestamptz not null default clock_timestamp(),
  primary key (space_id,job_id),
  foreign key (space_id,job_id) references public.wm_jobs(space_id,id)
);
alter table public.wm_job_isolations enable row level security;
revoke all on public.wm_job_isolations from public,anon,authenticated,service_role;
grant select,insert on public.wm_job_isolations to service_role;

create function public.wm_job_call_evidence(p_space_id uuid,p_job_id text)
returns text language sql stable security invoker set search_path='' as $$
 select encode(extensions.digest(convert_to(coalesce(jsonb_agg(
   jsonb_build_array(call_index,request_hash,response_hash,reserved_micro_usd,actual_micro_usd)
   order by call_index),'[]'::jsonb)::text,'UTF8'),'sha256'),'hex')
 from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id;
$$;


create function public.wm_job_calls_intact(p_space_id uuid,p_job_id text)
returns boolean language sql stable security invoker set search_path='' as $$
 select not exists(select 1 from public.wm_model_calls c
   where c.space_id=p_space_id and c.job_id=p_job_id
     and (c.request_hash is distinct from encode(extensions.digest(convert_to(c.request_json,'UTF8'),'sha256'),'hex')
       or (c.response_json is not null and c.response_hash is distinct from
         encode(extensions.digest(convert_to(c.response_json,'UTF8'),'sha256'),'hex'))));
$$;

-- Only a reserved call without receipt or a saved, explicitly recognized
-- transport-loss envelope qualifies. A known HTTP rejection is a shared
-- provider stop, and an unfamiliar error is not an isolation proof.
create function public.wm_job_has_unknown_provider_outcome(p_space_id uuid,p_job_id text)
returns boolean language sql stable security invoker set search_path='' as $$
 select exists(select 1 from public.wm_model_calls c
   where c.space_id=p_space_id and c.job_id=p_job_id
     and (c.response_json is null or (
       c.response_json::jsonb->>'error' in
         ('URLError','TimeoutError','OSError','ConnectionResetError','ValueError','JSONDecodeError','EOFError')
       and c.response_json::jsonb->>'usage_final'='false'
       and c.response_json::jsonb->>'terminal_status' is null
       and c.response_json::jsonb->>'stop_reason' is null)));
$$;

create function public.wm_job_isolation_valid(p_space_id uuid,p_job_id text)
returns boolean language sql stable security invoker set search_path='' as $$
 select exists (
  select 1 from public.wm_job_isolations a
  join public.wm_jobs j on j.space_id=a.space_id and j.id=a.job_id
  join public.wm_archive_documents d on d.space_id=j.space_id and d.id=j.document_id
  where a.space_id=p_space_id and a.job_id=p_job_id
    and j.state='review' and j.reason=a.reason and j.updated_at=a.job_updated_at
    and j.source_id=a.source_id and j.pipeline=a.pipeline
    and j.expected_revision=a.expected_revision and a.observed_revision>=a.expected_revision
    and a.prepared_hash=encode(extensions.digest(convert_to(coalesce(j.prepared_payload::text,'null'),'UTF8'),'sha256'),'hex')
    and d.source_id=a.source_id and d.body_hash=a.body_hash
    and d.redaction_id is null and d.body is not null
    and d.body_hash=encode(extensions.digest(convert_to(d.body,'UTF8'),'sha256'),'hex')
    and j.id=encode(extensions.digest(convert_to(d.source_id||':'||d.body_hash,'UTF8'),'sha256'),'hex')
    and a.call_count=(select count(*) from public.wm_model_calls c where c.space_id=j.space_id and c.job_id=j.id)
    and a.call_evidence_hash=public.wm_job_call_evidence(j.space_id,j.id)
    and public.wm_job_calls_intact(j.space_id,j.id)
    and ((a.reason='provider_outcome_unknown' and a.observed_revision=a.expected_revision and j.prepared_payload is null
       and public.wm_job_has_unknown_provider_outcome(j.space_id,j.id))
      or (a.reason='validation_failed' and j.prepared_payload is null
       and a.observed_revision=a.expected_revision and not public.wm_job_has_unknown_provider_outcome(j.space_id,j.id))
      or (a.reason='context_changed' and a.observed_revision>a.expected_revision and not public.wm_job_has_unknown_provider_outcome(j.space_id,j.id))
      or (a.reason='attempt_limit' and j.attempts>=3 and a.observed_revision=a.expected_revision and not public.wm_job_has_unknown_provider_outcome(j.space_id,j.id)))
 );
$$;

-- The worker only asks for this after verifying the original and entering
-- source-specific processing. SQL independently checks source, revision,
-- current lease identity, current call ledger and reason in one transaction.
create function public.wm_isolate_failed_job(
 p_space_id uuid,p_job_id text,p_lease_token uuid,p_reason text,p_body_hash text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype;
 j public.wm_jobs%rowtype; d public.wm_archive_documents%rowtype;
 calls integer; stamp timestamptz;
begin
 if p_job_id is null or p_lease_token is null or p_body_hash is null
    or p_reason not in ('validation_failed','provider_outcome_unknown') then
   return jsonb_build_object('isolated',false,'reason','invalid_evidence');
 end if;
 select * into s from public.wm_spaces where id=p_space_id for update;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if s.id is null or j.id is null or c.space_id is null
    or s.state='retired' or not c.enabled or j.state!='running' or j.lease_token is distinct from p_lease_token
    or j.pipeline is distinct from c.pipeline or j.expected_revision is distinct from s.revision
    or j.prepared_payload is not null or j.applied_revision is not null then
   return jsonb_build_object('isolated',false,'reason','state_or_policy_changed');
 end if;
 select * into d from public.wm_archive_documents where space_id=p_space_id and id=j.document_id;
 if not found or d.redaction_id is not null or d.body is null
    or d.body_hash is distinct from p_body_hash or d.source_id is distinct from j.source_id
    or d.body_hash is distinct from encode(extensions.digest(convert_to(d.body,'UTF8'),'sha256'),'hex')
    or j.id is distinct from encode(extensions.digest(convert_to(d.source_id||':'||d.body_hash,'UTF8'),'sha256'),'hex') then
   return jsonb_build_object('isolated',false,'reason','source_changed');
 end if;
 select count(*) into calls from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id;
 if not public.wm_job_calls_intact(p_space_id,p_job_id)
    or (p_reason='provider_outcome_unknown' and not public.wm_job_has_unknown_provider_outcome(p_space_id,p_job_id))
    or (p_reason='validation_failed' and public.wm_job_has_unknown_provider_outcome(p_space_id,p_job_id))
    or exists(select 1 from public.wm_job_isolations where space_id=p_space_id and job_id=p_job_id) then
   return jsonb_build_object('isolated',false,'reason','call_evidence_changed');
 end if;
 stamp:=clock_timestamp();
 update public.wm_jobs set state='review',reason=p_reason,lease_until=null,
   updated_at=stamp where space_id=p_space_id and id=p_job_id;
 insert into public.wm_job_isolations(
  space_id,job_id,source_id,body_hash,pipeline,expected_revision,reason,
  observed_revision,prepared_hash,call_count,call_evidence_hash,job_updated_at
 ) values(p_space_id,p_job_id,j.source_id,d.body_hash,j.pipeline,j.expected_revision,p_reason,
   s.revision,encode(extensions.digest(convert_to('null','UTF8'),'sha256'),'hex'),
   calls,public.wm_job_call_evidence(p_space_id,p_job_id),stamp);
 if not public.wm_job_isolation_valid(p_space_id,p_job_id) then
   raise exception 'Isolation proof failed after insert' using errcode='40001';
 end if;
 return jsonb_build_object('isolated',true,'state','review','reason',p_reason,'job_id',p_job_id);
end; $$;


-- Used only by wm_claim_job while its space/job locks are held. A stale
-- revision or exhausted per-job attempts is recorded as review, never skipped
-- on an unproven or changed archive/call ledger.
create function public.wm_isolate_claim_failure(
 p_space_id uuid,p_job_id text,p_reason text,p_observed_revision bigint
) returns boolean language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype;
 j public.wm_jobs%rowtype; d public.wm_archive_documents%rowtype;
 stamp timestamptz; calls integer;
begin
 if p_reason not in ('context_changed','attempt_limit') then return false; end if;
 select * into s from public.wm_spaces where id=p_space_id for update;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if s.id is null or j.id is null or c.space_id is null or s.state='retired' or not c.enabled
    or j.state not in ('queued','running','prepared') or j.pipeline is distinct from c.pipeline
    or j.event_date<c.automatic_from or j.expected_revision is null
    or p_observed_revision is distinct from s.revision
    or (j.lease_until is not null and j.lease_until>clock_timestamp())
    or public.wm_job_has_unknown_provider_outcome(p_space_id,p_job_id)
    or not public.wm_job_calls_intact(p_space_id,p_job_id)
    or exists(select 1 from public.wm_job_isolations where space_id=p_space_id and job_id=p_job_id)
    or (p_reason='context_changed' and not (j.expected_revision<s.revision))
    or (p_reason='attempt_limit' and not (j.attempts>=3 and j.expected_revision=s.revision)) then
   return false;
 end if;
 select * into d from public.wm_archive_documents where space_id=p_space_id and id=j.document_id;
 if d.id is null or d.redaction_id is not null or d.body is null
    or d.source_id is distinct from j.source_id or d.body_hash is null
    or d.body_hash is distinct from encode(extensions.digest(convert_to(d.body,'UTF8'),'sha256'),'hex')
    or j.id is distinct from encode(extensions.digest(convert_to(d.source_id||':'||d.body_hash,'UTF8'),'sha256'),'hex')
    or exists(select 1 from public.wm_source_deletions x where x.space_id=p_space_id
      and x.source_id=j.source_id and x.state in ('prepared','purging')) then
   return false;
 end if;
 select count(*) into calls from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id;
 stamp:=clock_timestamp();
 update public.wm_jobs set state='review',reason=p_reason,lease_until=null,updated_at=stamp
 where space_id=p_space_id and id=p_job_id;
 insert into public.wm_job_isolations(
  space_id,job_id,source_id,body_hash,pipeline,expected_revision,reason,
  observed_revision,prepared_hash,call_count,call_evidence_hash,job_updated_at
 ) values(p_space_id,p_job_id,j.source_id,d.body_hash,j.pipeline,j.expected_revision,p_reason,
   s.revision,encode(extensions.digest(convert_to(coalesce(j.prepared_payload::text,'null'),'UTF8'),'sha256'),'hex'),
   calls,public.wm_job_call_evidence(p_space_id,p_job_id),stamp);
 if not public.wm_job_isolation_valid(p_space_id,p_job_id) then
   raise exception 'Claim isolation proof failed after insert' using errcode='40001';
 end if;
 return true;
end; $$;

revoke all on function public.wm_job_call_evidence(uuid,text),
 public.wm_job_calls_intact(uuid,text),public.wm_job_has_unknown_provider_outcome(uuid,text),
 public.wm_job_isolation_valid(uuid,text),
 public.wm_isolate_failed_job(uuid,text,uuid,text,text),
 public.wm_isolate_claim_failure(uuid,text,text,bigint) from public,anon,authenticated;
grant execute on function public.wm_job_call_evidence(uuid,text),
 public.wm_job_calls_intact(uuid,text),public.wm_job_has_unknown_provider_outcome(uuid,text),
 public.wm_job_isolation_valid(uuid,text),
 public.wm_isolate_failed_job(uuid,text,uuid,text,text),
 public.wm_isolate_claim_failure(uuid,text,text,bigint) to service_role;

-- Claim and publish use the same positive predicate. A normal review without
-- a current proof, including human review or unknown state, keeps the fence.
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
   and not public.wm_job_isolation_valid(j0.space_id,j0.id)
 order by j0.event_date,j0.created_at,j0.id limit 1 for update of j0;
 if not found then return jsonb_build_object('state','idle'); end if;
 if j.state='review' then return jsonb_build_object('state','paused','reason',j.reason,'job_id',j.id); end if;
 if exists(select 1 from public.wm_jobs prior where prior.space_id=p_space_id
   and prior.source_id=j.source_id and prior.id!=j.id and prior.state='review') then
   return jsonb_build_object('state','paused','reason','same_source_review','job_id',j.id);
 end if;
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
 if j.expected_revision is not null and j.expected_revision!=s.revision then
   if public.wm_isolate_claim_failure(p_space_id,j.id,'context_changed',s.revision) then
     return jsonb_build_object('state','review','reason','context_changed','job_id',j.id,'technical_isolation',true);
   end if;
   update public.wm_jobs set state='review',reason='context_changed',updated_at=now() where space_id=p_space_id and id=j.id;
   return jsonb_build_object('state','paused','reason','context_changed','job_id',j.id);
 end if;
 if j.attempts>=3 then
   if public.wm_isolate_claim_failure(p_space_id,j.id,'attempt_limit',s.revision) then
     return jsonb_build_object('state','review','reason','attempt_limit','job_id',j.id,'technical_isolation',true);
   end if;
   update public.wm_jobs set state='review',reason='attempt_limit',updated_at=clock_timestamp() where space_id=p_space_id and id=j.id;
   return jsonb_build_object('state','paused','reason','attempt_limit','job_id',j.id);
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
   or exists(select 1 from public.wm_jobs where space_id=p_space_id and state not in ('applied','archived') and event_date<j.event_date
      and not public.wm_job_isolation_valid(p_space_id,id))
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

-- Preserve the existing status function (including recovery accounting) and
-- add explicit, positive markers. The exact replacement is verified; any
-- different prior schema refuses this migration instead of dropping fields.
do $migration$
declare sig regprocedure:='public.wm_processing_status(uuid)'::regprocedure;
 old_definition text; changed text; verified text;
 needle_count text:=$n$'jobs',coalesce($n$;
 add_count text:=$r$'isolated_count',(select count(*) from public.wm_job_isolations i
    where i.space_id=p_space_id and public.wm_job_isolation_valid(i.space_id,i.job_id)),
   'blocking_job',(select jsonb_build_object('id',candidate.id,'source_id',candidate.source_id,
      'event_date',candidate.event_date,'title',candidate.title,'state',candidate.state,'reason',candidate.block_reason,
      'technical_isolation',false)
    from (select j0.id,j0.source_id,j0.event_date,d.title,j0.state,
      case when j0.state='review' then coalesce(j0.reason,'review')
        when j0.pipeline is distinct from (select c.pipeline from public.wm_processing_config c where c.space_id=p_space_id)
          or j0.event_date<(select c.automatic_from from public.wm_processing_config c where c.space_id=p_space_id)
          then 'job_policy_changed'
        when exists(select 1 from public.wm_jobs prior where prior.space_id=j0.space_id
          and prior.source_id=j0.source_id and prior.id!=j0.id and prior.state='review')
          then 'same_source_review' end as block_reason
      from public.wm_jobs j0 join public.wm_archive_documents d
        on d.space_id=j0.space_id and d.id=j0.document_id
      where j0.space_id=p_space_id and j0.state not in ('applied','archived')
        and d.redaction_id is null and d.body is not null
        and not exists(select 1 from public.wm_source_deletions x where x.space_id=j0.space_id
          and x.source_id=j0.source_id and x.state in ('prepared','purging'))
        and not public.wm_job_isolation_valid(j0.space_id,j0.id)
      order by j0.event_date,j0.created_at,j0.id limit 1) candidate
    where candidate.block_reason is not null),
   'jobs',coalesce($r$;
 needle_job text:=$n$j.reason,j.attempts$n$;
 add_job text:=$r$j.reason,public.wm_job_isolation_valid(j.space_id,j.id) as technical_isolation,j.attempts$r$;
begin
 old_definition:=pg_get_functiondef(sig);
 if old_definition is null
   or (length(old_definition)-length(replace(old_definition,needle_count,'')))/length(needle_count)!=1
   or (length(old_definition)-length(replace(old_definition,needle_job,'')))/length(needle_job)!=1 then
   raise exception 'wm_processing_status changed; isolation merge required' using errcode='55000';
 end if;
 changed:=replace(replace(old_definition,needle_count,add_count),needle_job,add_job);
 execute changed;
 verified:=pg_get_functiondef(sig);
 if replace(replace(verified,add_count,needle_count),add_job,needle_job) is distinct from old_definition then
   raise exception 'wm_processing_status isolation merge changed existing fields' using errcode='55000';
 end if;
end $migration$;

-- A known provider-wide HTTP/auth/rate failure is a visible global fence.
create or replace function public.wm_pause_job(p_space_id uuid,p_job_id text,p_lease_token uuid,p_reason text)
returns jsonb language plpgsql security invoker set search_path='' as $$
begin
 if p_reason is null or p_reason not in ('validation_failed','budget_exceeded','provider_outcome_unknown','transport_failed','context_changed','pipeline_changed','provider_shared_failure') then
   raise exception 'Invalid operational reason' using errcode='22023'; end if;
 perform 1 from public.wm_spaces where id=p_space_id for update;
 update public.wm_jobs set state='review',reason=p_reason,updated_at=now()
 where space_id=p_space_id and id=p_job_id and lease_token=p_lease_token and state in ('running','prepared');
 return jsonb_build_object('paused',found);
end; $$;
revoke all on function public.wm_pause_job(uuid,text,uuid,text) from public,anon,authenticated;
grant execute on function public.wm_pause_job(uuid,text,uuid,text) to service_role;

-- Preserve the immutable isolation audit in the existing canonical backup
-- record stream. Physical self-host backups already contain the whole table.
alter table public.wm_backup_records drop constraint wm_backup_records_kind_check;
alter table public.wm_backup_records add constraint wm_backup_records_kind_check check(kind in
 ('config','job','call','job_decision','generation_review','search_document','search_snapshot','search_result',
  'conversation','pipeline_recovery','question','question_call','source_deletion','source_deletion_version',
  'source_deletion_check','source_reimport_authorization','job_isolation'));
do $migration$
declare original text; changed text; verified text;
 sig regprocedure:='public.wm_backup_begin(uuid,uuid)'::regprocedure;
 needle text:=') x;';
 addition text:=E'  union all select ''job_isolation'',to_jsonb(a)::text from public.wm_job_isolations a where a.space_id=p_space_id\n ) x;';
begin
 original:=pg_get_functiondef(sig);
 if original is null or
   (length(original)-length(replace(original,needle,'')))/length(needle)!=1 or
   position('wm_job_isolations' in original)>0 then
   raise exception 'wm_backup_begin changed; isolation merge required' using errcode='55000';
 end if;
 changed:=replace(original,needle,addition);
 execute changed;
 verified:=pg_get_functiondef(sig);
 if replace(verified,addition,needle) is distinct from original then
   raise exception 'wm_backup_begin isolation merge changed existing branches' using errcode='55000';
 end if;
end $migration$;
