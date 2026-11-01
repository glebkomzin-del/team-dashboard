do $$ declare definition text; begin
 select pg_get_functiondef(oid) into definition from pg_proc where pronamespace='public'::regnamespace and proname='wm_backup_begin';
 if definition not like '%to_jsonb(s)::text from public.wm_search_snapshots s%' then raise exception 'Unexpected backup function'; end if;
 execute replace(definition,'to_jsonb(s)::text from public.wm_search_snapshots s where s.space_id=p_space_id','to_jsonb(ss)::text from public.wm_search_snapshots ss where ss.space_id=p_space_id');
end $$;
