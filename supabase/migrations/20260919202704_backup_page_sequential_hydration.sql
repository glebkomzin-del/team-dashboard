-- Hydrate large immutable references one at a time.  The previous materialized
-- CTE hydrated 32 candidates before applying the page budget, repeatedly
-- loading bodies that the page could not return.
create or replace function public.wm_backup_page(
 p_space_id uuid,p_snapshot_id uuid,p_after bigint
)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare
 candidate record;
 hydrated text;
 item jsonb;
 page jsonb:='[]'::jsonb;
 prospective jsonb;
 count integer:=0;
 wire_bytes bigint;
begin
 if p_after is null or p_after<0 or not exists(
  select 1 from public.wm_backup_snapshots
  where id=p_snapshot_id and space_id=p_space_id
 ) then
  raise exception 'Snapshot unavailable' using errcode='22023';
 end if;

 for candidate in
  select sequence,kind,record_json
  from public.wm_backup_records
  where snapshot_id=p_snapshot_id and sequence>p_after
  order by sequence
  limit 32
 loop
  hydrated:=case
   when candidate.kind='search_document'
    and candidate.record_json::jsonb ? '__search_document_ref' then
    (select (to_jsonb(d)-'fts')::text
     from public.wm_search_documents d
     where d.space_id=p_space_id
       and d.id=candidate.record_json::jsonb->>'__search_document_ref')
   when candidate.kind='search_result'
    and candidate.record_json::jsonb ? '__search_result_ref' then
    (select to_jsonb(r)::text
     from public.wm_search_results r
     where r.space_id=p_space_id
       and r.snapshot_id=candidate.record_json::jsonb->>'snapshot_id'
       and r.query_hash=candidate.record_json::jsonb->>'__search_result_ref')
   when candidate.kind='search_snapshot'
    and candidate.record_json::jsonb ? '__search_snapshot_ref' then
    (select to_jsonb(ss)::text
     from public.wm_search_snapshots ss
     where ss.space_id=p_space_id
       and ss.id=candidate.record_json::jsonb->>'__search_snapshot_ref')
   when candidate.kind='call'
    and candidate.record_json::jsonb->>'__completed_call_ref'='v1' then
    public.wm_backup_completed_call_hydrate(p_space_id,candidate.record_json::jsonb)
   else candidate.record_json
  end;
  if hydrated is null then
   raise exception 'Pinned backup record is unavailable or changed' using errcode='22023';
  end if;

  item:=jsonb_build_object(
   'sequence',candidate.sequence,
   'kind',candidate.kind,
   'record_json',hydrated,
   'record_hash',encode(extensions.digest(convert_to(hydrated,'UTF8'),'sha256'),'hex')
  );
  prospective:=page||jsonb_build_array(item);
  -- Measure the serialized JSON envelope, including escaped record_json.
  wire_bytes:=octet_length(prospective::text);
  if octet_length(jsonb_build_array(item)::text)>3500000 then
   raise exception 'Backup record exceeds transport limit' using errcode='22023';
  end if;
  if count>0 and wire_bytes>=1000000 then
   exit;
  end if;
  page:=prospective;
  count:=count+1;
  -- A first record may exceed the preferred page budget, but remains bounded
  -- by the hard transport limit above and is returned alone.
  if wire_bytes>=1000000 then
   exit;
  end if;
 end loop;
 return page;
end $$;
