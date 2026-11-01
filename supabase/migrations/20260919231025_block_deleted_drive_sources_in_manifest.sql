-- A deleted Drive source remains a durable intake tombstone.  The source row
-- keeps non-plaintext Drive metadata so polling can suppress the same Drive ID
-- without reading or submitting it again.  A later, explicitly authorized
-- version becomes eligible only after it has been imported successfully and is
-- therefore the newest unredacted archive row; the pre-read manifest never
-- guesses that an authorization matches an unseen body hash.
create or replace function public.wm_drive_manifest(p_space_id uuid)
returns jsonb language sql stable security invoker set search_path='' as $$
 with latest as (
  select distinct on (source_id) d.* from public.wm_archive_documents d
  where d.space_id=p_space_id order by source_id,registered_revision desc
 )
 select coalesce(jsonb_agg(jsonb_build_object('document_id',d.id,'source_id',d.source_id,
   'event_date',d.event_date,'drive_metadata',d.metadata_json::jsonb->'drive_metadata',
   'intake_blocked',d.redaction_id is not null) order by d.source_id),'[]'::jsonb)
 from latest d left join public.wm_processing_config c on c.space_id=d.space_id
 where d.redaction_id is not null
   or c.automatic_from is null or d.event_date<c.automatic_from
   or exists(select 1 from public.wm_jobs j where j.space_id=p_space_id and j.id=encode(extensions.digest(convert_to(d.source_id||':'||d.body_hash,'UTF8'),'sha256'),'hex'))
   or exists(select 1 from public.wm_source_versions s where s.space_id=p_space_id and s.id=encode(extensions.digest(convert_to(d.source_id||':'||d.body_hash,'UTF8'),'sha256'),'hex'));
$$;

revoke all on function public.wm_drive_manifest(uuid) from public,anon,authenticated;
grant execute on function public.wm_drive_manifest(uuid) to service_role;
