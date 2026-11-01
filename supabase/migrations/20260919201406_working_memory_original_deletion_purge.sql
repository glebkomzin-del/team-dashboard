-- Privacy checkpoint and purge. The caller supplies a locally verified
-- projection snapshot; this function never calls a model and refuses to run
-- while an export snapshot can still hydrate pre-purge plaintext.
alter table public.wm_source_versions alter column transcript drop not null;
alter table public.wm_source_versions add column redaction_id uuid;
alter table public.wm_archive_documents alter column body drop not null;
alter table public.wm_archive_documents alter column export drop not null;
alter table public.wm_archive_documents add column redaction_id uuid;
alter table public.wm_archive_notes alter column note_json drop not null;
alter table public.wm_archive_notes add column redaction_id uuid;
alter table public.wm_model_calls alter column request_json drop not null;
alter table public.wm_model_calls add column redaction_id uuid;
alter table public.wm_model_calls add column redacted_at timestamptz;
alter table public.wm_questions alter column request_json drop not null;
alter table public.wm_questions add column redaction_id uuid;
alter table public.wm_question_calls alter column request_json drop not null;
alter table public.wm_question_calls add column redaction_id uuid;
alter table public.wm_journal add column redaction_id uuid;
alter table public.wm_journal add column original_payload_hash text check(original_payload_hash ~ '^[0-9a-f]{64}$');
alter table public.wm_generation_reviews add column redaction_id uuid;
alter table public.wm_generation_reviews add column original_payload_hash text check(original_payload_hash ~ '^[0-9a-f]{64}$');

alter table public.wm_model_calls drop constraint wm_model_calls_check;
alter table public.wm_model_calls add constraint wm_model_calls_check check(
 (redaction_id is not null and request_json is null and response_json is null)
 or (redaction_id is null and response_json is null and response_hash is null and received_at is null and actual_micro_usd is null)
 or (redaction_id is null and request_json is not null and response_json is not null and response_hash is not null and received_at is not null));
alter table public.wm_questions drop constraint wm_questions_check;
alter table public.wm_questions add constraint wm_questions_check check(
 (redaction_id is not null and request_json is null and response_json is null)
 or (redaction_id is null and response_json is null and response_hash is null and completed_at is null)
 or (redaction_id is null and request_json is not null and response_json is not null and response_hash is not null and completed_at is not null));
alter table public.wm_question_calls drop constraint wm_question_calls_check;
alter table public.wm_question_calls add constraint wm_question_calls_check check(
 (redaction_id is not null and request_json is null and response_json is null)
 or (redaction_id is null and response_json is null and response_hash is null and received_at is null and actual_micro_usd is null)
 or (redaction_id is null and request_json is not null and response_json is not null and response_hash is not null and received_at is not null));

alter table public.wm_journal drop constraint wm_journal_kind_check;
alter table public.wm_journal add constraint wm_journal_kind_check check(kind in ('source','human','generation','redaction'));
alter table public.wm_journal drop constraint wm_journal_check;
alter table public.wm_journal add constraint wm_journal_check check(
 (kind='source' and source_version is not null and actor_id is null)
 or (kind in ('human','generation','redaction') and source_version is null and actor_id is not null));

create function public.wm_source_deletion_purge(
 p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_command_id uuid,p_projection_snapshot jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
begin
 raise exception 'Sanitized deletion plan is required' using errcode='0A000';
end; $$;

create function public.wm_source_deletion_check(
 p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_scope text,p_receipt jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; d public.wm_source_deletions%rowtype;
 prior public.wm_source_deletion_checks%rowtype; h text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 select * into d from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id;
 if not found or d.state!='purging' or p_scope not in ('local_caches','backup_sets')
    or p_receipt is null or jsonb_typeof(p_receipt)!='object' or octet_length(p_receipt::text)>64000 then
  raise exception 'Invalid external deletion check' using errcode='22023'; end if;
 if p_scope='local_caches' and p_receipt->>'rebuilt' is distinct from 'true' then
  raise exception 'Local cache rebuild is not attested' using errcode='22023'; end if;
 if p_scope='backup_sets' and (p_receipt->>'expired_prior_sets' is distinct from 'true'
    or coalesce(p_receipt->>'minimum_deletion_revision','') !~ '^[0-9]+$'
    or (p_receipt->>'minimum_deletion_revision')::bigint<d.ledger_revision) then
  raise exception 'Backup expiry and restore watermark are not attested' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_receipt::text,'UTF8'),'sha256'),'hex');
 select * into prior from public.wm_source_deletion_checks
 where space_id=p_space_id and deletion_id=p_deletion_id and scope=p_scope;
 if found then
  if prior.receipt_hash!=h then raise exception 'Deletion check identity reused' using errcode='23505'; end if;
  return jsonb_build_object('scope',p_scope,'repeated',true);
 end if;
 insert into public.wm_source_deletion_checks values(p_space_id,p_deletion_id,p_scope,p_receipt,h,clock_timestamp());
 return jsonb_build_object('scope',p_scope,'repeated',false);
