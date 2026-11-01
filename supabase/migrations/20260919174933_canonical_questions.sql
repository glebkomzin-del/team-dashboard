-- Durable owner questions. They never append to the canonical work journal.
create table public.wm_questions (
 space_id uuid not null references public.wm_spaces(id), id uuid not null,
 actor_id uuid not null, revision bigint not null check(revision>=0),
 archive_revision bigint not null check(archive_revision>=0),
 request_json text not null check(jsonb_typeof(request_json::jsonb)='object'),
 request_hash text not null check(request_hash ~ '^[a-f0-9]{64}$'),
 response_json text check(jsonb_typeof(response_json::jsonb)='object'),
 response_hash text check(response_hash ~ '^[a-f0-9]{64}$'),
 created_at timestamptz not null default now(), completed_at timestamptz,
 primary key(space_id,id),
 check((response_json is null and response_hash is null and completed_at is null)
    or (response_json is not null and response_hash is not null and completed_at is not null))
);
create table public.wm_question_calls (
 space_id uuid not null, question_id uuid not null, call_index integer not null check(call_index between 0 and 1023),
 request_json text not null check(jsonb_typeof(request_json::jsonb)='object'),
 request_hash text not null check(request_hash ~ '^[a-f0-9]{64}$'),
 reserved_micro_usd bigint not null check(reserved_micro_usd>0), actual_micro_usd bigint check(actual_micro_usd>=0),
 response_json text check(jsonb_typeof(response_json::jsonb)='object'),
 response_hash text check(response_hash ~ '^[a-f0-9]{64}$'),
 created_at timestamptz not null default now(), received_at timestamptz,
 primary key(space_id,question_id,call_index), unique(space_id,question_id,request_hash),
 foreign key(space_id,question_id) references public.wm_questions(space_id,id),
 check((response_json is null and response_hash is null and received_at is null and actual_micro_usd is null)
    or (response_json is not null and response_hash is not null and received_at is not null))
);
alter table public.wm_questions enable row level security;
alter table public.wm_question_calls enable row level security;
revoke all on public.wm_questions,public.wm_question_calls from public,anon,authenticated,service_role;
grant select,insert,update on public.wm_questions,public.wm_question_calls to service_role;

create function public.wm_question_begin(p_space_id uuid,p_question_id uuid,p_actor_id uuid,
 p_request_json text,p_revision bigint,p_archive_revision bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; q public.wm_questions%rowtype; h text;
begin
 if p_request_json is null or octet_length(p_request_json)>64000 or jsonb_typeof(p_request_json::jsonb)!='object' then
  raise exception 'Invalid question request' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or s.owner_id is distinct from p_actor_id then
  raise exception 'Question owner mismatch' using errcode='22023'; end if;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id;
 if found then
  if q.actor_id is distinct from p_actor_id or q.request_hash!=h or q.request_json!=p_request_json then
   raise exception 'Question identity changed' using errcode='23505'; end if;
  return to_jsonb(q)||jsonb_build_object('next_call_index',(select count(*) from public.wm_question_calls
    where space_id=p_space_id and question_id=p_question_id));
 end if;
 if p_revision is distinct from s.revision or p_archive_revision is distinct from s.archive_revision then
  raise exception 'Question context changed' using errcode='40001'; end if;
 insert into public.wm_questions(space_id,id,actor_id,revision,archive_revision,request_json,request_hash)
 values(p_space_id,p_question_id,p_actor_id,p_revision,p_archive_revision,p_request_json,h) returning * into q;
 return to_jsonb(q)||jsonb_build_object('next_call_index',0);
end $$;

create function public.wm_question_reserve(p_space_id uuid,p_question_id uuid,p_actor_id uuid,p_call_index integer,
 p_request_json text,p_reserved_micro_usd bigint,p_budget_micro_usd bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare q public.wm_questions%rowtype; r public.wm_question_calls%rowtype; h text; total bigint;
begin
 perform 1 from public.wm_spaces where id=p_space_id for update;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id for update;
 if not found or q.actor_id is distinct from p_actor_id or q.response_json is not null then
  raise exception 'Question unavailable' using errcode='40001'; end if;
 if p_call_index is null or p_call_index<0 or p_call_index>1023 or p_request_json is null
   or octet_length(p_request_json)>1000000 or jsonb_typeof(p_request_json::jsonb)!='object'
   or p_reserved_micro_usd is null or p_reserved_micro_usd<=0 or p_budget_micro_usd is null or p_budget_micro_usd<=0 then
  raise exception 'Invalid question call' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into r from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and request_hash=h;
 if found then
  if r.request_json!=p_request_json or r.reserved_micro_usd!=p_reserved_micro_usd then
   raise exception 'Question call identity changed' using errcode='23505'; end if;
  return to_jsonb(r)||jsonb_build_object('send',false);
 end if;
 select * into r from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and call_index=p_call_index;
 if found then
  if r.request_hash!=h or r.reserved_micro_usd!=p_reserved_micro_usd then
   raise exception 'Question call identity changed' using errcode='23505'; end if;
  return to_jsonb(r)||jsonb_build_object('send',false);
 end if;
 if p_call_index!=(select count(*) from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id)
   or exists(select 1 from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and response_json is null) then
  raise exception 'Previous question call unresolved' using errcode='22023'; end if;
 select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) into total from public.wm_question_calls where space_id=p_space_id;
 if total+p_reserved_micro_usd>p_budget_micro_usd then
  return jsonb_build_object('send',false,'state','budget_exceeded','accounted_micro_usd',total); end if;
 insert into public.wm_question_calls(space_id,question_id,call_index,request_json,request_hash,reserved_micro_usd)
 values(p_space_id,p_question_id,p_call_index,p_request_json,h,p_reserved_micro_usd) returning * into r;
 return to_jsonb(r)||jsonb_build_object('send',true);
end $$;

create function public.wm_question_receive(p_space_id uuid,p_question_id uuid,p_actor_id uuid,p_call_index integer,
 p_response_json text,p_actual_micro_usd bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare q public.wm_questions%rowtype; r public.wm_question_calls%rowtype; h text;
begin
 perform 1 from public.wm_spaces where id=p_space_id for update;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id;
 if not found or q.actor_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 if p_response_json is null or octet_length(p_response_json)>1000000 or jsonb_typeof(p_response_json::jsonb)!='object'
   or (p_actual_micro_usd is not null and p_actual_micro_usd<0) then
  raise exception 'Invalid question response' using errcode='22023'; end if;
 select * into r from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and call_index=p_call_index for update;
 if not found then raise exception 'Question call was not reserved' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_response_json,'UTF8'),'sha256'),'hex');
 if r.response_json is not null then
  if r.response_hash!=h or r.actual_micro_usd is distinct from p_actual_micro_usd then
   raise exception 'Question response identity changed' using errcode='23505'; end if;
  return jsonb_build_object('saved',true,'repeated',true); end if;
 update public.wm_question_calls set response_json=p_response_json,response_hash=h,
  actual_micro_usd=p_actual_micro_usd,received_at=now()
 where space_id=p_space_id and question_id=p_question_id and call_index=p_call_index;
 return jsonb_build_object('saved',true,'repeated',false);
