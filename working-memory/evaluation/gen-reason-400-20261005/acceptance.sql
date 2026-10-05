do $$
declare r jsonb; s uuid := '22222222-2222-4222-8222-222222222222'; a uuid := '11111111-1111-4111-8111-111111111111';
begin
  perform pg_temp.expect(has_function_privilege('service_role','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE'),'service ACL retained');
  perform pg_temp.expect(not has_function_privilege('anon','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE'),'anon denied');
  perform pg_temp.expect(not has_function_privilege('authenticated','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE'),'browser role denied');
  perform pg_temp.expect(not (select prosecdef from pg_proc where oid='public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure),'security invoker');

  r:=public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333331',a,
    '55555555-5555-4555-8555-555555555551',0,repeat('a',64),'accept','');
  perform pg_temp.expect(r->>'state'='accepted' and r->>'revision'='1' and r->>'repeated'='false','empty note acceptance');
  perform pg_temp.expect((select length(trim(reason)) between 1 and 4000 and reason like 'Technischer Auditvermerk:%'
    and request->>'reason'='' from public.wm_job_decisions where job_id='job-empty'),'audit fallback and original request');
  perform pg_temp.expect((select decision_reason='' and state='accepted' from public.wm_generation_reviews
    where id='33333333-3333-4333-8333-333333333331'),'original review note remains empty');
  perform pg_temp.expect((select state='applied' and applied_revision=1 from public.wm_jobs where id='job-empty'),'job applied');
  perform pg_temp.expect((select count(*)=11 from public.wm_journal where kind='human'),'eleven human records preserved');
  perform pg_temp.expect((select count(*)=1 from public.wm_journal where kind='generation'),'one generation journal');
  r:=public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333331',a,
    '55555555-5555-4555-8555-555555555551',0,repeat('a',64),'accept','');
  perform pg_temp.expect(r->>'repeated'='true' and (select count(*)=1 from public.wm_job_decisions),'idempotent repeat');
  begin
    perform public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333331',a,
      '55555555-5555-4555-8555-555555555551',0,repeat('a',64),'accept','changed');
    raise exception 'Expected decision hash conflict';
  exception when unique_violation then null; end;

  r:=public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333332',a,
    '55555555-5555-4555-8555-555555555552',1,repeat('b',64),'accept','Owner provided note');
  perform pg_temp.expect(r->>'state'='accepted' and r->>'revision'='2','nonempty note acceptance');
  perform pg_temp.expect((select reason='Owner provided note' and request->>'reason'='Owner provided note'
    from public.wm_job_decisions where job_id='job-note'),'nonempty audit unchanged');

  r:=public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333333',a,
    '55555555-5555-4555-8555-555555555553',2,repeat('c',64),'reject','');
  perform pg_temp.expect(r->>'state'='rejected' and r->>'revision'='2','reject with optional empty note');
  perform pg_temp.expect((select decision_reason='' from public.wm_generation_reviews
    where id='33333333-3333-4333-8333-333333333333'),'rejection original note preserved');
  perform pg_temp.expect((select count(*)=2 from public.wm_job_decisions),'reject creates no job audit');

  begin
    perform public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333334',a,
      '55555555-5555-4555-8555-555555555554',2,repeat('d',64),'accept',null);
    raise exception 'Expected null reason rejection';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333334',a,
      '55555555-5555-4555-8555-555555555554',2,repeat('d',64),'accept',repeat('x',4001));
    raise exception 'Expected overlength reason rejection';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.wm_generation_decide(s,'33333333-3333-4333-8333-333333333334',
      '99999999-9999-4999-8999-999999999999',
      '55555555-5555-4555-8555-555555555554',2,repeat('d',64),'accept','');
    raise exception 'Expected owner ACL rejection';
  exception when insufficient_privilege then null; end;
  perform pg_temp.expect((select state='pending' from public.wm_generation_reviews
    where id='33333333-3333-4333-8333-333333333334'),'invalid decisions leave review pending');
  perform pg_temp.expect((select count(*)=11 from public.wm_journal where kind='human'),'human preservation after both accepts');
end; $$;
