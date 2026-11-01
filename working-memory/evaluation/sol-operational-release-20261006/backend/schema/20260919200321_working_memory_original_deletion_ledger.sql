-- Additive control plane for original-only deletion. This migration stages no
-- destructive work. A later worker migration must purge every plaintext scope,
-- verify it, and only then mark a deletion verified.
alter table public.wm_spaces add column deletion_revision bigint not null default 0 check(deletion_revision>=0);
create table public.wm_source_deletions (
 space_id uuid not null references public.wm_spaces(id),
 id uuid not null,
 source_id text not null check(length(source_id) between 1 and 512),
 actor_id uuid not null references auth.users(id),
 request_hash text not null check(request_hash ~ '^[0-9a-f]{64}$'),
 ledger_revision bigint not null check(ledger_revision>0),
 state text not null default 'prepared' check(state in ('prepared','purging','verified','failed')),
 archive_document_ids text[] not null,
 original_content_hashes text[] not null,
 required_scopes text[] not null,
 requested_at timestamptz not null default clock_timestamp(),
 completed_at timestamptz,
 failure_code text,
 primary key(space_id,id),
 check(array_position(archive_document_ids,null) is null),
 check(array_position(original_content_hashes,null) is null),
 check((state='verified' and completed_at is not null and failure_code is null)
    or (state='failed' and completed_at is not null and length(trim(failure_code)) between 1 and 200)
    or (state in ('prepared','purging') and completed_at is null and failure_code is null))
);
create index wm_source_deletions_source on public.wm_source_deletions(space_id,source_id,requested_at desc,id);

create table public.wm_source_deletion_versions (
 space_id uuid not null,
 deletion_id uuid not null,
 source_version text not null check(source_version ~ '^[0-9a-f]{64}$'),
 original_content_hash text not null check(original_content_hash ~ '^[0-9a-f]{64}$'),
 redaction_package jsonb not null check(jsonb_typeof(redaction_package)='object'),
 package_record_hash text not null check(package_record_hash ~ '^[0-9a-f]{64}$'),
 primary key(space_id,deletion_id,source_version),
 foreign key(space_id,deletion_id) references public.wm_source_deletions(space_id,id)
);
create table public.wm_source_deletion_checks (
 space_id uuid not null,
 deletion_id uuid not null,
 scope text not null,
 receipt jsonb not null check(jsonb_typeof(receipt)='object'),
 receipt_hash text not null check(receipt_hash ~ '^[0-9a-f]{64}$'),
 verified_at timestamptz not null default clock_timestamp(),
 primary key(space_id,deletion_id,scope),
 foreign key(space_id,deletion_id) references public.wm_source_deletions(space_id,id)
);
create table public.wm_source_reimport_authorizations (
 space_id uuid not null references public.wm_spaces(id),
 id uuid not null,
 source_id text not null check(length(source_id) between 1 and 512),
 content_hash text not null check(content_hash ~ '^[0-9a-f]{64}$'),
 actor_id uuid not null references auth.users(id),
 ledger_revision bigint not null check(ledger_revision>0),
 reason text not null check(length(trim(reason)) between 1 and 4000),
 created_at timestamptz not null default clock_timestamp(),
 primary key(space_id,id)
);
create index wm_source_reimport_source on public.wm_source_reimport_authorizations(space_id,source_id,created_at desc,id);

alter table public.wm_source_deletions enable row level security;
alter table public.wm_source_deletion_versions enable row level security;
alter table public.wm_source_deletion_checks enable row level security;
alter table public.wm_source_reimport_authorizations enable row level security;
revoke all on public.wm_source_deletions,public.wm_source_deletion_versions,
 public.wm_source_deletion_checks,public.wm_source_reimport_authorizations
 from public,anon,authenticated,service_role;
grant select on public.wm_source_deletions,public.wm_source_deletion_versions,
 public.wm_source_deletion_checks,public.wm_source_reimport_authorizations to authenticated;
grant select,insert on public.wm_source_deletions,public.wm_source_deletion_versions,
 public.wm_source_deletion_checks,public.wm_source_reimport_authorizations to service_role;
create policy wm_source_deletions_owner_read on public.wm_source_deletions for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_source_deletion_versions_owner_read on public.wm_source_deletion_versions for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_source_deletion_checks_owner_read on public.wm_source_deletion_checks for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_source_reimport_owner_read on public.wm_source_reimport_authorizations for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_source_deletions_service_insert on public.wm_source_deletions for insert to service_role with check(true);
create policy wm_source_deletion_versions_service_insert on public.wm_source_deletion_versions for insert to service_role with check(true);
create policy wm_source_deletion_checks_service_insert on public.wm_source_deletion_checks for insert to service_role with check(true);
create policy wm_source_reimport_service_insert on public.wm_source_reimport_authorizations for insert to service_role with check(true);

