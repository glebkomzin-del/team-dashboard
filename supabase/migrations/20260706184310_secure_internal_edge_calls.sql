create or replace function public.trigger_ingest_transcript()
returns trigger
language plpgsql
security definer
set search_path = public, vault, extensions, pg_temp
as $$
declare
  _url text := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/ingest-transcript';
  _anon_key text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM';
  _secret text;
begin
  if new.raw_transcript is null and new.source_file is null then return new; end if;
  select decrypted_secret into _secret from vault.decrypted_secrets where name='internal_function_secret';
  if _secret is null then raise exception 'Internal function secret missing'; end if;
  perform net.http_post(
    url := _url,
    headers := jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||_anon_key,'x-internal-secret',_secret),
    body := jsonb_build_object('meeting_id',new.id::text,'source_file',new.source_file)
  );
  return new;
end;
$$;

create or replace function public.trigger_extract_structured_data()
returns trigger
language plpgsql
security definer
set search_path = public, vault, extensions, pg_temp
as $$
declare
  _secret text;
begin
  select decrypted_secret into _secret from vault.decrypted_secrets where name='internal_function_secret';
  if _secret is null then raise exception 'Internal function secret missing'; end if;
  perform net.http_post(
    url := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/extract-structured-data',
    headers := jsonb_build_object('Content-Type','application/json','x-internal-secret',_secret),
    body := jsonb_build_object('meeting_id',new.id)
  );
  return new;
end;
$$;

create or replace function public.trigger_generate_embedding()
returns trigger
language plpgsql
security definer
set search_path = public, vault, extensions, pg_temp
as $$
declare
  _entity_type text;
  _action text;
  _url text := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/generate-embedding';
  _anon_key text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM';
  _secret text;
  _entity_id uuid;
begin
  select decrypted_secret into _secret from vault.decrypted_secrets where name='internal_function_secret';
  if _secret is null then raise exception 'Internal function secret missing'; end if;
  _entity_type := case tg_table_name when 'todos' then 'todo' when 'blockers' then 'blocker' when 'open_items' then 'open_item' when 'meetings' then 'meeting' when 'decisions' then 'decision' when 'projects' then 'project' else tg_table_name end;
  if tg_op='DELETE' then _action := 'deleted'; _entity_id := old.id; else _action := case when tg_op='INSERT' then 'created' else 'updated' end; _entity_id := new.id; end if;
  perform net.http_post(
    url := _url,
    headers := jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||_anon_key,'x-internal-secret',_secret),
    body := jsonb_build_object('entity_type',_entity_type,'entity_id',_entity_id::text,'action',_action)
  );
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$$;

create or replace function public.trigger_activity_embedding()
returns trigger
language plpgsql
security definer
set search_path = public, vault, extensions, pg_temp
as $$
declare
  _anon_key text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM';
  _secret text;
begin
  select decrypted_secret into _secret from vault.decrypted_secrets where name='internal_function_secret';
  if _secret is null then raise exception 'Internal function secret missing'; end if;
  perform net.http_post(
    url := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/generate-embedding',
    headers := jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||_anon_key,'x-internal-secret',_secret),
    body := jsonb_build_object('entity_type','activity','entity_id',new.id,'action','INSERT')
  );
  return new;
end;
$$;

revoke all on function public.trigger_ingest_transcript() from public, anon, authenticated;
revoke all on function public.trigger_extract_structured_data() from public, anon, authenticated;
revoke all on function public.trigger_generate_embedding() from public, anon, authenticated;
revoke all on function public.trigger_activity_embedding() from public, anon, authenticated;
