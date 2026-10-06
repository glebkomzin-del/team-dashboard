-- Additive storage only. Does not change legacy tables, triggers, embeddings,
-- routing, active generations or the user's previously approved cutoff cleanup.
create table public.wm_spaces (
  id uuid primary key,
  owner_id uuid not null references auth.users(id),
  label text not null check (length(label) between 1 and 200),
  state text not null default 'draft' check (state in ('draft','active','retired')),
  revision bigint not null default 0 check (revision >= 0),
  created_at timestamptz not null default now()
);
create unique index wm_one_active_space_per_owner on public.wm_spaces(owner_id) where state='active';
create index wm_spaces_owner on public.wm_spaces(owner_id);

create table public.wm_source_versions (
  space_id uuid not null references public.wm_spaces(id),
  id text not null check (id ~ '^[0-9a-f]{64}$'),
  source_id text not null check (length(source_id) between 1 and 512),
  content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
  event_date date not null,
  title text not null check (length(title) between 1 and 1000),
  transcript text not null check (length(transcript)>0),
  observed_at timestamptz not null,
  primary key(space_id,id),
  unique(space_id,source_id,content_hash)
);
create index wm_sources_date on public.wm_source_versions(space_id,event_date);

create table public.wm_journal (
  space_id uuid not null references public.wm_spaces(id),
  revision bigint not null check (revision>0),
  command_id uuid not null,
  request_hash text not null check (request_hash ~ '^[0-9a-f]{64}$'),
  kind text not null check (kind in ('source','human')),
  source_version text,
  actor_id uuid references auth.users(id),
  payload jsonb not null check (jsonb_typeof(payload)='object'),
  recorded_at timestamptz not null default now(),
  primary key(space_id,revision),
  unique(space_id,command_id),
  foreign key(space_id,source_version) references public.wm_source_versions(space_id,id),
  check ((kind='source' and source_version is not null and actor_id is null)
      or (kind='human' and source_version is null and actor_id is not null))
);
create unique index wm_journal_source_once on public.wm_journal(space_id,source_version) where kind='source';
create index wm_journal_actor on public.wm_journal(actor_id) where actor_id is not null;

alter table public.wm_spaces enable row level security;
alter table public.wm_source_versions enable row level security;
alter table public.wm_journal enable row level security;
revoke all on public.wm_spaces,public.wm_source_versions,public.wm_journal from public,anon,authenticated,service_role;
grant select on public.wm_spaces,public.wm_source_versions,public.wm_journal to authenticated;
-- Writes only through the server. Browser sessions cannot rewrite history.
grant select,insert,update on public.wm_spaces to service_role;
grant select,insert on public.wm_source_versions,public.wm_journal to service_role;
create policy wm_spaces_owner_read on public.wm_spaces for select to authenticated
  using ((select auth.uid())=owner_id);
create policy wm_sources_owner_read on public.wm_source_versions for select to authenticated
  using (exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_journal_owner_read on public.wm_journal for select to authenticated
  using (exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));

-- Optimistic concurrency + retry identity are checked under the same row lock.
-- SECURITY INVOKER: no privileged bypass hidden in a browser-callable function.
create function public.wm_append(
  p_space_id uuid,p_expected_revision bigint,p_command_id uuid,p_kind text,
  p_payload jsonb,p_source jsonb default null,p_actor_id uuid default null
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare
  space public.wm_spaces%rowtype;
  previous public.wm_journal%rowtype;
  request_hash text;
  version_id text;
  body_hash text;
  source_row public.wm_source_versions%rowtype;
begin
  if p_kind is null or p_kind not in ('source','human') or p_payload is null
     or jsonb_typeof(p_payload)!='object' or p_command_id is null
     or p_expected_revision is null or p_expected_revision<0 then
    raise exception 'Invalid journal request' using errcode='22023';
  end if;
  select * into space from public.wm_spaces where id=p_space_id for update;
  if not found or space.state='retired' then
    raise exception 'Space unavailable' using errcode='22023';
  end if;
  request_hash:=encode(extensions.digest(convert_to(jsonb_build_object(
    'kind',p_kind,'payload',p_payload,'source',p_source,'actor_id',p_actor_id)::text,'UTF8'),'sha256'),'hex');
  select * into previous from public.wm_journal where space_id=p_space_id and command_id=p_command_id;
  if found then
    if previous.request_hash!=request_hash then
      raise exception 'Idempotency key reused with different content' using errcode='23505';
    end if;
    return jsonb_build_object('revision',previous.revision,'repeated',true);
  end if;
  if space.revision!=p_expected_revision then
    raise exception 'Revision conflict: refresh and reconcile' using errcode='40001';
  end if;
  if p_kind='human' then
    if p_actor_id is distinct from space.owner_id or p_source is not null then
      raise exception 'Invalid human actor' using errcode='42501';
    end if;
    if not (p_payload ? 'action' and p_payload ? 'target_id' and p_payload ? 'reason')
       or coalesce(length(p_payload->>'reason'),0)=0 then
      raise exception 'Incomplete human decision' using errcode='22023';
    end if;
  else
    if p_actor_id is not null or p_source is null or jsonb_typeof(p_source)!='object'
       or not (p_source ?& array['source_id','content_hash','event_date','title','transcript','observed_at','id']) then
      raise exception 'Incomplete source identity' using errcode='22023';
    end if;
    body_hash:=encode(extensions.digest(convert_to(p_source->>'transcript','UTF8'),'sha256'),'hex');
    version_id:=encode(extensions.digest(convert_to((p_source->>'source_id')||':'||body_hash,'UTF8'),'sha256'),'hex');
    if body_hash is distinct from (p_source->>'content_hash') or version_id is distinct from (p_source->>'id') then
      raise exception 'Source checksum mismatch' using errcode='22023';
    end if;
    -- A changed already-applied source must be rebuilt in a draft generation.
    if exists(select 1 from public.wm_source_versions where space_id=p_space_id and source_id=p_source->>'source_id') then
      raise exception 'Source already represented; explicit generation required' using errcode='23505';
    end if;
    if exists(select 1 from public.wm_source_versions where space_id=p_space_id and event_date>(p_source->>'event_date')::date) then
      raise exception 'Out-of-order source; explicit generation required' using errcode='22023';
    end if;
    insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
      values(p_space_id,version_id,p_source->>'source_id',body_hash,(p_source->>'event_date')::date,
             p_source->>'title',p_source->>'transcript',(p_source->>'observed_at')::timestamptz);
  end if;
  insert into public.wm_journal(space_id,revision,command_id,request_hash,kind,source_version,actor_id,payload)
    values(p_space_id,space.revision+1,p_command_id,request_hash,p_kind,version_id,p_actor_id,p_payload);
  update public.wm_spaces set revision=revision+1 where id=p_space_id;
  return jsonb_build_object('revision',space.revision+1,'repeated',false);
end;
$$;
revoke all on function public.wm_append(uuid,bigint,uuid,text,jsonb,jsonb,uuid) from public,anon,authenticated;
grant execute on function public.wm_append(uuid,bigint,uuid,text,jsonb,jsonb,uuid) to service_role;
