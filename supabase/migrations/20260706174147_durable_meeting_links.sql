create table public.meeting_links (
  source text primary key,
  meeting_id uuid,
  title text not null,
  meeting_date date,
  deleted_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.meeting_links enable row level security;

create policy "authenticated_select_meeting_links"
  on public.meeting_links for select to authenticated using (true);

grant select on public.meeting_links to authenticated;
revoke all on public.meeting_links from anon;

alter table public.todos add column meeting_source text;
alter table public.blockers add column meeting_source text;
alter table public.open_items add column meeting_source text;
alter table public.decisions add column meeting_source text;

create index todos_meeting_source_idx on public.todos (meeting_source) where meeting_source is not null;
create index blockers_meeting_source_idx on public.blockers (meeting_source) where meeting_source is not null;
create index open_items_meeting_source_idx on public.open_items (meeting_source) where meeting_source is not null;
create index decisions_meeting_source_idx on public.decisions (meeting_source) where meeting_source is not null;

create or replace function public.sync_meeting_link_from_inbox()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_meeting_id uuid;
  v_title text;
  v_date date;
begin
  if tg_op = 'DELETE' then
    if old.entity_type = 'meeting' and nullif(old.source, '') is not null then
      update public.meeting_links
         set deleted_at = case when meeting_id is null then now() else deleted_at end,
             updated_at = now()
       where source = old.source;
    end if;
    return old;
  end if;

  if new.entity_type <> 'meeting' or nullif(new.source, '') is null then
    return new;
  end if;

  v_title := coalesce(nullif(new.payload ->> 'title', ''), 'Meeting');
  v_date := nullif(new.payload ->> 'meeting_date', '')::date;

  if new.status = 'approved' then
    select m.id
      into v_meeting_id
      from public.meetings m
     where (nullif(new.payload ->> 'content_hash', '') is not null and m.content_hash = new.payload ->> 'content_hash')
        or (nullif(new.payload ->> 'source_file', '') is not null and m.source_file = new.payload ->> 'source_file')
     order by
       (m.content_hash = nullif(new.payload ->> 'content_hash', '')) desc,
       m.processed_at desc nulls last,
       m.created_at desc nulls last,
       m.title asc
     limit 1;
  end if;

  insert into public.meeting_links (source, meeting_id, title, meeting_date, deleted_at, updated_at)
  values (new.source, v_meeting_id, v_title, v_date, null, now())
  on conflict (source) do update
    set meeting_id = coalesce(excluded.meeting_id, public.meeting_links.meeting_id),
        title = excluded.title,
        meeting_date = excluded.meeting_date,
        deleted_at = case when excluded.meeting_id is not null then null else public.meeting_links.deleted_at end,
        updated_at = now();

  if v_meeting_id is not null then
    update public.inbox_items child
       set payload = child.payload || jsonb_build_object(
         'meeting_id', v_meeting_id,
         'meeting_source', new.source,
         'meeting_title', v_title,
         'meeting_date', coalesce(child.payload ->> 'meeting_date', v_date::text)
       )
     where child.source = new.source
       and child.entity_type in ('todo', 'blocker', 'open_item', 'decision');
  end if;

  return new;
end;
$$;

create trigger sync_meeting_link_from_inbox_trigger
after insert or update of status, payload on public.inbox_items
for each row execute function public.sync_meeting_link_from_inbox();

create trigger mark_pending_meeting_link_deleted_trigger
after delete on public.inbox_items
for each row execute function public.sync_meeting_link_from_inbox();

create or replace function public.mark_meeting_link_deleted()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  update public.meeting_links
     set deleted_at = now(), updated_at = now()
   where meeting_id = old.id;
  return old;
end;
$$;

create trigger mark_meeting_link_deleted_trigger
before delete on public.meetings
for each row execute function public.mark_meeting_link_deleted();

with ranked as (
  select distinct on (i.source)
         i.source,
         m.id as meeting_id,
         coalesce(nullif(i.payload ->> 'title', ''), m.title, 'Meeting') as title,
         coalesce(nullif(i.payload ->> 'meeting_date', '')::date, m.meeting_date::date) as meeting_date,
         case when i.status = 'approved' and m.id is null then i.created_at else null end as deleted_at
    from public.inbox_items i
    left join public.meetings m
      on (nullif(i.payload ->> 'content_hash', '') is not null and m.content_hash = i.payload ->> 'content_hash')
      or (nullif(i.payload ->> 'source_file', '') is not null and m.source_file = i.payload ->> 'source_file')
   where i.entity_type = 'meeting'
     and nullif(i.source, '') is not null
   order by i.source,
            (m.content_hash = nullif(i.payload ->> 'content_hash', '')) desc,
            m.processed_at desc nulls last,
            m.created_at desc nulls last,
            m.title asc,
            i.created_at desc
)
insert into public.meeting_links (source, meeting_id, title, meeting_date, deleted_at)
select source, meeting_id, title, meeting_date, deleted_at from ranked
on conflict (source) do nothing;

update public.inbox_items child
   set payload = child.payload || jsonb_strip_nulls(jsonb_build_object(
     'meeting_id', link.meeting_id,
     'meeting_source', link.source,
     'meeting_title', link.title,
     'meeting_date', coalesce(child.payload ->> 'meeting_date', link.meeting_date::text)
   ))
  from public.meeting_links link
 where child.source = link.source
   and child.entity_type in ('todo', 'blocker', 'open_item', 'decision');

with source_for_meeting as (
  select distinct on (link.meeting_id) link.meeting_id, link.source
    from public.meeting_links link
   where link.meeting_id is not null
   order by link.meeting_id, link.updated_at desc, link.source
)
update public.todos item set meeting_source = source.source
  from source_for_meeting source where item.meeting_id = source.meeting_id;

with source_for_meeting as (
  select distinct on (link.meeting_id) link.meeting_id, link.source
    from public.meeting_links link
   where link.meeting_id is not null
   order by link.meeting_id, link.updated_at desc, link.source
)
update public.blockers item set meeting_source = source.source
  from source_for_meeting source where item.meeting_id = source.meeting_id;

with source_for_meeting as (
  select distinct on (link.meeting_id) link.meeting_id, link.source
    from public.meeting_links link
   where link.meeting_id is not null
   order by link.meeting_id, link.updated_at desc, link.source
)
update public.open_items item set meeting_source = source.source
  from source_for_meeting source where item.meeting_id = source.meeting_id;

with source_for_meeting as (
  select distinct on (link.meeting_id) link.meeting_id, link.source
    from public.meeting_links link
   where link.meeting_id is not null
   order by link.meeting_id, link.updated_at desc, link.source
)
update public.decisions item set meeting_source = source.source
  from source_for_meeting source where item.meeting_id = source.meeting_id;

revoke all on function public.sync_meeting_link_from_inbox() from public, anon, authenticated;
revoke all on function public.mark_meeting_link_deleted() from public, anon, authenticated;
