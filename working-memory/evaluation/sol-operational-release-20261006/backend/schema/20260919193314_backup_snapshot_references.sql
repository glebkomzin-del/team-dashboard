-- Search snapshots are content-addressed and immutable through the application
-- API. Pin their identities in the short snapshot transaction; hydrate their
-- large document lists only in bounded export pages, like search documents.
-- Mutable jobs/calls/questions remain copied at the snapshot boundary.
do $$ declare definition text; begin
 select pg_get_functiondef(oid) into definition from pg_proc
 where pronamespace='public'::regnamespace and proname='wm_backup_begin';
 if position('to_jsonb(ss)::text from public.wm_search_snapshots ss' in definition)=0 then
  raise exception 'Unexpected backup function: search snapshot branch missing';
 end if;
 execute replace(definition,
  'to_jsonb(ss)::text from public.wm_search_snapshots ss',
  'jsonb_build_object(''space_id'',ss.space_id,''__search_snapshot_ref'',ss.id)::text from public.wm_search_snapshots ss');
 select pg_get_functiondef(oid) into definition from pg_proc
 where pronamespace='public'::regnamespace and proname='wm_backup_page';
 if position('else record_json end' in definition)=0 then
  raise exception 'Unexpected backup page hydration';
 end if;
 execute replace(definition,'else record_json end',
  'when kind=''search_snapshot'' and record_json::jsonb ? ''__search_snapshot_ref'' then
   (select to_jsonb(ss)::text from public.wm_search_snapshots ss
    where ss.space_id=p_space_id and ss.id=record_json::jsonb->>''__search_snapshot_ref'')
   else record_json end');
end $$;