end; $$;

create function public.wm_source_deletion_finalize(
 p_space_id uuid,p_deletion_id uuid,p_actor_id uuid
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; d public.wm_source_deletions%rowtype;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or p_actor_id is distinct from s.owner_id then raise exception 'Owner required' using errcode='42501'; end if;
 select * into d from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id for update;
 if not found then raise exception 'Deletion ledger unavailable' using errcode='22023'; end if;
 if d.state='verified' then return jsonb_build_object('deletion_id',p_deletion_id,'state','verified','repeated',true); end if;
 if d.state!='purging'
    or exists(select 1 from public.wm_backup_snapshots b where b.space_id=p_space_id)
    or (select array_agg(scope order by scope) from public.wm_source_deletion_checks
        where space_id=p_space_id and deletion_id=p_deletion_id)
       is distinct from (select array_agg(scope order by scope) from unnest(d.required_scopes) scope)
    or exists(select 1 from public.wm_source_versions where space_id=p_space_id and source_id=d.source_id and transcript is not null)
    or exists(select 1 from public.wm_archive_documents where space_id=p_space_id and source_id=d.source_id and (body is not null or export is not null))
    or exists(select 1 from public.wm_archive_notes where space_id=p_space_id and document_id=any(d.archive_document_ids) and note_json is not null)
    or exists(select 1 from public.wm_model_calls c join public.wm_jobs j on j.space_id=c.space_id and j.id=c.job_id
      where c.space_id=p_space_id and j.source_id=d.source_id and (c.request_json is not null or c.response_json is not null))
    or exists(select 1 from public.wm_questions where space_id=p_space_id and (request_json is not null or response_json is not null))
    or exists(select 1 from public.wm_question_calls where space_id=p_space_id and (request_json is not null or response_json is not null))
    or exists(select 1 from public.wm_search_documents where space_id=p_space_id and source_id=d.source_id) then
  raise exception 'Deletion verification is incomplete' using errcode='40001'; end if;
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=p_space_id
 returning deletion_revision into s.deletion_revision;
 update public.wm_source_deletions set state='verified',completed_at=clock_timestamp(),
  ledger_revision=s.deletion_revision where space_id=p_space_id and id=p_deletion_id;
 return jsonb_build_object('deletion_id',p_deletion_id,'state','verified',
  'deletion_revision',s.deletion_revision,'repeated',false);
end; $$;

revoke all on function public.wm_source_deletion_purge(uuid,uuid,uuid,uuid,jsonb),
 public.wm_source_deletion_check(uuid,uuid,uuid,text,jsonb),
 public.wm_source_deletion_finalize(uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.wm_source_deletion_purge(uuid,uuid,uuid,uuid,jsonb),
 public.wm_source_deletion_check(uuid,uuid,uuid,text,jsonb),
 public.wm_source_deletion_finalize(uuid,uuid,uuid) to service_role;

-- Deletion ledgers and checkpoint payloads are mandatory restore inputs.
alter table public.wm_backup_snapshots add column deletion_revision bigint not null default 0;
alter table public.wm_backup_records drop constraint wm_backup_records_kind_check;
alter table public.wm_backup_records add constraint wm_backup_records_kind_check check(kind in
 ('config','job','call','job_decision','generation_review','search_document','search_snapshot','search_result',
  'question','question_call','source_deletion','source_deletion_version','source_deletion_check','source_reimport_authorization'));
do $$ declare definition text; begin
 select pg_get_functiondef('public.wm_backup_begin(uuid,uuid)'::regprocedure) into definition;
 if position('insert into public.wm_backup_snapshots(id,space_id,revision,archive_revision,space_json)' in definition)=0
    or position('values(p_snapshot_id,p_space_id,s.revision,s.archive_revision,to_jsonb(s))' in definition)=0
    or position(') x;' in definition)=0 then raise exception 'Unexpected backup implementation'; end if;
 definition:=replace(definition,
  'insert into public.wm_backup_snapshots(id,space_id,revision,archive_revision,space_json)',
  'insert into public.wm_backup_snapshots(id,space_id,revision,archive_revision,deletion_revision,space_json)');
 definition:=replace(definition,
  'values(p_snapshot_id,p_space_id,s.revision,s.archive_revision,to_jsonb(s))',
  'values(p_snapshot_id,p_space_id,s.revision,s.archive_revision,s.deletion_revision,to_jsonb(s))');
 definition:=replace(definition,') x;',$branch$
  union all select 'source_deletion',to_jsonb(d)::text from public.wm_source_deletions d where d.space_id=p_space_id
  union all select 'source_deletion_version',to_jsonb(v)::text from public.wm_source_deletion_versions v where v.space_id=p_space_id
  union all select 'source_deletion_check',to_jsonb(c)::text from public.wm_source_deletion_checks c where c.space_id=p_space_id
  union all select 'source_reimport_authorization',to_jsonb(a)::text from public.wm_source_reimport_authorizations a where a.space_id=p_space_id
 ) x;$branch$);
 execute definition;
end $$;
