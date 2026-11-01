-- A question is pinned to the deletion epoch in which its context was read.
-- Normal journal revisions may advance afterwards; a source deletion must not
-- permit a late provider receipt or a replay to reintroduce that old context.
do $$ begin
 if exists(select 1 from public.wm_source_deletions where state in ('prepared','purging')) then
  raise exception 'Question epoch migration requires no active source deletion' using errcode='40001';
 end if;
end $$;
alter table public.wm_questions add column deletion_revision bigint;
update public.wm_questions q set deletion_revision=s.deletion_revision
 from public.wm_spaces s where s.id=q.space_id;
alter table public.wm_questions alter column deletion_revision set not null;
alter table public.wm_questions add constraint wm_questions_deletion_revision_check check(deletion_revision>=0);

create or replace function public.wm_question_epoch_write_guard()
returns trigger language plpgsql security invoker set search_path='' as $$
declare current_revision bigint;
begin
 select deletion_revision into current_revision from public.wm_spaces where id=new.space_id for key share;
 if not found or new.deletion_revision is distinct from current_revision then
  raise exception 'Question deletion epoch changed' using errcode='40001';
 end if;
 return new;
end; $$;

create or replace function public.wm_question_call_epoch_write_guard()
returns trigger language plpgsql security invoker set search_path='' as $$
declare question_revision bigint; current_revision bigint;
begin
 select q.deletion_revision,s.deletion_revision into question_revision,current_revision
 from public.wm_questions q join public.wm_spaces s on s.id=q.space_id
 where q.space_id=new.space_id and q.id=new.question_id for key share of s;
 if not found or question_revision is distinct from current_revision then
  raise exception 'Question deletion epoch changed' using errcode='40001';
 end if;
 return new;
end; $$;

-- Stage advances the epoch before purge.  A provider outcome that is still
-- unknown must settle first; otherwise the new epoch would correctly reject
-- its receipt but leave the paid call unresolved forever.  A question with no
-- reserved call is deliberately not included: its old epoch invalidates it.
create or replace function public.wm_space_deletion_pending_work_guard()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if new.deletion_revision is distinct from old.deletion_revision and (
   exists(select 1 from public.wm_jobs j where j.space_id=new.id and j.state in ('running','prepared'))
   or exists(select 1 from public.wm_model_calls c where c.space_id=new.id and c.response_json is null and c.redaction_id is null)
   or exists(select 1 from public.wm_question_calls c where c.space_id=new.id and c.response_json is null and c.redaction_id is null)
 ) then
  raise exception 'Active unresolved call or job blocks deletion epoch' using errcode='40001';
 end if;
 return new;
end; $$;

-- Purge sanitizes existing question receipts in its own transaction before it
-- advances the space epoch.  Only new direct writes need this table-level
-- guard; RPC updates below independently compare the pinned epoch.
create trigger wm_questions_deletion_epoch_guard before insert on public.wm_questions
 for each row execute function public.wm_question_epoch_write_guard();
create trigger wm_question_calls_deletion_epoch_guard before insert on public.wm_question_calls
 for each row execute function public.wm_question_call_epoch_write_guard();
create trigger wm_spaces_pending_work_deletion_guard before update of deletion_revision on public.wm_spaces
 for each row execute function public.wm_space_deletion_pending_work_guard();

