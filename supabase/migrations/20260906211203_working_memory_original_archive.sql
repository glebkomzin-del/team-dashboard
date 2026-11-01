-- Original archive is independent of extraction. Saving an original or an old
-- summary never queues a model call and never creates working-memory actions.
alter table public.wm_spaces add column archive_revision bigint not null default 0 check(archive_revision>=0);
create table public.wm_archive_documents (
  space_id uuid not null references public.wm_spaces(id),
  id text not null check(id ~ '^[0-9a-f]{64}$'),
  source_id text not null check(length(source_id) between 1 and 512),
  event_date date not null,
  observed_at timestamptz not null,
  title text not null check(length(title) between 1 and 1000),
  body_hash text not null check(body_hash ~ '^[0-9a-f]{64}$'),
  export_hash text not null check(export_hash ~ '^[0-9a-f]{64}$'),
  body text not null check(length(body)>0),
  export text not null,
  metadata_json text not null check(jsonb_typeof(metadata_json::jsonb)='object'),
  registered_revision bigint not null check(registered_revision>0),
  primary key(space_id,id)
);
create index wm_archive_source on public.wm_archive_documents(space_id,source_id,observed_at);
create index wm_archive_revision on public.wm_archive_documents(space_id,registered_revision);
create table public.wm_archive_notes (
  space_id uuid not null,
  id text not null check(id ~ '^[0-9a-f]{64}$'),
  document_id text not null,
  origin text not null check(origin in ('legacy_meetings','legacy_meeting_inbox','source_summary')),
  origin_id text not null check(length(origin_id) between 1 and 512),
  note_json text not null check(jsonb_typeof(note_json::jsonb)='object'),
  note_hash text not null check(note_hash ~ '^[0-9a-f]{64}$'),
  registered_revision bigint not null check(registered_revision>0),
  primary key(space_id,id),
  foreign key(space_id,document_id) references public.wm_archive_documents(space_id,id)
);
create index wm_archive_notes_document on public.wm_archive_notes(space_id,document_id);
create index wm_archive_notes_revision on public.wm_archive_notes(space_id,registered_revision);
alter table public.wm_archive_documents enable row level security;
alter table public.wm_archive_notes enable row level security;
revoke all on public.wm_archive_documents,public.wm_archive_notes from public,anon,authenticated,service_role;
grant select on public.wm_archive_documents,public.wm_archive_notes to authenticated;
grant select,insert on public.wm_archive_documents,public.wm_archive_notes to service_role;
create policy wm_archive_owner_read on public.wm_archive_documents for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));
create policy wm_archive_notes_owner_read on public.wm_archive_notes for select to authenticated
 using(exists(select 1 from public.wm_spaces s where s.id=space_id and s.owner_id=(select auth.uid())));

