begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
insert into auth.users(id) values('55555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label) values
 ('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Synthetic questions');
set local role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666';
 owner uuid:='55555555-5555-4555-8555-555555555555';q uuid:='77777777-7777-4777-8777-777777777777';
 r jsonb;snapshot uuid:=gen_random_uuid();
begin
 r:=public.wm_question_begin(s,q,owner,'{"question":"Was ist offen?"}',0,0,0);
 perform pg_temp.expect(r->>'request_hash'=encode(extensions.digest(convert_to('{"question":"Was ist offen?"}','UTF8'),'sha256'),'hex'),'request hash pinned');
 r:=public.wm_question_reserve(s,q,owner,0,'{"model":"gpt-5.6-terra"}',5000,10000);
 perform pg_temp.expect((r->>'send')::boolean,'first call reserved before sending');
 r:=public.wm_question_reserve(s,q,owner,0,'{"model":"gpt-5.6-terra"}',5000,10000);
 perform pg_temp.expect(not (r->>'send')::boolean and r->>'response_json' is null,'unresolved question call never resends');
 perform public.wm_question_receive(s,q,owner,0,'{"usage_final":true,"content":[]}',1200);
 r:=public.wm_question_reserve(s,q,owner,0,'{"model":"gpt-5.6-terra"}',5000,10000);
 perform pg_temp.expect(not (r->>'send')::boolean and r->>'response_json' is not null,'saved question response replays');
 r:=public.wm_question_reserve(s,q,owner,1,'{"model":"gpt-5.6-terra"}',5000,10000);
 perform pg_temp.expect(not (r->>'send')::boolean and (r->>'call_index')::integer=0,
  'request hash replays its original slot when cached stages change');
 r:=public.wm_question_begin(s,q,owner,'{"question":"Was ist offen?"}',0,0,0);
 perform pg_temp.expect((r->>'next_call_index')::integer=1,'retry starts after historical call slots');
 r:=public.wm_question_reserve(s,q,owner,1,'{"model":"gpt-5.6-terra","stage":2}',9000,10000);
 perform pg_temp.expect(r->>'state'='budget_exceeded','question budget includes actual settled cost');
 perform public.wm_question_complete(s,q,owner,'{"answer":"Belegt [E001].","citations":[]}');
 perform pg_temp.expect((public.wm_question_complete(s,q,owner,'{"answer":"Belegt [E001].","citations":[]}')->>'repeated')::boolean,'completion is idempotent');
 begin
  perform public.wm_question_begin(s,q,owner,'{"question":"Changed"}',0,0,0);
  raise exception 'FAILED: changed question identity accepted';
 exception when unique_violation then null; end;
 perform public.wm_backup_begin(s,snapshot);
 perform pg_temp.expect((select count(*)=1 from public.wm_backup_records where snapshot_id=snapshot and kind='question'),'question included in backup');
 perform pg_temp.expect((select count(*)=1 from public.wm_backup_records where snapshot_id=snapshot and kind='question_call'),'question cost call included in backup');
 perform public.wm_backup_release(s,snapshot);
end; $$;
reset role;
set local role authenticated;
select set_config('request.jwt.claim.sub','55555555-5555-4555-8555-555555555555',true);
do $$ begin
 begin
  perform 1 from public.wm_questions;
  raise exception 'FAILED: browser read private question prompts';
 exception when insufficient_privilege then null; end;
 begin
  perform 1 from public.wm_question_calls;
  raise exception 'FAILED: browser read provider receipts';
 exception when insufficient_privilege then null; end;
 begin
  perform public.wm_question_begin('66666666-6666-4666-8666-666666666666','88888888-8888-4888-8888-888888888888',
   '55555555-5555-4555-8555-555555555555','{}',0,0,0);
  raise exception 'FAILED: browser began a private provider call';
 exception when insufficient_privilege then null; end;
end; $$;
reset role;
rollback;
