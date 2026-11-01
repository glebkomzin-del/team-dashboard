-- Search content is immutable. Pin identities atomically and hydrate each bounded
-- export page, avoiding copying hundreds of MB inside the snapshot transaction.
do $$ declare definition text; begin
 select pg_get_functiondef(oid) into definition from pg_proc where pronamespace='public'::regnamespace and proname='wm_backup_begin';
 execute replace(replace(definition,
 '(to_jsonb(d)-''fts'')::text from public.wm_search_documents d',
 'jsonb_build_object(''space_id'',d.space_id,''__search_document_ref'',d.id)::text from public.wm_search_documents d'),
 'to_jsonb(r)::text from public.wm_search_results r',
 'jsonb_build_object(''space_id'',r.space_id,''__search_result_ref'',r.query_hash,''snapshot_id'',r.snapshot_id)::text from public.wm_search_results r');
end $$;
create or replace function public.wm_backup_page(p_space_id uuid,p_snapshot_id uuid,p_after bigint)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if p_after is null or p_after<0 or not exists(select 1 from public.wm_backup_snapshots where id=p_snapshot_id and space_id=p_space_id) then
  raise exception 'Snapshot unavailable' using errcode='22023'; end if;
 return coalesce((with candidates as materialized (select sequence,kind,record_json from public.wm_backup_records where snapshot_id=p_snapshot_id and sequence>p_after order by sequence limit 32),
 hydrated as materialized (select sequence,kind,case
 when kind='search_document' and record_json::jsonb ? '__search_document_ref' then
  (select (to_jsonb(d)-'fts')::text from public.wm_search_documents d where d.space_id=p_space_id and d.id=record_json::jsonb->>'__search_document_ref')
 when kind='search_result' and record_json::jsonb ? '__search_result_ref' then
  (select to_jsonb(r)::text from public.wm_search_results r where r.space_id=p_space_id and r.snapshot_id=record_json::jsonb->>'snapshot_id' and r.query_hash=record_json::jsonb->>'__search_result_ref')
 else record_json end record_json from candidates),
 sized as(select *,row_number() over(order by sequence) n,sum(octet_length(record_json)) over(order by sequence) bytes from hydrated)
 select jsonb_agg(jsonb_build_object('sequence',sequence,'kind',kind,'record_json',record_json,'record_hash',encode(extensions.digest(record_json,'sha256'),'hex')) order by sequence) from sized where n=1 or bytes<1000000),'[]'::jsonb);
end $$;
