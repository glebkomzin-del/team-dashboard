\set ON_ERROR_STOP on
drop table if exists public.wm_job_decisions,public.wm_model_calls,public.wm_jobs,
  public.wm_processing_config,public.wm_spaces cascade;
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create table public.wm_spaces (
  id uuid primary key, owner_id uuid not null, state text not null,
  revision bigint not null
);
create table public.wm_processing_config (
  space_id uuid primary key references public.wm_spaces(id), enabled boolean not null,
  automatic_from date, pipeline text, budget_micro_usd bigint,
  updated_at timestamptz not null default now()
);
create table public.wm_jobs (
  space_id uuid not null references public.wm_spaces(id), id text not null,
  document_id text not null, source_id text not null, event_date date not null,
  pipeline text not null, state text not null, reason text, expected_revision bigint,
  lease_token uuid, lease_until timestamptz, attempts integer not null default 0,
  command_id uuid not null default gen_random_uuid(), prepared_payload jsonb,
  applied_revision bigint, created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(), primary key(space_id,id)
);
create table public.wm_model_calls (
  space_id uuid not null, job_id text not null, call_index integer not null,
  request_json text not null, request_hash text not null,
  reserved_micro_usd bigint not null, actual_micro_usd bigint,
  response_json text, response_hash text, created_at timestamptz not null default now(),
  received_at timestamptz, primary key(space_id,job_id,call_index),
  foreign key(space_id,job_id) references public.wm_jobs(space_id,id)
);
create table public.wm_job_decisions (
  space_id uuid not null,command_id uuid not null,job_id text not null,actor_id uuid not null,
  action text not null,reason text not null,request jsonb not null,
  previous_job jsonb not null,result jsonb not null,recorded_at timestamptz not null default now(),
  primary key(space_id,command_id),foreign key(space_id,job_id) references public.wm_jobs(space_id,id),
  constraint wm_job_decisions_action_check check(action in ('retry','archive_only','rebase_prepared','apply_generation','pipeline_cutover')),
  constraint wm_job_decisions_reason_check check(length(trim(reason)) between 1 and 4000)
);
insert into public.wm_spaces values(
  '96a2dc44-9b9e-4644-b236-c5c1956cd39d','11111111-1111-4111-8111-111111111111','active',226);
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
values('96a2dc44-9b9e-4644-b236-c5c1956cd39d',false,'2026-09-08',
  'v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c',null);
insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state,applied_revision)
values
('96a2dc44-9b9e-4644-b236-c5c1956cd39d',repeat('a',64),'doc-a','source-a','2026-10-01','v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c','queued',null),
('96a2dc44-9b9e-4644-b236-c5c1956cd39d',repeat('b',64),'doc-b','source-b','2026-10-02','v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c','queued',null),
('96a2dc44-9b9e-4644-b236-c5c1956cd39d',repeat('c',64),'doc-c','source-c','2026-09-30','v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c','applied',225),
('96a2dc44-9b9e-4644-b236-c5c1956cd39d',repeat('d',64),'doc-d','source-d','2026-09-29','v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c','archived',null);
insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd,
  actual_micro_usd,response_json,response_hash,received_at)
values('96a2dc44-9b9e-4644-b236-c5c1956cd39d',repeat('c',64),0,'{}',repeat('1',64),10,8,'{}',repeat('2',64),now());
