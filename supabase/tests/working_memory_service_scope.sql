begin;
insert into auth.users(id) values('00000000-0000-4000-8000-000000000001');
insert into public.wm_spaces(id,owner_id,label) values('10000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','Synthetic scope test');
insert into memory_private.service_tokens(token_hash,space_id,label) values(repeat('a',64),'10000000-0000-4000-8000-000000000001','Synthetic token');
set local role service_role;
do $$ begin
 if (select count(*) from public.wm_service_scope(repeat('a',64)))!=1 then raise exception 'Scope missing';end if;
 if (select count(*) from public.wm_service_scope(repeat('b',64)))!=0 then raise exception 'Unknown token accepted';end if;
 begin
  update memory_private.service_tokens set enabled=true;
  raise exception 'Server can edit its grants';
 exception when insufficient_privilege then null;end;
end $$;
reset role;
update memory_private.service_tokens set enabled=false where token_hash=repeat('a',64);
set local role service_role;
do $$ begin
 if (select count(*) from public.wm_service_scope(repeat('a',64)))!=0 then raise exception 'Revocation ignored';end if;
end $$;
reset role;
set local role authenticated;
do $$ begin
 begin
  perform 1 from memory_private.service_tokens;
  raise exception 'Browser read token scopes';
 exception when insufficient_privilege then null;end;
 begin
  perform 1 from public.wm_service_scope(repeat('a',64));
  raise exception 'Browser called scope lookup';
 exception when insufficient_privilege then null;end;
end $$;
reset role;
rollback;
