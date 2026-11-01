create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;

do $$
begin
  begin
    perform public.wm_generation_decide(
      '22222222-2222-4222-8222-222222222222',
      '33333333-3333-4333-8333-333333333331',
      '11111111-1111-4111-8111-111111111111',
      '55555555-5555-4555-8555-555555555551',0,repeat('a',64),'accept','');
    raise exception 'Expected old audit reason constraint failure';
  exception when check_violation then
    if sqlerrm not like '%wm_job_decisions_reason_check%' then raise; end if;
  end;
  perform pg_temp.expect((select revision=0 from public.wm_spaces where id='22222222-2222-4222-8222-222222222222'),'old failure rolled back revision');
  perform pg_temp.expect((select state='pending' from public.wm_generation_reviews where id='33333333-3333-4333-8333-333333333331'),'old failure left review pending');
  perform pg_temp.expect((select state='review' from public.wm_jobs where id='job-empty'),'old failure left job unchanged');
  perform pg_temp.expect((select count(*)=0 from public.wm_job_decisions),'old failure wrote no decision');
  perform pg_temp.expect((select count(*)=11 from public.wm_journal where kind='human'),'old failure preserved humans');
end; $$;
