-- Owner-scoped, resumable memory-chat conversations. Message bodies remain in
-- wm_questions so source deletion, immutable receipts and model-call accounting
-- keep one canonical copy.
create table public.wm_conversations (
 space_id uuid not null references public.wm_spaces(id) on delete cascade,
 id uuid not null,
 owner_id uuid not null,
 title text not null default 'Neues Gespräch' check(char_length(title) between 1 and 200),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 primary key(space_id,id)
);
alter table public.wm_conversations enable row level security;
revoke all on public.wm_conversations from public,anon,authenticated,service_role;
grant select,insert,update on public.wm_conversations to service_role;

alter table public.wm_questions
 add column conversation_id uuid,
 add column conversation_seq bigint,
 add constraint wm_questions_conversation_fkey foreign key(space_id,conversation_id)
   references public.wm_conversations(space_id,id) on delete cascade;
create unique index wm_questions_conversation_idx
 on public.wm_questions(space_id,conversation_id,conversation_seq)
 where conversation_id is not null;

create function public.wm_conversation_create(p_space_id uuid,p_conversation_id uuid,p_actor_id uuid,p_title text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; c public.wm_conversations%rowtype; chosen text;
begin
 chosen:=coalesce(nullif(btrim(p_title),''),'Neues Gespräch');
 if char_length(chosen)>200 then raise exception 'Invalid conversation title' using errcode='22023'; end if;
 select * into s from public.wm_spaces where id=p_space_id;
 if not found or s.state='retired' or s.owner_id is distinct from p_actor_id then
  raise exception 'Conversation owner mismatch' using errcode='22023'; end if;
 select * into c from public.wm_conversations where space_id=p_space_id and id=p_conversation_id;
 if found then
  if c.owner_id is distinct from p_actor_id or c.title is distinct from chosen then
   raise exception 'Conversation identity changed' using errcode='23505'; end if;
  return (to_jsonb(c)-'space_id'-'owner_id')||jsonb_build_object('conversation_id',c.id,'repeated',true);
 end if;
 insert into public.wm_conversations(space_id,id,owner_id,title)
 values(p_space_id,p_conversation_id,p_actor_id,chosen) returning * into c;
 return (to_jsonb(c)-'space_id'-'owner_id')||jsonb_build_object('conversation_id',c.id,'repeated',false);
end $$;

create function public.wm_conversations_list(p_space_id uuid,p_actor_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if not exists(select 1 from public.wm_spaces where id=p_space_id and owner_id=p_actor_id and state!='retired') then
  raise exception 'Conversation owner mismatch' using errcode='22023'; end if;
 select coalesce(jsonb_agg(item order by item->>'updated_at' desc),'[]'::jsonb) into result
 from (
  select jsonb_build_object(
   'conversation_id',c.id,'title',c.title,'created_at',c.created_at,'updated_at',c.updated_at,
   'message_count',(select count(request_json)+count(*) filter(where response_json is not null
                      and nullif(btrim(response_json::jsonb->>'answer'),'') is not null) from public.wm_questions q
                    where q.space_id=c.space_id and q.conversation_id=c.id),
   'last_message_preview',coalesce((select left(coalesce(q.response_json::jsonb->>'answer',q.request_json::jsonb->>'question',''),240)
                    from public.wm_questions q where q.space_id=c.space_id and q.conversation_id=c.id
                    order by q.conversation_seq desc limit 1),'')
  ) item from public.wm_conversations c
  where c.space_id=p_space_id and c.owner_id=p_actor_id
 ) rows;
 return jsonb_build_object('conversations',result);
end $$;

create function public.wm_conversation_get(p_space_id uuid,p_conversation_id uuid,p_actor_id uuid,p_before_question_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare c public.wm_conversations%rowtype; before_seq bigint; messages jsonb;
begin
 select * into c from public.wm_conversations where space_id=p_space_id and id=p_conversation_id and owner_id=p_actor_id;
 if not found then return null; end if;
 if p_before_question_id is not null then
  select conversation_seq into before_seq from public.wm_questions
   where space_id=p_space_id and id=p_before_question_id and conversation_id=p_conversation_id;
  if before_seq is null then raise exception 'Question is not in conversation' using errcode='22023'; end if;
 end if;
 select coalesce(jsonb_agg(message order by seq,ordinal),'[]'::jsonb) into messages from (
  select q.conversation_seq seq,0 ordinal,jsonb_build_object(
   'message_id','q:'||q.id::text||':user','role','user','content',q.request_json::jsonb->>'question',
   'created_at',q.created_at,'request_id',q.id) message
  from public.wm_questions q where q.space_id=p_space_id and q.conversation_id=p_conversation_id
   and q.request_json is not null and (before_seq is null or q.conversation_seq<before_seq)
  union all
  select q.conversation_seq seq,1 ordinal,jsonb_strip_nulls(jsonb_build_object(
   'message_id','q:'||q.id::text||':assistant','role','assistant','content',q.response_json::jsonb->>'answer',
   'created_at',q.completed_at,'request_id',q.id,'citations',q.response_json::jsonb->'citations',
   'coverage',q.response_json::jsonb->'coverage','memory_actions',q.response_json::jsonb->'memory_actions')) message
  from public.wm_questions q where q.space_id=p_space_id and q.conversation_id=p_conversation_id
   and q.response_json is not null and nullif(btrim(q.response_json::jsonb->>'answer'),'') is not null
   and (before_seq is null or q.conversation_seq<before_seq)
 ) turns;
 return jsonb_build_object('conversation',
  (to_jsonb(c)-'space_id'-'owner_id')||jsonb_build_object('conversation_id',c.id),
  'messages',messages);
end $$;

-- Overload the pinned question begin RPC so old direct callers keep the reviewed
-- seven-argument contract while the chat gateway can bind an optional thread.
create function public.wm_question_begin(p_space_id uuid,p_question_id uuid,p_actor_id uuid,
 p_request_json text,p_revision bigint,p_archive_revision bigint,p_deletion_revision bigint,p_conversation_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.wm_spaces%rowtype; q public.wm_questions%rowtype; h text; next_seq bigint;
begin
 if p_request_json is null or octet_length(p_request_json)>64000 or jsonb_typeof(p_request_json::jsonb)!='object' then
  raise exception 'Invalid question request' using errcode='22023'; end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' or s.owner_id is distinct from p_actor_id then
  raise exception 'Question owner mismatch' using errcode='22023'; end if;
 if p_conversation_id is not null and not exists(select 1 from public.wm_conversations
   where space_id=p_space_id and id=p_conversation_id and owner_id=p_actor_id) then
  raise exception 'Unknown conversation' using errcode='22023'; end if;
 if p_revision is distinct from s.revision or p_archive_revision is distinct from s.archive_revision
    or p_deletion_revision is distinct from s.deletion_revision then
  raise exception 'Question context changed' using errcode='40001'; end if;
 select * into q from public.wm_questions where space_id=p_space_id and id=p_question_id for update;
 if found then
  if q.actor_id is distinct from p_actor_id or q.conversation_id is distinct from p_conversation_id then
   raise exception 'Question identity changed' using errcode='23505'; end if;
  if q.deletion_revision is distinct from s.deletion_revision then
   raise exception 'Question deletion epoch changed' using errcode='40001'; end if;
  if q.request_hash!=h or q.request_json!=p_request_json then raise exception 'Question identity changed' using errcode='23505'; end if;
  return to_jsonb(q)||jsonb_build_object('next_call_index',(select count(*) from public.wm_question_calls
    where space_id=p_space_id and question_id=p_question_id));
 end if;
 if p_conversation_id is not null then
  select coalesce(max(conversation_seq),0)+1 into next_seq from public.wm_questions
   where space_id=p_space_id and conversation_id=p_conversation_id;
 end if;
 insert into public.wm_questions(space_id,id,actor_id,revision,archive_revision,deletion_revision,
   request_json,request_hash,conversation_id,conversation_seq)
 values(p_space_id,p_question_id,p_actor_id,p_revision,p_archive_revision,p_deletion_revision,
   p_request_json,h,p_conversation_id,next_seq) returning * into q;
 if p_conversation_id is not null then
  update public.wm_conversations set updated_at=now() where space_id=p_space_id and id=p_conversation_id;
 end if;
 return to_jsonb(q)||jsonb_build_object('next_call_index',0);
end $$;

create function public.wm_conversation_touch() returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if new.conversation_id is not null and new.response_json is not null and old.response_json is null then
  update public.wm_conversations set updated_at=new.completed_at
   where space_id=new.space_id and id=new.conversation_id;
 end if;
 return new;
end $$;
create trigger wm_questions_conversation_touch after update of response_json on public.wm_questions
 for each row execute function public.wm_conversation_touch();

do $$ declare f record; begin
 for f in select oid::regprocedure signature from pg_proc where pronamespace='public'::regnamespace
  and proname in ('wm_conversation_create','wm_conversations_list','wm_conversation_get','wm_question_begin','wm_conversation_touch') loop
  execute format('revoke all on function %s from public,anon,authenticated',f.signature);
  execute format('grant execute on function %s to service_role',f.signature);
 end loop;
end $$;
