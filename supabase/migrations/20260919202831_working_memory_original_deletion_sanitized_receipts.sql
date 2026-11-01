-- Complete, hash-bound sanitization plan for original-only deletion. The
-- service scans every durable context-bearing row before this transaction;
-- purge locks the tables, proves exact coverage, and applies only that plan.
alter table public.wm_model_calls add column sanitized_request_hash text check(sanitized_request_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_model_calls add column sanitized_response_hash text check(sanitized_response_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_questions add column sanitized_request_hash text check(sanitized_request_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_questions add column sanitized_response_hash text check(sanitized_response_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_question_calls add column sanitized_request_hash text check(sanitized_request_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_question_calls add column sanitized_response_hash text check(sanitized_response_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_archive_notes add column sanitized_note_hash text check(sanitized_note_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_jobs add column redaction_id uuid;
alter table public.wm_jobs add column original_prepared_payload_hash text check(original_prepared_payload_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_job_decisions add column redaction_id uuid;
alter table public.wm_job_decisions add column original_payload_hashes jsonb check(jsonb_typeof(original_payload_hashes)='object');

alter table public.wm_model_calls drop constraint wm_model_calls_check;
alter table public.wm_model_calls add constraint wm_model_calls_check check(
 (request_json is not null or redaction_id is not null)
 and (response_json is null or received_at is not null)
 and (received_at is null or response_hash is not null)
 and (received_at is not null or (response_json is null and response_hash is null and actual_micro_usd is null)));
alter table public.wm_questions drop constraint wm_questions_check;
alter table public.wm_questions add constraint wm_questions_check check(
 (request_json is not null or redaction_id is not null)
 and (completed_at is null or response_hash is not null)
 and (completed_at is not null or (response_json is null and response_hash is null)));
alter table public.wm_question_calls drop constraint wm_question_calls_check;
alter table public.wm_question_calls add constraint wm_question_calls_check check(
 (request_json is not null or redaction_id is not null)
 and (received_at is null or response_hash is not null)
 and (received_at is not null or (response_json is null and response_hash is null and actual_micro_usd is null)));

create table public.wm_source_deletion_plan (
 space_id uuid not null, deletion_id uuid not null, scope text not null,
 record_key text not null check(length(record_key) between 1 and 256),
 before_hash text not null check(before_hash ~ '^[0-9a-f]{64}$'),
 replacement jsonb not null check(jsonb_typeof(replacement)='object'),
 replacement_hash text not null check(replacement_hash ~ '^[0-9a-f]{64}$'),
 scan_receipt jsonb not null check(jsonb_typeof(scan_receipt)='object'),
 planned_at timestamptz not null default clock_timestamp(),
 primary key(space_id,deletion_id,scope,record_key),
 foreign key(space_id,deletion_id) references public.wm_source_deletions(space_id,id),
 check(scope in ('archive_note','prepared_job','model_call','question','question_call',
   'generation_review','journal_generation','job_decision'))
);
alter table public.wm_source_deletion_plan enable row level security;
revoke all on public.wm_source_deletion_plan from public,anon,authenticated,service_role;
grant select,insert on public.wm_source_deletion_plan to service_role;

create function public.wm_source_deletion_candidate_rows(p_space_id uuid)
returns table(scope text,record_key text,data jsonb) language sql stable security invoker set search_path='' as $$
 select 'archive_note',n.id,jsonb_build_object('note_json',n.note_json) from public.wm_archive_notes n where n.space_id=p_space_id
 union all select 'prepared_job',j.id,jsonb_build_object('prepared_payload',j.prepared_payload) from public.wm_jobs j where j.space_id=p_space_id
 union all select 'model_call',c.job_id||':'||c.call_index,jsonb_build_object('request_json',c.request_json,'response_json',c.response_json) from public.wm_model_calls c where c.space_id=p_space_id
 union all select 'question',q.id::text,jsonb_build_object('request_json',q.request_json,'response_json',q.response_json) from public.wm_questions q where q.space_id=p_space_id
 union all select 'question_call',q.question_id::text||':'||q.call_index,jsonb_build_object('request_json',q.request_json,'response_json',q.response_json) from public.wm_question_calls q where q.space_id=p_space_id
 union all select 'generation_review',g.id::text,jsonb_build_object('payload',g.payload,'decision_result',g.decision_result) from public.wm_generation_reviews g where g.space_id=p_space_id
 union all select 'journal_generation',j.revision::text,jsonb_build_object('payload',j.payload) from public.wm_journal j where j.space_id=p_space_id and j.kind in ('generation','redaction')
 union all select 'job_decision',d.command_id::text,jsonb_build_object('request',d.request,'previous_job',d.previous_job,'result',d.result) from public.wm_job_decisions d where d.space_id=p_space_id;
$$;

create function public.wm_source_deletion_candidates(p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_after text default '')
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare d public.wm_source_deletions%rowtype; result jsonb;
begin
 select d0.* into d from public.wm_source_deletions d0 join public.wm_spaces s on s.id=d0.space_id
 where d0.space_id=p_space_id and d0.id=p_deletion_id and s.owner_id=p_actor_id;
 if not found or d.state!='prepared' then raise exception 'Prepared owner deletion required' using errcode='42501'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('scope',scope,'record_key',record_key,'data',data,
   'before_hash',encode(extensions.digest(convert_to(data::text,'UTF8'),'sha256'),'hex')) order by scope,record_key),'[]'::jsonb)
 into result from (select * from public.wm_source_deletion_candidate_rows(p_space_id)
   where scope||'|'||record_key>p_after order by scope,record_key limit 32) rows;
 return result;
end; $$;

create function public.wm_source_deletion_inputs(p_space_id uuid,p_source_id text,p_actor_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if not exists(select 1 from public.wm_spaces where id=p_space_id and owner_id=p_actor_id and state!='retired') then
  raise exception 'Owner required' using errcode='42501'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('kind','source','source',to_jsonb(v)-'space_id'-'redaction_id',
   'payload',j.payload) order by v.event_date,v.observed_at,v.id),'[]'::jsonb) into result
 from public.wm_source_versions v join public.wm_journal j on j.space_id=v.space_id and j.source_version=v.id and j.kind='source'
 where v.space_id=p_space_id and v.source_id=p_source_id and v.redaction_id is null;
 return result;
end; $$;

create function public.wm_source_deletion_ledger(p_space_id uuid,p_actor_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if not exists(select 1 from public.wm_spaces where id=p_space_id and owner_id=p_actor_id) then
  raise exception 'Owner required' using errcode='42501'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('deletion_id',id,'source_id',source_id,'state',state,
   'ledger_revision',ledger_revision) order by requested_at,id),'[]'::jsonb) into result
 from public.wm_source_deletions where space_id=p_space_id;
 return result;
end; $$;

-- Restart-safe worker view. It contains evidence-only redaction packages and
-- verification receipts, never a deleted transcript or archive body.
create function public.wm_source_deletion_status(p_space_id uuid,p_deletion_id uuid,p_actor_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if not exists(select 1 from public.wm_spaces where id=p_space_id and owner_id=p_actor_id) then
  raise exception 'Owner required' using errcode='42501'; end if;
 select jsonb_build_object('deletion_id',d.id,'source_id',d.source_id,'state',d.state,
   'ledger_revision',d.ledger_revision,'requested_at',d.requested_at,'completed_at',d.completed_at,
   'packages',(select coalesce(jsonb_agg(v.redaction_package order by v.source_version),'[]'::jsonb)
     from public.wm_source_deletion_versions v where v.space_id=d.space_id and v.deletion_id=d.id),
   'checks',(select coalesce(jsonb_object_agg(c.scope,c.receipt),'{}'::jsonb)
     from public.wm_source_deletion_checks c where c.space_id=d.space_id and c.deletion_id=d.id))
 into result from public.wm_source_deletions d where d.space_id=p_space_id and d.id=p_deletion_id;
 return result;
end; $$;

create function public.wm_source_deletion_plan_put(p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,
 p_scope text,p_record_key text,p_before_hash text,p_replacement jsonb,p_scan_receipt jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare d public.wm_source_deletions%rowtype; current_data jsonb; actual text; replacement_digest text;
begin
 select d0.* into d from public.wm_source_deletions d0 join public.wm_spaces s on s.id=d0.space_id
 where d0.space_id=p_space_id and d0.id=p_deletion_id and s.owner_id=p_actor_id for update of d0;
 if not found or d.state!='prepared' then raise exception 'Prepared owner deletion required' using errcode='42501'; end if;
 select data into current_data from public.wm_source_deletion_candidate_rows(p_space_id)
  where scope=p_scope and record_key=p_record_key;
 actual:=encode(extensions.digest(convert_to(current_data::text,'UTF8'),'sha256'),'hex');
 if current_data is null or actual is distinct from p_before_hash or p_replacement is null
    or jsonb_typeof(p_replacement)!='object' or p_scan_receipt is null or jsonb_typeof(p_scan_receipt)!='object'
    or jsonb_typeof(p_scan_receipt->'changed')!='boolean'
    or coalesce(p_scan_receipt->>'removed_characters','') !~ '^[0-9]+$'
    or octet_length(p_replacement::text)>3900000 then
  raise exception 'Invalid or stale sanitization plan' using errcode='40001'; end if;
 if (select array_agg(key order by key) from jsonb_object_keys(current_data) key)
    is distinct from (select array_agg(key order by key) from jsonb_object_keys(p_replacement) key) then
  raise exception 'Sanitization plan changed record shape' using errcode='22023'; end if;
 replacement_digest:=encode(extensions.digest(convert_to(p_replacement::text,'UTF8'),'sha256'),'hex');
 insert into public.wm_source_deletion_plan(space_id,deletion_id,scope,record_key,before_hash,replacement,replacement_hash,scan_receipt)
 values(p_space_id,p_deletion_id,p_scope,p_record_key,p_before_hash,p_replacement,replacement_digest,p_scan_receipt)
 on conflict(space_id,deletion_id,scope,record_key) do update set
  before_hash=excluded.before_hash,replacement=excluded.replacement,replacement_hash=excluded.replacement_hash,
  scan_receipt=excluded.scan_receipt,planned_at=clock_timestamp();
 return jsonb_build_object('scope',p_scope,'record_key',p_record_key,'replacement_hash',replacement_digest);
end; $$;

create or replace function public.wm_source_deletion_purge(
 p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_command_id uuid,p_projection_snapshot jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; d public.wm_source_deletions%rowtype; existing public.wm_journal%rowtype;
 package jsonb; p public.wm_source_deletion_plan%rowtype; current_data jsonb; current_hash text;
 request_hash text; receipt jsonb; target_search_ids text[]; affected bigint; changed bigint:=0;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 select * into d from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id for update;
 if not found or d.actor_id is distinct from p_actor_id then raise exception 'Deletion ledger unavailable' using errcode='22023'; end if;
 select * into existing from public.wm_journal where space_id=p_space_id and command_id=p_command_id;
 if found then
  if existing.kind!='redaction' or existing.redaction_id is distinct from p_deletion_id then raise exception 'Deletion command identity reused' using errcode='23505'; end if;
  return jsonb_build_object('deletion_id',p_deletion_id,'state',d.state,'revision',existing.revision,'repeated',true);
 end if;
 if d.state!='prepared' then raise exception 'Deletion is not prepared' using errcode='40001'; end if;
 if exists(select 1 from public.wm_backup_snapshots b where b.space_id=p_space_id)
    or exists(select 1 from public.wm_jobs where space_id=p_space_id and state in ('running','prepared'))
    or exists(select 1 from public.wm_model_calls where space_id=p_space_id and response_json is null)
    or exists(select 1 from public.wm_question_calls where space_id=p_space_id and response_json is null) then
  raise exception 'Active work or backup snapshot blocks source purge' using errcode='40001'; end if;
 if p_command_id is null or p_projection_snapshot is null
    or p_projection_snapshot->>'format' is distinct from 'wm-projection-snapshot-v1'
    or coalesce(p_projection_snapshot->>'snapshot_sha256','') !~ '^[0-9a-f]{64}$'
    or coalesce(p_projection_snapshot->>'rows_sha256','') !~ '^[0-9a-f]{64}$'
    or coalesce(p_projection_snapshot->>'state_sha256','') !~ '^[0-9a-f]{64}$'
    or coalesce(p_projection_snapshot->>'logical_basis_sha256','') !~ '^[0-9a-f]{64}$'
    or coalesce(p_projection_snapshot->>'through_revision','') !~ '^[0-9]+$'
    or (p_projection_snapshot->>'through_revision')::bigint is distinct from s.revision
    or jsonb_typeof(p_projection_snapshot->'tables')!='object'
    or jsonb_typeof(p_projection_snapshot->'logical_basis')!='array'
    or jsonb_typeof(p_projection_snapshot->'deletions')!='array'
    or octet_length(p_projection_snapshot::text)>3900000
    -- The checkpoint is cumulative across distinct deleted sources.  An
    -- explicitly reimported source can have several historical epochs; only
    -- its newest effective epoch belongs in the replay basis.
    or jsonb_array_length(p_projection_snapshot->'deletions') is distinct from (
      select count(*) from public.wm_source_deletions expected
      where expected.space_id=p_space_id
        and (expected.id=p_deletion_id or expected.state in ('purging','verified'))
        and not exists(
          select 1 from public.wm_source_deletions newer
          where newer.space_id=expected.space_id and newer.source_id=expected.source_id
            and (newer.id=p_deletion_id or newer.state in ('purging','verified'))
            and (newer.ledger_revision,newer.id)>(expected.ledger_revision,expected.id)))
    or exists(
      select 1 from jsonb_array_elements(p_projection_snapshot->'deletions') x
      where jsonb_typeof(x)!='object' or not exists(
        select 1 from public.wm_source_deletions expected
        where expected.space_id=p_space_id and expected.id::text=x->>'deletion_id'
          and expected.source_id=x->>'source_id'
          and (expected.id=p_deletion_id or expected.state in ('purging','verified'))
          and not exists(
            select 1 from public.wm_source_deletions newer
            where newer.space_id=expected.space_id and newer.source_id=expected.source_id
              and (newer.id=p_deletion_id or newer.state in ('purging','verified'))
              and (newer.ledger_revision,newer.id)>(expected.ledger_revision,expected.id)))) then
  raise exception 'Invalid verified projection snapshot' using errcode='22023'; end if;

 lock table public.wm_archive_notes,public.wm_jobs,public.wm_model_calls,public.wm_questions,
  public.wm_question_calls,public.wm_generation_reviews,public.wm_journal,public.wm_job_decisions,
  public.wm_search_documents,public.wm_search_snapshots,public.wm_search_results in share row exclusive mode;
 if exists(select 1 from public.wm_source_deletion_candidate_rows(p_space_id) c left join public.wm_source_deletion_plan p0
      on p0.space_id=p_space_id and p0.deletion_id=p_deletion_id and p0.scope=c.scope and p0.record_key=c.record_key
      where p0.record_key is null or p0.before_hash!=encode(extensions.digest(convert_to(c.data::text,'UTF8'),'sha256'),'hex'))
    or exists(select 1 from public.wm_source_deletion_plan p0 left join public.wm_source_deletion_candidate_rows(p_space_id) c
      on c.scope=p0.scope and c.record_key=p0.record_key where p0.space_id=p_space_id and p0.deletion_id=p_deletion_id and c.record_key is null) then
  raise exception 'Sanitization plan does not exactly cover the locked database state' using errcode='40001'; end if;

 for p in select * from public.wm_source_deletion_plan where space_id=p_space_id and deletion_id=p_deletion_id order by scope,record_key loop
  select data into current_data from public.wm_source_deletion_candidate_rows(p_space_id) where scope=p.scope and record_key=p.record_key;
  current_hash:=encode(extensions.digest(convert_to(current_data::text,'UTF8'),'sha256'),'hex');
  if current_hash!=p.before_hash then raise exception 'Sanitization candidate changed' using errcode='40001'; end if;
  if p.replacement is not distinct from current_data then continue; end if;
  changed:=changed+1;
  if p.scope='archive_note' then
   update public.wm_archive_notes set note_json=p.replacement->>'note_json',sanitized_note_hash=encode(extensions.digest(convert_to(p.replacement->>'note_json','UTF8'),'sha256'),'hex'),redaction_id=p_deletion_id where space_id=p_space_id and id=p.record_key;
  elsif p.scope='prepared_job' then
   update public.wm_jobs set original_prepared_payload_hash=case when prepared_payload is null then null else encode(extensions.digest(convert_to(prepared_payload::text,'UTF8'),'sha256'),'hex') end,prepared_payload=p.replacement->'prepared_payload',redaction_id=p_deletion_id where space_id=p_space_id and id=p.record_key;
  elsif p.scope='model_call' then
   -- Provider responses are internal receipts, not the user-visible answer.
   -- Clearing a touched response keeps the later completed-call reference
   -- migration fail-closed while request/response hashes and cost remain.
   update public.wm_model_calls set request_json=p.replacement->>'request_json',response_json=null,
    sanitized_request_hash=case when p.replacement->>'request_json' is null then null else encode(extensions.digest(convert_to(p.replacement->>'request_json','UTF8'),'sha256'),'hex') end,
    sanitized_response_hash=null,
    redaction_id=p_deletion_id,redacted_at=clock_timestamp()
    where space_id=p_space_id and job_id=split_part(p.record_key,':',1) and call_index=split_part(p.record_key,':',2)::integer;
  elsif p.scope='question' then
   update public.wm_questions set request_json=p.replacement->>'request_json',response_json=p.replacement->>'response_json',
    sanitized_request_hash=case when p.replacement->>'request_json' is null then null else encode(extensions.digest(convert_to(p.replacement->>'request_json','UTF8'),'sha256'),'hex') end,
    sanitized_response_hash=case when p.replacement->>'response_json' is null then null else encode(extensions.digest(convert_to(p.replacement->>'response_json','UTF8'),'sha256'),'hex') end,redaction_id=p_deletion_id
    where space_id=p_space_id and id=p.record_key::uuid;
  elsif p.scope='question_call' then
   update public.wm_question_calls set request_json=p.replacement->>'request_json',response_json=p.replacement->>'response_json',
    sanitized_request_hash=case when p.replacement->>'request_json' is null then null else encode(extensions.digest(convert_to(p.replacement->>'request_json','UTF8'),'sha256'),'hex') end,
    sanitized_response_hash=case when p.replacement->>'response_json' is null then null else encode(extensions.digest(convert_to(p.replacement->>'response_json','UTF8'),'sha256'),'hex') end,redaction_id=p_deletion_id
    where space_id=p_space_id and question_id=split_part(p.record_key,':',1)::uuid and call_index=split_part(p.record_key,':',2)::integer;
  elsif p.scope='generation_review' then
   update public.wm_generation_reviews set original_payload_hash=encode(extensions.digest(convert_to(payload::text,'UTF8'),'sha256'),'hex'),
    payload=jsonb_build_object('format','wm-redacted-generation-v1','deletion_id',p_deletion_id,
      'sanitized_payload',p.replacement->'payload'),decision_result=p.replacement->'decision_result',redaction_id=p_deletion_id
    where space_id=p_space_id and id=p.record_key::uuid;
  elsif p.scope='journal_generation' then
   update public.wm_journal set original_payload_hash=encode(extensions.digest(convert_to(payload::text,'UTF8'),'sha256'),'hex'),
    payload=jsonb_build_object('format','wm-redacted-generation-v1','deletion_id',p_deletion_id,
      'sanitized_payload',p.replacement->'payload'),redaction_id=p_deletion_id
    where space_id=p_space_id and revision=p.record_key::bigint;
  elsif p.scope='job_decision' then
   update public.wm_job_decisions set original_payload_hashes=jsonb_build_object(
    'request',encode(extensions.digest(convert_to(request::text,'UTF8'),'sha256'),'hex'),
    'previous_job',encode(extensions.digest(convert_to(previous_job::text,'UTF8'),'sha256'),'hex'),
    'result',encode(extensions.digest(convert_to(result::text,'UTF8'),'sha256'),'hex')),
    request=p.replacement->'request',previous_job=p.replacement->'previous_job',result=p.replacement->'result',redaction_id=p_deletion_id
    where space_id=p_space_id and command_id=p.record_key::uuid;
  end if;
 end loop;

 for package in select redaction_package from public.wm_source_deletion_versions where space_id=p_space_id and deletion_id=p_deletion_id order by source_version loop
  if package->>'format'!='wm-redacted-source-v1'
     or encode(extensions.digest(convert_to((package->'source'->>'source_id')||':'||(package->'source'->>'content_hash'),'UTF8'),'sha256'),'hex')!=package->'source'->>'id'
     or exists(select 1 from jsonb_array_elements(package->'evidence_manifest'->'entries') e where
       encode(extensions.digest(convert_to(e->>'quote','UTF8'),'sha256'),'hex')!=e->>'quote_sha256')
     or package->'retained_payload'->>'result_sha256' is distinct from package->'attestation'->>'accepted_result_sha256' then
   raise exception 'Redaction package integrity failed' using errcode='22023'; end if;
  update public.wm_journal set original_payload_hash=package->'attestation'->>'accepted_payload_sha256',payload=package->'retained_payload',redaction_id=p_deletion_id
   where space_id=p_space_id and kind='source' and source_version=package->'source'->>'id';
 end loop;

 select coalesce(array_agg(id),'{}') into target_search_ids from public.wm_search_documents where space_id=p_space_id and source_id=d.source_id;
 delete from public.wm_search_results r where r.space_id=p_space_id and exists(select 1 from public.wm_search_snapshots ss where ss.space_id=r.space_id and ss.id=r.snapshot_id and ss.document_ids&&target_search_ids);
 get diagnostics affected=row_count;
 delete from public.wm_search_snapshots where space_id=p_space_id and document_ids&&target_search_ids;
 delete from public.wm_search_documents where space_id=p_space_id and id=any(target_search_ids);
 receipt:=jsonb_build_object('target_documents',cardinality(target_search_ids),'affected_results',affected,'controlled_rebuild_required',true);
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'search_documents',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'search_results',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());

 update public.wm_archive_documents set body=null,export=null,redaction_id=p_deletion_id where space_id=p_space_id and source_id=d.source_id and redaction_id is null;
 get diagnostics affected=row_count;receipt:=jsonb_build_object('original_bodies_removed',affected);
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'archive_documents',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 update public.wm_source_versions set transcript=null,redaction_id=p_deletion_id where space_id=p_space_id and source_id=d.source_id and redaction_id is null;
 get diagnostics affected=row_count;receipt:=jsonb_build_object('projection_transcripts_removed',affected);
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'source_versions',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());

 receipt:=jsonb_build_object('planned_records',(select count(*) from public.wm_source_deletion_plan where space_id=p_space_id and deletion_id=p_deletion_id),'changed_records',changed);
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'archive_notes',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'prepared_jobs',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'model_receipts',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'question_receipts',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'generation_payloads',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,'journal_payloads',receipt,encode(extensions.digest(convert_to(receipt::text,'UTF8'),'sha256'),'hex'),clock_timestamp());

 request_hash:=encode(extensions.digest(convert_to(jsonb_build_object('kind','redaction','payload',p_projection_snapshot,'actor_id',p_actor_id,'deletion_id',p_deletion_id)::text,'UTF8'),'sha256'),'hex');
 insert into public.wm_journal(space_id,revision,command_id,request_hash,kind,actor_id,payload,redaction_id)
 values(p_space_id,s.revision+1,p_command_id,request_hash,'redaction',p_actor_id,p_projection_snapshot,p_deletion_id);
 update public.wm_spaces set revision=revision+1,deletion_revision=deletion_revision+1 where id=p_space_id;
 update public.wm_source_deletions set state='purging' where space_id=p_space_id and id=p_deletion_id;
 delete from public.wm_source_deletion_plan where space_id=p_space_id and deletion_id=p_deletion_id;
 return jsonb_build_object('deletion_id',p_deletion_id,'state','purging','revision',s.revision+1,'repeated',false,
  'external_checks',jsonb_build_array('local_caches','backup_sets'));
end; $$;

-- After reimport, a new deletion epoch covers only currently live versions.
create or replace function public.wm_source_deletion_stage(
 p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_source_id text,p_packages jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; previous public.wm_source_deletions%rowtype; request_hash text; package jsonb;
 expected_versions text[]; supplied_versions text[]; archive_ids text[]; content_hashes text[];
 required constant text[]:=array['archive_documents','archive_notes','source_versions','journal_payloads','generation_payloads','prepared_jobs','model_receipts','question_receipts','search_documents','search_results','local_caches','backup_sets'];
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 request_hash:=encode(extensions.digest(convert_to(jsonb_build_object('actor_id',p_actor_id,'source_id',p_source_id,'packages',p_packages)::text,'UTF8'),'sha256'),'hex');
 select * into previous from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id;
 if found then if previous.request_hash!=request_hash then raise exception 'Deletion identity reused' using errcode='23505'; end if; return jsonb_build_object('deletion_id',previous.id,'state',previous.state,'repeated',true); end if;
 if exists(select 1 from public.wm_source_deletions where space_id=p_space_id and source_id=p_source_id and state in ('prepared','purging')) then raise exception 'Source identity already has an active deletion' using errcode='23505'; end if;
 select coalesce(array_agg(v.id order by v.id),'{}') into expected_versions from public.wm_source_versions v where v.space_id=p_space_id and v.source_id=p_source_id and v.redaction_id is null;
 select coalesce(array_agg(value->'source'->>'id' order by value->'source'->>'id'),'{}') into supplied_versions from jsonb_array_elements(p_packages);
 if expected_versions is distinct from supplied_versions or cardinality(expected_versions)=0 then raise exception 'Every live source version needs one redaction package' using errcode='22023'; end if;
 for package in select value from jsonb_array_elements(p_packages) loop
  if package->>'format'!='wm-redacted-source-v1' or package->'source'->>'source_id' is distinct from p_source_id
    or encode(extensions.digest(convert_to((package->'source'->>'source_id')||':'||(package->'source'->>'content_hash'),'UTF8'),'sha256'),'hex')!=package->'source'->>'id'
    or exists(select 1 from jsonb_array_elements(package->'evidence_manifest'->'entries') e where encode(extensions.digest(convert_to(e->>'quote','UTF8'),'sha256'),'hex')!=e->>'quote_sha256')
    or not exists(select 1 from public.wm_source_versions v where v.space_id=p_space_id and v.id=package->'source'->>'id' and v.source_id=p_source_id and v.content_hash=package->'source'->>'content_hash' and v.redaction_id is null)
   then raise exception 'Invalid redaction package' using errcode='22023'; end if;
 end loop;
 select coalesce(array_agg(d.id order by d.id),'{}') into archive_ids from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id and d.redaction_id is null;
 select coalesce(array_agg(distinct h order by h),'{}') into content_hashes from (
  select v.content_hash h from public.wm_source_versions v where v.space_id=p_space_id and v.source_id=p_source_id and v.redaction_id is null
  union select d.body_hash from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id and d.redaction_id is null) hashes;
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=p_space_id returning deletion_revision into s.deletion_revision;
 insert into public.wm_source_deletions(space_id,id,source_id,actor_id,request_hash,ledger_revision,archive_document_ids,original_content_hashes,required_scopes)
 values(p_space_id,p_deletion_id,p_source_id,p_actor_id,request_hash,s.deletion_revision,archive_ids,content_hashes,required);
 for package in select value from jsonb_array_elements(p_packages) loop
  insert into public.wm_source_deletion_versions values(p_space_id,p_deletion_id,package->'source'->>'id',package->'source'->>'content_hash',package,encode(extensions.digest(convert_to(package::text,'UTF8'),'sha256'),'hex'));
 end loop;
 return jsonb_build_object('deletion_id',p_deletion_id,'state','prepared','repeated',false,'processed_versions',cardinality(expected_versions),'archive_documents',cardinality(archive_ids));
end; $$;

-- Active copies are gone before this check. Old offline sets may age out under
-- retention, but an independently current monotonic restore ledger is required.
create or replace function public.wm_source_deletion_check(p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_scope text,p_receipt jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; d public.wm_source_deletions%rowtype; prior public.wm_source_deletion_checks%rowtype; h text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 select * into d from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id;
 if not found or d.state!='purging' or p_scope not in ('local_caches','backup_sets') or p_receipt is null or jsonb_typeof(p_receipt)!='object' then raise exception 'Invalid external deletion check' using errcode='22023'; end if;
 if p_scope='local_caches' and (p_receipt->>'rebuilt'!='true' or p_receipt->>'canary_scan_clear'!='true') then raise exception 'Local cache rebuild is not attested' using errcode='22023'; end if;
 if p_scope='backup_sets' and (p_receipt->>'restore_ledger_persisted'!='true' or p_receipt->>'retention_policy' is distinct from '14-latest-plus-8-observed-weeks' or coalesce(p_receipt->>'minimum_deletion_revision','') !~ '^[0-9]+$' or (p_receipt->>'minimum_deletion_revision')::bigint<s.deletion_revision) then raise exception 'Independent restore watermark is not attested' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_receipt::text,'UTF8'),'sha256'),'hex');
 select * into prior from public.wm_source_deletion_checks where space_id=p_space_id and deletion_id=p_deletion_id and scope=p_scope;
 if found then if prior.receipt_hash!=h then raise exception 'Deletion check identity reused' using errcode='23505'; end if; return jsonb_build_object('scope',p_scope,'repeated',true); end if;
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,p_scope,p_receipt,h,clock_timestamp());
 return jsonb_build_object('scope',p_scope,'repeated',false);
end; $$;

create or replace function public.wm_source_deletion_finalize(p_space_id uuid,p_deletion_id uuid,p_actor_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; d public.wm_source_deletions%rowtype;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 select * into d from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id for update;
 if not found then raise exception 'Deletion ledger unavailable' using errcode='22023'; end if;
 if d.state='verified' then return jsonb_build_object('deletion_id',p_deletion_id,'state','verified','repeated',true); end if;
 if d.state!='purging' or exists(select 1 from public.wm_backup_snapshots b where b.space_id=p_space_id)
   or (select array_agg(scope order by scope) from public.wm_source_deletion_checks where space_id=p_space_id and deletion_id=p_deletion_id)
      is distinct from (select array_agg(scope order by scope) from unnest(d.required_scopes) scope)
   or exists(select 1 from public.wm_source_versions where space_id=p_space_id and source_id=d.source_id and redaction_id is null)
   or exists(select 1 from public.wm_archive_documents where space_id=p_space_id and source_id=d.source_id and redaction_id is null)
   or exists(select 1 from public.wm_search_documents where space_id=p_space_id and source_id=d.source_id)
  then raise exception 'Deletion verification is incomplete' using errcode='40001'; end if;
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=p_space_id returning deletion_revision into s.deletion_revision;
 update public.wm_source_deletions set state='verified',completed_at=clock_timestamp(),ledger_revision=s.deletion_revision where space_id=p_space_id and id=p_deletion_id;
 return jsonb_build_object('deletion_id',p_deletion_id,'state','verified','deletion_revision',s.deletion_revision,'repeated',false);
end; $$;

-- Generation remains available after a verified privacy checkpoint. The
-- trusted service compiles from the checkpoint's logical_basis; this function
-- still locks and binds expected_revision, and every new full source must match
-- a currently live archived original. Rebuild independently verifies the
-- checkpoint and generation hashes before materializing either payload.

revoke all on function public.wm_source_deletion_candidate_rows(uuid),public.wm_source_deletion_candidates(uuid,uuid,uuid,text),
 public.wm_source_deletion_inputs(uuid,text,uuid),public.wm_source_deletion_ledger(uuid,uuid),
 public.wm_source_deletion_status(uuid,uuid,uuid),
 public.wm_source_deletion_plan_put(uuid,uuid,uuid,text,text,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.wm_source_deletion_candidates(uuid,uuid,uuid,text),
 public.wm_source_deletion_inputs(uuid,text,uuid),public.wm_source_deletion_ledger(uuid,uuid),
 public.wm_source_deletion_status(uuid,uuid,uuid),
 public.wm_source_deletion_plan_put(uuid,uuid,uuid,text,text,text,jsonb,jsonb) to service_role;