end $$;

create function public.wm_question_complete(p_space_id uuid,p_question_id uuid,p_actor_id uuid,p_response_json text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare q public.wm_questions%rowtype; h text;
begin
 perform 1 from public.wm_spaces where id=p_space_id for update;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id for update;
 if not found or q.actor_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 if p_response_json is null or octet_length(p_response_json)>1000000 or jsonb_typeof(p_response_json::jsonb)!='object'
   or exists(select 1 from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and response_json is null) then
  raise exception 'Incomplete question result' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_response_json,'UTF8'),'sha256'),'hex');
 if q.response_json is not null then
  if q.response_hash!=h then raise exception 'Question result changed' using errcode='23505'; end if;
  return jsonb_build_object('saved',true,'repeated',true); end if;
 update public.wm_questions set response_json=p_response_json,response_hash=h,completed_at=now()
 where space_id=p_space_id and id=p_question_id;
 return jsonb_build_object('saved',true,'repeated',false);
end $$;

do $$ declare f record; begin
 for f in select oid::regprocedure signature from pg_proc where pronamespace='public'::regnamespace and proname like 'wm_question_%' loop
  execute format('revoke all on function %s from public,anon,authenticated',f.signature);
  execute format('grant execute on function %s to service_role',f.signature);
 end loop;
end $$;

-- Question receipts are part of the same encrypted/off-server recovery set.
alter table public.wm_backup_records drop constraint wm_backup_records_kind_check;
alter table public.wm_backup_records add constraint wm_backup_records_kind_check check(kind in
 ('config','job','call','job_decision','generation_review','search_document','search_snapshot','search_result','question','question_call'));
-- Extend the installed backup implementation without overwriting its paging
-- optimizations. Questions/calls are mutable and must be copied atomically.
do $$ declare definition text; begin
 select pg_get_functiondef('public.wm_backup_begin(uuid,uuid)'::regprocedure) into definition;
 if position(') x;' in definition)=0 then raise exception 'Unexpected backup implementation'; end if;
 execute replace(definition,') x;',$branch$
  union all select 'question',to_jsonb(q)::text from public.wm_questions q where q.space_id=p_space_id
  union all select 'question_call',to_jsonb(qc)::text from public.wm_question_calls qc where qc.space_id=p_space_id
 ) x;$branch$);
end $$;
