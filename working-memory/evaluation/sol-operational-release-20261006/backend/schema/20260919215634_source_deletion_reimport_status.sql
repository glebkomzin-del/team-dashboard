-- A verified deletion is no longer the current UI state after an explicitly
-- authorized new source version has actually been imported. Historical ledger
-- rows remain immutable and visible for restore enforcement.
create or replace function public.wm_source_deletion_ledger(p_space_id uuid,p_actor_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if not exists(select 1 from public.wm_spaces where id=p_space_id and owner_id=p_actor_id) then
  raise exception 'Owner required' using errcode='42501'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('deletion_id',d.id,'source_id',d.source_id,'state',d.state,
   'ledger_revision',d.ledger_revision,'requested_at',d.requested_at,'completed_at',d.completed_at,
   'superseded_by_reimport',d.state='verified' and exists(
     select 1 from public.wm_source_reimport_authorizations a
     where a.space_id=d.space_id and a.source_id=d.source_id and a.ledger_revision>d.ledger_revision)
    and (exists(select 1 from public.wm_source_versions v where v.space_id=d.space_id and v.source_id=d.source_id and v.redaction_id is null)
      or exists(select 1 from public.wm_archive_documents x where x.space_id=d.space_id and x.source_id=d.source_id and x.redaction_id is null)))
   order by d.requested_at,d.id),'[]'::jsonb) into result
 from public.wm_source_deletions d where d.space_id=p_space_id;
 return result;
end; $$;

revoke all on function public.wm_source_deletion_ledger(uuid,uuid) from public,anon,authenticated;
grant execute on function public.wm_source_deletion_ledger(uuid,uuid) to service_role;
