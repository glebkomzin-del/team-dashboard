begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
insert into auth.users(id) values('55555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label) values
 ('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Synthetic backup references');
set local role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; snap uuid:=gen_random_uuid();
 search_id text:=encode(extensions.digest('','sha256'),'hex'); expected text; rows jsonb; row jsonb;
begin
 perform public.wm_search_snapshot(s,search_id,'{}'::text[]);
 select to_jsonb(ss)::text into expected from public.wm_search_snapshots ss where space_id=s and id=search_id;
 perform public.wm_backup_begin(s,snap);
 perform pg_temp.expect((select (record_json::jsonb->>'__search_snapshot_ref')=search_id
  from public.wm_backup_records where snapshot_id=snap and kind='search_snapshot'),'snapshot stores compact identity');
 rows:=public.wm_backup_page(s,snap,0);
 perform pg_temp.expect(jsonb_array_length(rows)=1,'exact snapshot membership');
 row:=rows->0;
 perform pg_temp.expect(row->>'record_json'=expected,'hydration preserves complete original snapshot');
 perform pg_temp.expect(row->>'record_hash'=encode(extensions.digest(expected,'sha256'),'hex'),'hydration checksum covers full record');
 perform pg_temp.expect(public.wm_backup_page(s,snap,(row->>'sequence')::bigint)='[]'::jsonb,'cursor terminates');
 perform public.wm_backup_release(s,snap);
 perform pg_temp.expect((select count(*)=1 from public.wm_search_snapshots where space_id=s),'backup release preserves search data');
end $$;
reset role;
rollback;
