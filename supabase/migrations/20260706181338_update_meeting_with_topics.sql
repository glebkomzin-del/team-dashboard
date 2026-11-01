create or replace function public.update_meeting_with_topics(
  p_meeting_id uuid,
  p_title text,
  p_meeting_date date,
  p_participants text[],
  p_ai_summary text,
  p_key_decisions text[],
  p_topics jsonb
)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_topic_names text[];
begin
  if auth.uid() is null then
    raise exception using errcode = '42501', message = 'Authentication required';
  end if;

  if jsonb_typeof(coalesce(p_topics, '[]'::jsonb)) <> 'array' then
    raise exception using errcode = '22023', message = 'p_topics must be a JSON array';
  end if;

  select coalesce(array_agg(topic_name order by ordinal) filter (where topic_name <> ''), array[]::text[])
    into v_topic_names
    from (
      select t.ordinal,
             btrim(coalesce(t.value ->> 'name', '')) as topic_name
        from jsonb_array_elements(coalesce(p_topics, '[]'::jsonb)) with ordinality as t(value, ordinal)
    ) names;

  update public.meetings
     set title = p_title,
         meeting_date = p_meeting_date::timestamptz,
         topics = v_topic_names,
         participants = coalesce(p_participants, array[]::text[]),
         ai_summary = p_ai_summary,
         executive_summary = p_ai_summary,
         key_decisions = coalesce(p_key_decisions, array[]::text[])
   where id = p_meeting_id;

  if not found then
    raise exception using errcode = 'P0002', message = format('Meeting %s not found', p_meeting_id);
  end if;

  delete from public.meeting_topics where meeting_id = p_meeting_id;

  insert into public.meeting_topics (meeting_id, name, summary, sequence)
  select p_meeting_id,
         btrim(coalesce(t.value ->> 'name', '')),
         coalesce(t.value ->> 'summary', ''),
         t.ordinal::integer
    from jsonb_array_elements(coalesce(p_topics, '[]'::jsonb)) with ordinality as t(value, ordinal)
   where btrim(coalesce(t.value ->> 'name', '')) <> '';
end;
$$;

revoke all on function public.update_meeting_with_topics(uuid, text, date, text[], text, text[], jsonb) from public, anon;
grant execute on function public.update_meeting_with_topics(uuid, text, date, text[], text, text[], jsonb) to authenticated;
