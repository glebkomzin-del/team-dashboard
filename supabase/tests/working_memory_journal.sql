-- Synthetic, rollback-only checks. Run against an isolated Postgres/Supabase DB.
begin;
insert into auth.users(id) values('00000000-0000-4000-8000-000000000001'),('00000000-0000-4000-8000-000000000002');
insert into public.wm_spaces(id,owner_id,label) values('10000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','Synthetic verification');
set local role service_role;
do $$
declare
  source jsonb; result jsonb; body_hash text; sid text;
  space uuid:='10000000-0000-4000-8000-000000000001';
  cmd uuid:='20000000-0000-4000-8000-000000000001';
begin
  body_hash:=encode(extensions.digest('Synthetic original','sha256'),'hex');
  sid:=encode(extensions.digest('drive:synthetic:'||body_hash,'sha256'),'hex');
  source:=jsonb_build_object('id',sid,'source_id','drive:synthetic','content_hash',body_hash,
    'event_date','2026-09-07','title','Synthetic only','transcript','Synthetic original','observed_at','2026-09-07T10:00:00Z');
  result:=public.wm_append(space,0,cmd,'source','{"observations": []}',source);
  if result!='{"revision":1,"repeated":false}'::jsonb then raise exception 'Bad append';end if;
  -- A retry with the original expected revision returns the same receipt.
  result:=public.wm_append(space,0,cmd,'source','{"observations": []}',source);
  if result!='{"revision":1,"repeated":true}'::jsonb then raise exception 'Bad retry';end if;
  begin
    perform public.wm_append(space,0,cmd,'source','{"observations": ["tampered"]}',source);
    raise exception 'Changed retry accepted';
  exception when unique_violation then null;end;
  begin
    perform public.wm_append(space,0,'20000000-0000-4000-8000-000000000002','human',
      '{"action":"done","target_id":"synthetic","reason":"test"}',null,'00000000-0000-4000-8000-000000000001');
    raise exception 'Stale revision accepted';
  exception when serialization_failure then null;end;
  begin
    perform public.wm_append(space,1,'20000000-0000-4000-8000-000000000002','human',
      '{"action":"done","target_id":"synthetic","reason":"test"}',null,'00000000-0000-4000-8000-000000000002');
    raise exception 'Wrong actor accepted';
  exception when insufficient_privilege then null;end;
  begin
    perform public.wm_append(space,1,'20000000-0000-4000-8000-000000000002','source','{}',
      source||'{"transcript":"tampered"}');
    raise exception 'Bad checksum accepted';
  exception when invalid_parameter_value then null;end;
  begin
    perform public.wm_append(space,1,'20000000-0000-4000-8000-000000000002','source','{}',source);
    raise exception 'Repeated source accepted';
  exception when unique_violation then null;end;
  source:=source||jsonb_build_object('source_id','drive:earlier','event_date','2026-09-06',
    'id',encode(extensions.digest('drive:earlier:'||body_hash,'sha256'),'hex'));
  begin
    perform public.wm_append(space,1,'20000000-0000-4000-8000-000000000002','source','{}',source);
    raise exception 'Out of order accepted';
  exception when invalid_parameter_value then null;end;
  perform public.wm_append(space,1,'20000000-0000-4000-8000-000000000002','human',
    '{"action":"done","target_id":"synthetic","reason":"test"}',null,'00000000-0000-4000-8000-000000000001');
  if (select count(*) from public.wm_journal)!=2 or (select revision from public.wm_spaces where id=space)!=2
     or (select count(*) from public.wm_source_versions)!=1 then raise exception 'Non atomic write';end if;
end $$;
reset role;
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000001',true);
do $$ begin
  if (select count(*) from public.wm_journal)!=2 or (select count(*) from public.wm_source_versions)!=1 then raise exception 'Owner read failed';end if;
  begin
    delete from public.wm_journal;
    raise exception 'Browser erased history';
  exception when insufficient_privilege then null;end;
  begin
    perform public.wm_append('10000000-0000-4000-8000-000000000001',2,'20000000-0000-4000-8000-000000000003','human','{}');
    raise exception 'Browser invoked server RPC';
  exception when insufficient_privilege then null;end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000002',true);
do $$ begin
  if (select count(*) from public.wm_spaces)!=0 or (select count(*) from public.wm_journal)!=0 or (select count(*) from public.wm_source_versions)!=0 then raise exception 'Cross account leak';end if;
end $$;
reset role;
set local role anon;
do $$ begin
  begin
    perform 1 from public.wm_journal;
    raise exception 'Anonymous access';
  exception when insufficient_privilege then null;end;
end $$;
reset role;
rollback;