drop function public.wm_question_begin(uuid,uuid,uuid,text,bigint,bigint);
create function public.wm_question_begin(p_space_id uuid,p_question_id uuid,p_actor_id uuid,
 p_request_json text,p_revision bigint,p_archive_revision bigint,p_deletion_revision bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; q public.wm_questions%rowtype; h text;
begin
 if p_request_json is null or octet_length(p_request_json)>64000 or jsonb_typeof(p_request_json::jsonb)!='object' then
  raise exception 'Invalid question request' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or s.owner_id is distinct from p_actor_id then
  raise exception 'Question owner mismatch' using errcode='22023'; end if;
 if p_revision is distinct from s.revision or p_archive_revision is distinct from s.archive_revision
    or p_deletion_revision is distinct from s.deletion_revision then
  raise exception 'Question context changed' using errcode='40001'; end if;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id for update;
 if found then
  if q.actor_id is distinct from p_actor_id then raise exception 'Question identity changed' using errcode='23505'; end if;
  if q.deletion_revision is distinct from s.deletion_revision then
   raise exception 'Question deletion epoch changed' using errcode='40001'; end if;
  if q.request_hash!=h or q.request_json!=p_request_json then raise exception 'Question identity changed' using errcode='23505'; end if;
  return to_jsonb(q)||jsonb_build_object('next_call_index',(select count(*) from public.wm_question_calls
    where space_id=p_space_id and question_id=p_question_id));
 end if;
 insert into public.wm_questions(space_id,id,actor_id,revision,archive_revision,deletion_revision,request_json,request_hash)
 values(p_space_id,p_question_id,p_actor_id,p_revision,p_archive_revision,p_deletion_revision,p_request_json,h) returning * into q;
 return to_jsonb(q)||jsonb_build_object('next_call_index',0);
end $$;

create or replace function public.wm_question_reserve(p_space_id uuid,p_question_id uuid,p_actor_id uuid,p_call_index integer,
 p_request_json text,p_reserved_micro_usd bigint,p_budget_micro_usd bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; q public.wm_questions%rowtype; r public.wm_question_calls%rowtype; h text; total bigint;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.owner_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id for update;
 if not found or q.actor_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 if q.deletion_revision is distinct from s.deletion_revision then raise exception 'Question deletion epoch changed' using errcode='40001'; end if;
 if q.response_json is not null then raise exception 'Question unavailable' using errcode='40001'; end if;
 if p_call_index is null or p_call_index<0 or p_call_index>1023 or p_request_json is null
   or octet_length(p_request_json)>1000000 or jsonb_typeof(p_request_json::jsonb)!='object'
   or p_reserved_micro_usd is null or p_reserved_micro_usd<=0 or (p_budget_micro_usd is not null and p_budget_micro_usd<=0) then
  raise exception 'Invalid question call' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into r from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and request_hash=h;
 if found then
  if r.request_json!=p_request_json or r.reserved_micro_usd!=p_reserved_micro_usd then raise exception 'Question call identity changed' using errcode='23505'; end if;
  return to_jsonb(r)||jsonb_build_object('send',false);
 end if;
 select * into r from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and call_index=p_call_index;
 if found then
  if r.request_hash!=h or r.reserved_micro_usd!=p_reserved_micro_usd then raise exception 'Question call identity changed' using errcode='23505'; end if;
  return to_jsonb(r)||jsonb_build_object('send',false);
 end if;
 if p_call_index!=(select count(*) from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id)
   or exists(select 1 from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and response_json is null) then
  raise exception 'Previous question call unresolved' using errcode='22023'; end if;
 select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) into total from public.wm_question_calls where space_id=p_space_id;
 if p_budget_micro_usd is not null and total+p_reserved_micro_usd>p_budget_micro_usd then
  return jsonb_build_object('send',false,'state','budget_exceeded','accounted_micro_usd',total); end if;
 insert into public.wm_question_calls(space_id,question_id,call_index,request_json,request_hash,reserved_micro_usd)
 values(p_space_id,p_question_id,p_call_index,p_request_json,h,p_reserved_micro_usd) returning * into r;
 return to_jsonb(r)||jsonb_build_object('send',true);
end $$;

create or replace function public.wm_question_receive(p_space_id uuid,p_question_id uuid,p_actor_id uuid,p_call_index integer,
 p_response_json text,p_actual_micro_usd bigint)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; q public.wm_questions%rowtype; r public.wm_question_calls%rowtype; h text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.owner_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id for update;
 if not found or q.actor_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 if q.deletion_revision is distinct from s.deletion_revision then raise exception 'Question deletion epoch changed' using errcode='40001'; end if;
 if p_response_json is null or octet_length(p_response_json)>1000000 or jsonb_typeof(p_response_json::jsonb)!='object'
   or (p_actual_micro_usd is not null and p_actual_micro_usd<0) then raise exception 'Invalid question response' using errcode='22023'; end if;
 select * into r from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and call_index=p_call_index for update;
 if not found then raise exception 'Question call was not reserved' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_response_json,'UTF8'),'sha256'),'hex');
 if r.response_json is not null then
  if r.response_hash!=h or r.actual_micro_usd is distinct from p_actual_micro_usd then raise exception 'Question response identity changed' using errcode='23505'; end if;
  return jsonb_build_object('saved',true,'repeated',true);
 end if;
 update public.wm_question_calls set response_json=p_response_json,response_hash=h,actual_micro_usd=p_actual_micro_usd,received_at=now()
 where space_id=p_space_id and question_id=p_question_id and call_index=p_call_index;
 return jsonb_build_object('saved',true,'repeated',false);
end $$;

create or replace function public.wm_question_complete(p_space_id uuid,p_question_id uuid,p_actor_id uuid,p_response_json text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; q public.wm_questions%rowtype; h text;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.owner_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id for update;
 if not found or q.actor_id is distinct from p_actor_id then raise exception 'Question unavailable' using errcode='40001'; end if;
 if q.deletion_revision is distinct from s.deletion_revision then raise exception 'Question deletion epoch changed' using errcode='40001'; end if;
 if p_response_json is null or octet_length(p_response_json)>1000000 or jsonb_typeof(p_response_json::jsonb)!='object'
   or exists(select 1 from public.wm_question_calls where space_id=p_space_id and question_id=p_question_id and response_json is null) then
  raise exception 'Incomplete question result' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_response_json,'UTF8'),'sha256'),'hex');
 if q.response_json is not null then
  if q.response_hash!=h then raise exception 'Question result changed' using errcode='23505'; end if;
  return jsonb_build_object('saved',true,'repeated',true);
 end if;
 update public.wm_questions set response_json=p_response_json,response_hash=h,completed_at=now()
 where space_id=p_space_id and id=p_question_id;
 return jsonb_build_object('saved',true,'repeated',false);
end $$;

revoke all on function public.wm_question_begin(uuid,uuid,uuid,text,bigint,bigint,bigint),
 public.wm_question_reserve(uuid,uuid,uuid,integer,text,bigint,bigint),
 public.wm_question_receive(uuid,uuid,uuid,integer,text,bigint),
 public.wm_question_complete(uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.wm_question_begin(uuid,uuid,uuid,text,bigint,bigint,bigint),
 public.wm_question_reserve(uuid,uuid,uuid,integer,text,bigint,bigint),
 public.wm_question_receive(uuid,uuid,uuid,integer,text,bigint),
 public.wm_question_complete(uuid,uuid,uuid,text) to service_role;
