-- Temporary, consistent export of mutable queue state. Immutable journal and
-- archive rows are read separately at the revisions pinned here.
create table public.wm_backup_snapshots (
 id uuid primary key, space_id uuid not null references public.wm_spaces(id),
 revision bigint not null, archive_revision bigint not null,
 space_json jsonb not null, record_count bigint not null default 0,
 created_at timestamptz not null default clock_timestamp()
);
create table public.wm_backup_records (
 snapshot_id uuid not null references public.wm_backup_snapshots(id) on delete cascade,
 sequence bigint generated always as identity,
 kind text not null check(kind in ('config','job','call','job_decision')),
 record_json text not null, record_hash text not null check(record_hash ~ '^[0-9a-f]{64}$'),
 primary key(snapshot_id,sequence)
);
alter table public.wm_backup_snapshots enable row level security;
alter table public.wm_backup_records enable row level security;
revoke all on public.wm_backup_snapshots,public.wm_backup_records from public,anon,authenticated,service_role;
grant select,insert,update,delete on public.wm_backup_snapshots to service_role;
grant select,insert on public.wm_backup_records to service_role;
grant usage,select on sequence public.wm_backup_records_sequence_seq to service_role;
create policy wm_backup_snapshots_service_access on public.wm_backup_snapshots for all to service_role using(true) with check(true);
create policy wm_backup_records_service_access on public.wm_backup_records for all to service_role using(true) with check(true);

create function public.wm_backup_begin(p_space_id uuid,p_snapshot_id uuid)
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
 ) x;
 update public.wm_backup_snapshots set record_count=(select count(*) from public.wm_backup_records where snapshot_id=p_snapshot_id)
 where id=p_snapshot_id returning * into b;
 return to_jsonb(b)||jsonb_build_object('repeated',false);
end; $$;
create function public.wm_backup_page(p_space_id uuid,p_snapshot_id uuid,p_after bigint)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if p_after is null or p_after<0 or not exists(select 1 from public.wm_backup_snapshots where id=p_snapshot_id and space_id=p_space_id) then
  raise exception 'Snapshot unavailable' using errcode='22023'; end if;
 -- One call record may contain a complete prompt and response. Do not truncate
 -- it or combine an unbounded number of large responses into an Edge reply.
 return coalesce((select jsonb_agg(to_jsonb(r)) from (select sequence,kind,record_json,record_hash
  from public.wm_backup_records where snapshot_id=p_snapshot_id and sequence>p_after order by sequence limit 1) r),'[]'::jsonb);
end; $$;
create function public.wm_backup_release(p_space_id uuid,p_snapshot_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
begin
 perform 1 from public.wm_spaces where id=p_space_id for update;
 delete from public.wm_backup_snapshots where id=p_snapshot_id and space_id=p_space_id;
 return jsonb_build_object('released',found);
end; $$;
revoke all on function public.wm_backup_begin(uuid,uuid),public.wm_backup_page(uuid,uuid,bigint),public.wm_backup_release(uuid,uuid) from public,anon,authenticated;
grant execute on function public.wm_backup_begin(uuid,uuid),public.wm_backup_page(uuid,uuid,bigint),public.wm_backup_release(uuid,uuid) to service_role;
