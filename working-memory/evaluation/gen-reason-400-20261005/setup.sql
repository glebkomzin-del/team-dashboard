create role service_role;
create role anon;
create role authenticated;
create schema auth;
create schema extensions;
create extension pgcrypto with schema extensions;
create table auth.users(id uuid primary key);
create table public.wm_spaces(
 id uuid primary key, owner_id uuid not null references auth.users(id),
 state text not null default 'active', revision bigint not null default 0
);
create table public.wm_jobs(
 space_id uuid not null references public.wm_spaces(id), id text not null,
 updated_at timestamptz not null, state text not null, lease_until timestamptz,
 reason text, applied_revision bigint, primary key(space_id,id)
);
create table public.wm_generation_reviews(
 space_id uuid not null references public.wm_spaces(id), id uuid not null,
 expected_revision bigint not null, review_sha256 text not null,
 state text not null default 'pending', payload jsonb not null,
 job_id text, job_updated_at timestamptz,
 decision_command_id uuid, decision_actor_id uuid,
 decision_reason text, decision_hash text, decision_result jsonb, decided_at timestamptz,
 primary key(space_id,id), unique(space_id,decision_command_id)
);
create table public.wm_source_versions(
 space_id uuid not null, id text not null, source_id text not null,
 content_hash text not null, event_date date not null, title text not null,
 transcript text not null, observed_at timestamptz not null,
 primary key(space_id,id)
);
create table public.wm_journal(
 space_id uuid not null, revision bigint not null, command_id uuid not null,
 request_hash text not null, kind text not null, actor_id uuid,
 payload jsonb not null, primary key(space_id,revision)
);
create table public.wm_job_decisions(
 space_id uuid not null, command_id uuid not null, job_id text not null,
 actor_id uuid not null, action text not null, reason text not null,
 request jsonb not null, previous_job jsonb not null, result jsonb not null,
 primary key(space_id,command_id),
 constraint wm_job_decisions_reason_check check(length(trim(reason)) between 1 and 4000)
);
insert into auth.users(id) values ('11111111-1111-4111-8111-111111111111');
insert into public.wm_spaces(id,owner_id) values
 ('22222222-2222-4222-8222-222222222222','11111111-1111-4111-8111-111111111111');
insert into public.wm_jobs(space_id,id,updated_at,state) values
 ('22222222-2222-4222-8222-222222222222','job-empty','2026-10-05 19:00:00+00','review'),
 ('22222222-2222-4222-8222-222222222222','job-note','2026-10-05 19:01:00+00','review');
insert into public.wm_generation_reviews(space_id,id,expected_revision,review_sha256,payload,job_id,job_updated_at) values
 ('22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333331',0,repeat('a',64),'{"new_sources":[]}'::jsonb,'job-empty','2026-10-05 19:00:00+00'),
 ('22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333332',1,repeat('b',64),'{"new_sources":[]}'::jsonb,'job-note','2026-10-05 19:01:00+00'),
 ('22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333',2,repeat('c',64),'{"new_sources":[]}'::jsonb,null,null),
 ('22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333334',2,repeat('d',64),'{"new_sources":[]}'::jsonb,null,null);
insert into public.wm_journal(space_id,revision,command_id,request_hash,kind,actor_id,payload)
select '22222222-2222-4222-8222-222222222222',100+n,
 ('44444444-4444-4444-8444-'||lpad(n::text,12,'0'))::uuid,
 repeat('f',64),'human','11111111-1111-4111-8111-111111111111','{}'::jsonb
from generate_series(1,11) n;
