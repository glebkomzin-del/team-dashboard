-- A server token is restricted to one memory generation. The full Supabase
-- service credential stays inside the Edge runtime and is never exported.
create schema if not exists memory_private;
revoke all on schema memory_private from public,anon,authenticated;
grant usage on schema memory_private to service_role;
create table memory_private.service_tokens (
  token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
  space_id uuid not null references public.wm_spaces(id),
  label text not null,
  enabled boolean not null default true,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);
alter table memory_private.service_tokens enable row level security;
revoke all on memory_private.service_tokens from public,anon,authenticated,service_role;
grant select on memory_private.service_tokens to service_role;
create index wm_service_tokens_space on memory_private.service_tokens(space_id);
create function public.wm_service_scope(p_token_hash text)
returns table(space_id uuid,owner_id uuid) language sql stable security invoker set search_path='' as $$
  select t.space_id,s.owner_id from memory_private.service_tokens t
  join public.wm_spaces s on s.id=t.space_id
  where t.token_hash=p_token_hash and t.enabled
    and (t.expires_at is null or t.expires_at>now()) and s.state!='retired'
$$;
revoke all on function public.wm_service_scope(text) from public,anon,authenticated;
grant execute on function public.wm_service_scope(text) to service_role;
