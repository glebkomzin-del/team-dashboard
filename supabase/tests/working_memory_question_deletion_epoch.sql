begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;

insert into auth.users(id) values('85555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label)
values('86666666-6666-4666-8666-666666666666','85555555-5555-4555-8555-555555555555','Question deletion epoch');

set local role service_role;
do $$
declare
 s uuid:='86666666-6666-4666-8666-666666666666';
 owner uuid:='85555555-5555-4555-8555-555555555555';
 q uuid:='87777777-7777-4777-8777-777777777777';
 active uuid:='88888888-8888-4888-8888-888888888888';
 pending uuid:='89999999-9999-4999-8999-999999999999';
 r jsonb;
begin
 -- Stage changes the epoch before purge. An unknown paid call must settle
 -- first, or its later receipt would be correctly rejected and remain stuck.
 perform public.wm_question_begin(s,pending,owner,'{"question":"provider pending"}',0,0,0);
 perform public.wm_question_reserve(s,pending,owner,0,'{"model":"fixture"}',100,1000);
 begin
  update public.wm_spaces set deletion_revision=deletion_revision+1 where id=s;
  raise exception 'FAILED: pending provider question allowed deletion stage';
 exception when serialization_failure then null; end;
 perform public.wm_question_receive(s,pending,owner,0,'{"content":["settled"]}',10);
 perform public.wm_question_complete(s,pending,owner,'{"answer":"settled"}');

 r:=public.wm_question_begin(s,q,owner,'{"question":"Pinned evidence"}',0,0,0);
 perform pg_temp.expect(r->>'deletion_revision'='0','question pins the source-deletion epoch');

 -- Ordinary journal progress deliberately does not invalidate an already
 -- pinned question. It may still reserve, receive and complete normally.
 update public.wm_spaces set revision=revision+1 where id=s;
 perform public.wm_question_reserve(s,q,owner,0,'{"model":"fixture"}',100,1000);
 perform public.wm_question_receive(s,q,owner,0,'{"content":["settled"]}',10);
 r:=public.wm_question_reserve(s,q,owner,1,'{"model":"fixture","unlimited":true}',100,null);
 perform pg_temp.expect((r->>'send')::boolean,'null question budget permits the priced call');
 perform public.wm_question_receive(s,q,owner,1,'{"content":["settled unlimited"]}',10);
 perform public.wm_question_complete(s,q,owner,'{"answer":"settled"}');

 -- This is the post-purge epoch. A replay or any late provider write from the
 -- preceding context must fail before it can restore an old prompt or answer.
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=s;
 begin
  perform public.wm_question_begin(s,q,owner,'{"question":"Pinned evidence"}',1,0,1);
  raise exception 'FAILED: stale cached question replay was accepted';
 exception when serialization_failure then null; end;
 begin
  perform public.wm_question_reserve(s,q,owner,1,'{"model":"fixture","retry":true}',100,1000);
  raise exception 'FAILED: stale reserve was accepted';
 exception when serialization_failure then null; end;
 begin
  perform public.wm_question_receive(s,q,owner,0,'{"content":["late old context"]}',10);
  raise exception 'FAILED: stale provider receipt was accepted';
 exception when serialization_failure then null; end;
 begin
  perform public.wm_question_complete(s,q,owner,'{"answer":"late old context"}');
  raise exception 'FAILED: stale completion was accepted';
 exception when serialization_failure then null; end;
 begin
  perform public.wm_question_begin(s,gen_random_uuid(),owner,'{"question":"stale snapshot"}',1,0,0);
  raise exception 'FAILED: begin accepted a pre-deletion source snapshot';
 exception when serialization_failure then null; end;

 -- An abandoned question without a provider call must not permanently block a
 -- deletion. Its old epoch makes every later reserve/write fail instead.
 perform public.wm_question_begin(s,active,owner,'{"question":"free question"}',1,0,1);
 update public.wm_spaces set deletion_revision=deletion_revision+1 where id=s;
 perform pg_temp.expect((select deletion_revision=2 from public.wm_spaces where id=s),
  'abandoned no-call question does not permanently block deletion');
 begin
  perform public.wm_question_reserve(s,active,owner,0,'{"model":"late"}',100,1000);
  raise exception 'FAILED: abandoned pre-deletion question reserved a late call';
 exception when serialization_failure then null; end;
end; $$;
reset role;
rollback;
