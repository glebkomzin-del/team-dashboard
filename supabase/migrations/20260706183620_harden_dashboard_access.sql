create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists private.dashboard_users (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

revoke all on private.dashboard_users from public, anon, authenticated;

insert into private.dashboard_users (user_id)
select id from auth.users where email_confirmed_at is not null
on conflict (user_id) do nothing;

create or replace function public.is_dashboard_user()
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, private
as $$
  select exists (
    select 1 from private.dashboard_users allowed
    where allowed.user_id = auth.uid()
  );
$$;

revoke all on function public.is_dashboard_user() from public, anon;
grant execute on function public.is_dashboard_user() to authenticated;

drop policy if exists auth_all_activity on public.activity_log;
create policy auth_all_activity on public.activity_log for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists auth_all_blockers on public.blockers;
create policy auth_all_blockers on public.blockers for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists authenticated_select_decisions on public.decisions;
create policy authenticated_select_decisions on public.decisions for select to authenticated
  using ((select public.is_dashboard_user()));

drop policy if exists authenticated_delete_inbox_items on public.inbox_items;
create policy authenticated_delete_inbox_items on public.inbox_items for delete to authenticated
  using ((select public.is_dashboard_user()));
drop policy if exists authenticated_select_inbox_items on public.inbox_items;
create policy authenticated_select_inbox_items on public.inbox_items for select to authenticated
  using ((select public.is_dashboard_user()));
drop policy if exists authenticated_update_inbox_items on public.inbox_items;
create policy authenticated_update_inbox_items on public.inbox_items for update to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists authenticated_select_meeting_links on public.meeting_links;
create policy authenticated_select_meeting_links on public.meeting_links for select to authenticated
  using ((select public.is_dashboard_user()));

drop policy if exists authenticated_select_meeting_topics on public.meeting_topics;
create policy authenticated_select_meeting_topics on public.meeting_topics for select to authenticated
  using ((select public.is_dashboard_user()));

drop policy if exists auth_all_meetings on public.meetings;
create policy auth_all_meetings on public.meetings for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists auth_all_open on public.open_items;
create policy auth_all_open on public.open_items for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists authenticated_all_project_meetings on public.project_meetings;
create policy authenticated_all_project_meetings on public.project_meetings for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists authenticated_all_projects on public.projects;
create policy authenticated_all_projects on public.projects for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists auth_all_team on public.team_members;
create policy auth_all_team on public.team_members for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

drop policy if exists auth_all_todos on public.todos;
create policy auth_all_todos on public.todos for all to authenticated
  using ((select public.is_dashboard_user())) with check ((select public.is_dashboard_user()));

alter function public.promote_inbox_meeting(uuid) rename to promote_inbox_meeting_internal;
revoke all on function public.promote_inbox_meeting_internal(uuid) from public, anon, authenticated;

create function public.promote_inbox_meeting(p_inbox_id uuid)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if not public.is_dashboard_user() then
    raise exception using errcode = '42501', message = 'Dashboard access denied';
  end if;
  return public.promote_inbox_meeting_internal(p_inbox_id);
end;
$$;
revoke all on function public.promote_inbox_meeting(uuid) from public, anon;
grant execute on function public.promote_inbox_meeting(uuid) to authenticated;

alter function public.update_meeting_with_topics(uuid, text, date, text[], text, text[], jsonb)
  rename to update_meeting_with_topics_internal;
revoke all on function public.update_meeting_with_topics_internal(uuid, text, date, text[], text, text[], jsonb)
  from public, anon, authenticated;

create function public.update_meeting_with_topics(
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
begin
  if not public.is_dashboard_user() then
    raise exception using errcode = '42501', message = 'Dashboard access denied';
  end if;
  perform public.update_meeting_with_topics_internal(
    p_meeting_id, p_title, p_meeting_date, p_participants,
    p_ai_summary, p_key_decisions, p_topics
  );
end;
$$;
revoke all on function public.update_meeting_with_topics(uuid, text, date, text[], text, text[], jsonb)
  from public, anon;
grant execute on function public.update_meeting_with_topics(uuid, text, date, text[], text, text[], jsonb)
  to authenticated;

create or replace function public.is_nightly_job_active()
returns boolean
language plpgsql
security definer
set search_path = public, cron, pg_temp
as $$
begin
  if not public.is_dashboard_user() then
    raise exception using errcode = '42501', message = 'Dashboard access denied';
  end if;
  return exists (select 1 from cron.job where jobname = 'nightly-archive');
end;
$$;

create or replace function public.toggle_nightly_job(enable boolean)
returns text
language plpgsql
security definer
set search_path = public, cron, pg_temp
as $$
begin
  if not public.is_dashboard_user() then
    raise exception using errcode = '42501', message = 'Dashboard access denied';
  end if;
  if enable then
    perform cron.schedule('nightly-archive', '0 22 * * *', 'SELECT nightly_archive_completed();');
    return 'enabled';
  end if;
  perform cron.unschedule('nightly-archive');
  return 'disabled';
exception when others then
  if sqlstate = '42501' then raise; end if;
  return case when enable then 'already_enabled' else 'already_disabled' end;
end;
$$;

revoke all on function public.is_nightly_job_active() from public, anon;
grant execute on function public.is_nightly_job_active() to authenticated;
revoke all on function public.toggle_nightly_job(boolean) from public, anon;
grant execute on function public.toggle_nightly_job(boolean) to authenticated;

revoke all on function public.trigger_activity_embedding() from public, anon, authenticated;
revoke all on function public.trigger_extract_structured_data() from public, anon, authenticated;
revoke all on function public.trigger_generate_embedding() from public, anon, authenticated;
revoke all on function public.trigger_ingest_transcript() from public, anon, authenticated;
