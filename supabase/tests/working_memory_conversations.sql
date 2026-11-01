begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
insert into auth.users(id) values('11111111-1111-4111-8111-111111111111'),('22222222-2222-4222-8222-222222222222')
 on conflict(id) do nothing;
insert into public.wm_spaces(id,owner_id,label) values
 ('33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111','Conversation test');
set local role service_role;
do $$
declare s uuid:='33333333-3333-4333-8333-333333333333'; owner uuid:='11111111-1111-4111-8111-111111111111';
 c uuid:='44444444-4444-4444-8444-444444444444';q uuid:='55555555-5555-4555-8555-555555555555';
 failed uuid:='66666666-6666-4666-8666-666666666666';r jsonb;
begin
 r:=public.wm_conversation_create(s,c,owner,'Projekt X');
 perform pg_temp.expect(r->>'conversation_id'=c::text and not (r->>'repeated')::boolean,'conversation created');
 r:=public.wm_conversation_create(s,c,owner,'Projekt X');
 perform pg_temp.expect((r->>'repeated')::boolean,'conversation create idempotent');
 r:=public.wm_question_begin(s,q,owner,'{"request_id":"55555555-5555-4555-8555-555555555555","question":"Was ist offen?","conversation_id":"44444444-4444-4444-8444-444444444444"}',0,0,0,c);
 perform pg_temp.expect(r->>'conversation_id'=c::text,'question bound to conversation');
 perform public.wm_question_complete(s,q,owner,'{"answer":"Eine belegte Antwort.","citations":[],"coverage":{},"memory_actions":[]}');
 r:=public.wm_conversation_get(s,c,owner,null);
 perform pg_temp.expect(jsonb_array_length(r->'messages')=2,'conversation returns user and assistant turns');
 perform pg_temp.expect(r#>>'{messages,0,content}'='Was ist offen?' and r#>>'{messages,1,content}'='Eine belegte Antwort.','conversation content derives from question receipt');
 r:=public.wm_conversations_list(s,owner);
 perform pg_temp.expect((r#>>'{conversations,0,message_count}')::integer=2,'conversation list has message count');
 perform public.wm_question_begin(s,failed,owner,'{"request_id":"66666666-6666-4666-8666-666666666666","question":"Unbelegte Frage","conversation_id":"44444444-4444-4444-8444-444444444444"}',0,0,0,c);
 perform public.wm_question_complete(s,failed,owner,'{"_question_error":"invalid_or_ungrounded"}');
 r:=public.wm_conversation_get(s,c,owner,null);
 perform pg_temp.expect(jsonb_array_length(r->'messages')=3 and r#>>'{messages,2,role}'='user',
  'terminal failure does not create an assistant message without content');
 r:=public.wm_conversations_list(s,owner);
 perform pg_temp.expect((r#>>'{conversations,0,message_count}')::integer=3,'terminal failure counts only its visible user message');
 begin
  perform public.wm_conversation_create(s,c,owner,'Changed');
  raise exception 'FAILED: changed conversation retry accepted';
 exception when unique_violation then null; end;
 begin
  perform public.wm_conversation_create(s,gen_random_uuid(),'22222222-2222-4222-8222-222222222222','Forged');
  raise exception 'FAILED: wrong owner accepted';
 exception when invalid_parameter_value then null; end;
end; $$;
reset role;
set local role authenticated;
do $$ begin
 begin perform 1 from public.wm_conversations;raise exception 'FAILED: browser read conversations';
 exception when insufficient_privilege then null;end;
end; $$;
reset role;
rollback;