create function public.wm_archive_put(p_space_id uuid,p_document jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare
  space public.wm_spaces%rowtype;
  previous public.wm_archive_documents%rowtype;
  meta jsonb;
  identifier text;
begin
  select * into space from public.wm_spaces where id=p_space_id for update;
  if not found or space.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
  if p_document is null or jsonb_typeof(p_document)!='object'
     or not(p_document ?& array['id','source_id','event_date','observed_at','title','body_hash','export_hash','body','export','metadata_json'])
     or exists(select 1 from jsonb_each(p_document) e where jsonb_typeof(e.value)!='string') then
    raise exception 'Invalid original envelope' using errcode='22023';
  end if;
  if (p_document->>'observed_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' then
    raise exception 'Observation time requires timezone' using errcode='22023';
  end if;
  meta:=(p_document->>'metadata_json')::jsonb;
  identifier:=encode(extensions.digest(convert_to((p_document->>'source_id')||':'||(p_document->>'metadata_json'),'UTF8'),'sha256'),'hex');
  if identifier is distinct from p_document->>'id'
     or encode(extensions.digest(convert_to(p_document->>'body','UTF8'),'sha256'),'hex') is distinct from p_document->>'body_hash'
     or encode(extensions.digest(convert_to(p_document->>'export','UTF8'),'sha256'),'hex') is distinct from p_document->>'export_hash'
     or meta->>'source_id' is distinct from p_document->>'source_id'
     or meta->>'event_date' is distinct from p_document->>'event_date'
     or meta->>'title' is distinct from p_document->>'title'
     or meta->>'body_sha256' is distinct from p_document->>'body_hash'
     or meta->>'export_sha256' is distinct from p_document->>'export_hash'
     or coalesce(meta->>'body_offset_characters','') !~ '^[0-9]+$'
     or substring(p_document->>'export' from (meta->>'body_offset_characters')::integer+1) is distinct from p_document->>'body' then
    raise exception 'Original provenance or checksum mismatch' using errcode='22023';
  end if;
  select * into previous from public.wm_archive_documents where space_id=p_space_id and id=identifier;
  if found then
    if (to_jsonb(previous)-'space_id'-'registered_revision'-'event_date'-'observed_at')
         is distinct from (p_document-'event_date'-'observed_at')
       or previous.event_date is distinct from (p_document->>'event_date')::date
       or previous.observed_at is distinct from (p_document->>'observed_at')::timestamptz then
      raise exception 'Original identity reused with changed data' using errcode='23505';
    end if;
    return jsonb_build_object('id',identifier,'archive_revision',previous.registered_revision,'repeated',true);
  end if;
  insert into public.wm_archive_documents values(p_space_id,identifier,p_document->>'source_id',
    (p_document->>'event_date')::date,(p_document->>'observed_at')::timestamptz,p_document->>'title',
    p_document->>'body_hash',p_document->>'export_hash',p_document->>'body',p_document->>'export',
    p_document->>'metadata_json',space.archive_revision+1);
  update public.wm_spaces set archive_revision=archive_revision+1 where id=p_space_id;
  return jsonb_build_object('id',identifier,'archive_revision',space.archive_revision+1,'repeated',false);
end;
$$;
revoke all on function public.wm_archive_put(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.wm_archive_put(uuid,jsonb) to service_role;

create function public.wm_archive_note_put(p_space_id uuid,p_note jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare
  space public.wm_spaces%rowtype;
  previous public.wm_archive_notes%rowtype;
  identifier text;
  body_hash text;
begin
  select * into space from public.wm_spaces where id=p_space_id for update;
  if not found or space.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
  if p_note is null or jsonb_typeof(p_note)!='object'
     or not(p_note ?& array['id','document_id','origin','origin_id','note_json','note_hash'])
     or exists(select 1 from jsonb_each(p_note) e where jsonb_typeof(e.value)!='string') then
    raise exception 'Invalid archive note envelope' using errcode='22023';
  end if;
  body_hash:=encode(extensions.digest(convert_to(p_note->>'note_json','UTF8'),'sha256'),'hex');
  identifier:=encode(extensions.digest(convert_to((p_note->>'document_id')||':'||(p_note->>'origin')||':'||(p_note->>'origin_id')||':'||body_hash,'UTF8'),'sha256'),'hex');
  if body_hash is distinct from p_note->>'note_hash' or identifier is distinct from p_note->>'id' then
    raise exception 'Note checksum mismatch' using errcode='22023';
  end if;
  select * into previous from public.wm_archive_notes where space_id=p_space_id and id=identifier;
  if found then
    if (to_jsonb(previous)-'space_id'-'registered_revision') is distinct from p_note then
      raise exception 'Note identity reused with changed data' using errcode='23505';
    end if;
    return jsonb_build_object('id',identifier,'archive_revision',previous.registered_revision,'repeated',true);
  end if;
  insert into public.wm_archive_notes values(p_space_id,identifier,p_note->>'document_id',p_note->>'origin',
    p_note->>'origin_id',p_note->>'note_json',body_hash,space.archive_revision+1);
  update public.wm_spaces set archive_revision=archive_revision+1 where id=p_space_id;
  return jsonb_build_object('id',identifier,'archive_revision',space.archive_revision+1,'repeated',false);
end;
$$;
revoke all on function public.wm_archive_note_put(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.wm_archive_note_put(uuid,jsonb) to service_role;
