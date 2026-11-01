create or replace function public.promote_inbox_meeting(p_inbox_id uuid)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_item public.inbox_items%rowtype;
  v_payload jsonb;
  v_hash text;
  v_meeting_id uuid;
  v_topic_names text[];
begin
  select i.*
    into v_item
    from public.inbox_items as i
   where i.id = p_inbox_id
   for update;

  if not found then
    raise exception using
      errcode = 'P0002',
      message = format('Inbox item %s not found', p_inbox_id);
  end if;

  if v_item.entity_type <> 'meeting' then
    raise exception using
      errcode = 'P0001',
      message = format('Inbox item %s is not a meeting', p_inbox_id);
  end if;

  if v_item.status <> 'pending' then
    raise exception using
      errcode = 'P0001',
      message = format('Inbox item %s is not pending', p_inbox_id);
  end if;

  v_payload := v_item.payload;
  v_hash := coalesce(
    nullif(btrim(v_payload ->> 'content_hash'), ''),
    md5(v_payload ->> 'raw_transcript')
  );

  select m.id
    into v_meeting_id
    from public.meetings as m
   where v_hash is not null
     and m.content_hash = v_hash
   limit 1;

  if v_meeting_id is not null then
    update public.inbox_items
       set status = 'approved'
     where id = p_inbox_id
       and status = 'pending';

    if not found then
      raise exception using
        errcode = 'P0001',
        message = format('Inbox item %s is no longer pending', p_inbox_id);
    end if;

    return v_meeting_id;
  end if;

  select coalesce(
           array_agg(topic_name order by ordinal) filter (where topic_name <> ''),
           array[]::text[]
         )
    into v_topic_names
    from (
      select t.ordinal,
             btrim(
               case jsonb_typeof(t.value)
                 when 'object' then coalesce(t.value ->> 'name', '')
                 when 'string' then t.value #>> '{}'
                 else ''
               end
             ) as topic_name
        from jsonb_array_elements(
               case
                 when jsonb_typeof(v_payload -> 'topics') = 'array'
                   then v_payload -> 'topics'
                 else '[]'::jsonb
               end
             ) with ordinality as t(value, ordinal)
    ) as topic_names;

  insert into public.meetings (
    title,
    meeting_date,
    topics,
    participants,
    ai_summary,
    executive_summary,
    key_decisions,
    raw_transcript,
    source_file,
    content_hash
  )
  values (
    v_payload ->> 'title',
    (v_payload ->> 'meeting_date')::timestamptz,
    v_topic_names,
    coalesce(
      array(
        select jsonb_array_elements_text(
          case
            when jsonb_typeof(v_payload -> 'participants') = 'array'
              then v_payload -> 'participants'
            else '[]'::jsonb
          end
        )
      ),
      array[]::text[]
    ),
    v_payload ->> 'ai_summary',
    v_payload ->> 'ai_summary',
    coalesce(
      array(
        select jsonb_array_elements_text(
          case
            when jsonb_typeof(v_payload -> 'key_decisions') = 'array'
              then v_payload -> 'key_decisions'
            else '[]'::jsonb
          end
        )
      ),
      array[]::text[]
    ),
    v_payload ->> 'raw_transcript',
    v_payload ->> 'source_file',
    v_hash
  )
  on conflict (content_hash) do nothing
  returning id into v_meeting_id;

  if v_meeting_id is null then
    select m.id
      into v_meeting_id
      from public.meetings as m
     where m.content_hash = v_hash;

    if v_meeting_id is null then
      raise exception using
        errcode = 'P0001',
        message = 'Meeting promotion failed without creating or finding a meeting';
    end if;

    update public.inbox_items
       set status = 'approved'
     where id = p_inbox_id
       and status = 'pending';

    if not found then
      raise exception using
        errcode = 'P0001',
        message = format('Inbox item %s is no longer pending', p_inbox_id);
    end if;

    return v_meeting_id;
  end if;

  insert into public.meeting_topics (meeting_id, name, summary, sequence)
  select v_meeting_id,
         topic_name,
         topic_summary,
         topic_sequence
    from (
      select btrim(
               case jsonb_typeof(t.value)
                 when 'object' then coalesce(t.value ->> 'name', '')
                 when 'string' then t.value #>> '{}'
                 else ''
               end
             ) as topic_name,
             case jsonb_typeof(t.value)
               when 'object' then coalesce(t.value ->> 'summary', '')
               else ''
             end as topic_summary,
             case
               when jsonb_typeof(t.value) = 'object'
                and coalesce(t.value ->> 'sequence', '') ~ '^[0-9]+$'
                 then (t.value ->> 'sequence')::integer
               else t.ordinal::integer
             end as topic_sequence
        from jsonb_array_elements(
               case
                 when jsonb_typeof(v_payload -> 'topics') = 'array'
                   then v_payload -> 'topics'
                 else '[]'::jsonb
               end
             ) with ordinality as t(value, ordinal)
    ) as topics_to_insert
   where topic_name <> '';

  update public.inbox_items
     set status = 'approved'
   where id = p_inbox_id
     and status = 'pending';

  if not found then
    raise exception using
      errcode = 'P0001',
      message = format('Inbox item %s is no longer pending', p_inbox_id);
  end if;

  return v_meeting_id;
end;
$$;

revoke all on function public.promote_inbox_meeting(uuid) from public, anon;
grant execute on function public.promote_inbox_meeting(uuid) to authenticated;