create function public.wm_source_deletion_stage(
 p_space_id uuid,p_deletion_id uuid,p_actor_id uuid,p_source_id text,p_packages jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; previous public.wm_source_deletions%rowtype;
 request_hash text; package jsonb; package_source jsonb; expected_versions text[]; supplied_versions text[];
 archive_ids text[]; content_hashes text[];
 required constant text[]:=array['archive_documents','archive_notes','source_versions','journal_payloads',
  'generation_payloads','prepared_jobs','model_receipts','question_receipts','search_documents',
  'search_results','local_caches','backup_sets'];
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then
  raise exception 'Owner required' using errcode='42501'; end if;
 if p_deletion_id is null or p_source_id is null or length(p_source_id) not between 1 and 512
    or p_packages is null or jsonb_typeof(p_packages)!='array' then
  raise exception 'Invalid source deletion request' using errcode='22023'; end if;
 request_hash:=encode(extensions.digest(convert_to(jsonb_build_object(
  'actor_id',p_actor_id,'source_id',p_source_id,'packages',p_packages)::text,'UTF8'),'sha256'),'hex');
 select * into previous from public.wm_source_deletions where space_id=p_space_id and id=p_deletion_id;
 if found then
  if previous.request_hash!=request_hash then raise exception 'Deletion identity reused' using errcode='23505'; end if;
  return jsonb_build_object('deletion_id',previous.id,'state',previous.state,'repeated',true,
   'active_backup_snapshots',(select count(*) from public.wm_backup_snapshots b where b.space_id=p_space_id));
 end if;
 if exists(select 1 from public.wm_source_deletions where space_id=p_space_id and source_id=p_source_id) then
  raise exception 'Source identity already has a deletion ledger' using errcode='23505'; end if;
 if not exists(select 1 from public.wm_source_versions v where v.space_id=p_space_id and v.source_id=p_source_id)
    and not exists(select 1 from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id) then
  raise exception 'Source identity unavailable' using errcode='22023'; end if;
 select coalesce(array_agg(v.id order by v.id),'{}') into expected_versions
 from public.wm_source_versions v where v.space_id=p_space_id and v.source_id=p_source_id;
 select coalesce(array_agg(value->'source'->>'id' order by value->'source'->>'id'),'{}') into supplied_versions
 from jsonb_array_elements(p_packages);
 if expected_versions is distinct from supplied_versions then
  raise exception 'Every processed source version needs one redaction package' using errcode='22023'; end if;
 for package in select value from jsonb_array_elements(p_packages) loop
  package_source:=package->'source';
  if package->>'format' is distinct from 'wm-redacted-source-v1'
     or package_source->>'source_id' is distinct from p_source_id
     or coalesce(package_source->>'id','') !~ '^[0-9a-f]{64}$'
     or coalesce(package_source->>'content_hash','') !~ '^[0-9a-f]{64}$'
     or package_source ? 'transcript'
     or coalesce(package->>'package_sha256','') !~ '^[0-9a-f]{64}$'
     or jsonb_typeof(package->'evidence_manifest'->'entries') is distinct from 'array'
     or not exists(select 1 from public.wm_source_versions v where v.space_id=p_space_id
       and v.id=package_source->>'id' and v.source_id=p_source_id
       and v.content_hash=package_source->>'content_hash') then
   raise exception 'Invalid redaction package' using errcode='22023'; end if;
 end loop;
 select coalesce(array_agg(d.id order by d.id),'{}') into archive_ids
 from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id;
 select coalesce(array_agg(distinct h order by h),'{}') into content_hashes from (
  select v.content_hash h from public.wm_source_versions v where v.space_id=p_space_id and v.source_id=p_source_id
  union select d.body_hash from public.wm_archive_documents d where d.space_id=p_space_id and d.source_id=p_source_id
 ) hashes;
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=p_space_id
 returning deletion_revision into s.deletion_revision;
 insert into public.wm_source_deletions(space_id,id,source_id,actor_id,request_hash,ledger_revision,
  archive_document_ids,original_content_hashes,required_scopes)
 values(p_space_id,p_deletion_id,p_source_id,p_actor_id,request_hash,s.deletion_revision,archive_ids,content_hashes,required);
 for package in select value from jsonb_array_elements(p_packages) loop
  insert into public.wm_source_deletion_versions(space_id,deletion_id,source_version,original_content_hash,
   redaction_package,package_record_hash)
  values(p_space_id,p_deletion_id,package->'source'->>'id',package->'source'->>'content_hash',package,
   encode(extensions.digest(convert_to(package::text,'UTF8'),'sha256'),'hex'));
 end loop;
 return jsonb_build_object('deletion_id',p_deletion_id,'state','prepared','repeated',false,
  'processed_versions',jsonb_array_length(p_packages),'archive_documents',cardinality(archive_ids),
  'active_backup_snapshots',(select count(*) from public.wm_backup_snapshots b where b.space_id=p_space_id));
end; $$;

create function public.wm_source_reimport_authorize(
 p_space_id uuid,p_authorization_id uuid,p_actor_id uuid,p_source_id text,p_content_hash text,p_reason text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; latest public.wm_source_deletions%rowtype;
 previous public.wm_source_reimport_authorizations%rowtype;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or p_actor_id is distinct from s.owner_id then
  raise exception 'Owner required' using errcode='42501'; end if;
 if p_authorization_id is null or p_source_id is null or length(p_source_id) not between 1 and 512
    or coalesce(p_content_hash,'') !~ '^[0-9a-f]{64}$'
    or p_reason is null or length(trim(p_reason)) not between 1 and 4000 then
  raise exception 'Explicit reimport authorization required' using errcode='22023'; end if;
 select * into previous from public.wm_source_reimport_authorizations
 where space_id=p_space_id and id=p_authorization_id;
 if found then
  if previous.actor_id is distinct from p_actor_id or previous.source_id is distinct from p_source_id
     or previous.content_hash is distinct from p_content_hash or previous.reason is distinct from p_reason then
   raise exception 'Authorization identity reused' using errcode='23505'; end if;
  return jsonb_build_object('authorization_id',previous.id,'repeated',true);
 end if;
 select * into latest from public.wm_source_deletions
 where space_id=p_space_id and source_id=p_source_id order by requested_at desc,id desc limit 1;
 if not found or latest.state!='verified' then
  raise exception 'Only a verified deletion can be explicitly reimported' using errcode='22023'; end if;
 if p_content_hash=any(latest.original_content_hashes) then
  raise exception 'Deleted original content cannot be reimported' using errcode='22023'; end if;
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=p_space_id
 returning deletion_revision into s.deletion_revision;
 insert into public.wm_source_reimport_authorizations(space_id,id,source_id,content_hash,actor_id,ledger_revision,reason)
 values(p_space_id,p_authorization_id,p_source_id,p_content_hash,p_actor_id,s.deletion_revision,p_reason);
 return jsonb_build_object('authorization_id',p_authorization_id,'repeated',false);
end; $$;

create function public.wm_block_deleted_source_reimport()
returns trigger language plpgsql security invoker set search_path='' as $$
declare latest_requested timestamptz; candidate_hash text;
begin
 candidate_hash:=case when tg_table_name='wm_archive_documents' then to_jsonb(new)->>'body_hash' else to_jsonb(new)->>'content_hash' end;
 select d.requested_at into latest_requested from public.wm_source_deletions d
 where d.space_id=new.space_id and d.source_id=new.source_id
 order by d.requested_at desc,d.id desc limit 1;
 if found and not exists(
  select 1 from public.wm_source_reimport_authorizations a
  where a.space_id=new.space_id and a.source_id=new.source_id and a.content_hash=candidate_hash
    and a.created_at>latest_requested
 ) then
  raise exception 'Deleted source identity requires explicit reimport authorization' using errcode='23505';
 end if;
 return new;
end; $$;
create trigger wm_archive_block_deleted_source before insert on public.wm_archive_documents
 for each row execute function public.wm_block_deleted_source_reimport();
create trigger wm_projection_block_deleted_source before insert on public.wm_source_versions
 for each row execute function public.wm_block_deleted_source_reimport();

revoke all on function public.wm_source_deletion_stage(uuid,uuid,uuid,text,jsonb),
 public.wm_source_reimport_authorize(uuid,uuid,uuid,text,text,text),
 public.wm_block_deleted_source_reimport() from public,anon,authenticated;
grant execute on function public.wm_source_deletion_stage(uuid,uuid,uuid,text,jsonb),
 public.wm_source_reimport_authorize(uuid,uuid,uuid,text,text,text) to service_role;
