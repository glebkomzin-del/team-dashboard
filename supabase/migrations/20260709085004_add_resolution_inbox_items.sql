alter table public.inbox_items
  drop constraint if exists inbox_items_entity_type_check;

alter table public.inbox_items
  add constraint inbox_items_entity_type_check
  check (entity_type in ('todo','blocker','open_item','meeting','decision','resolution'));

create index if not exists inbox_items_resolution_idempotency_idx
  on public.inbox_items ((payload ->> 'target_id'), (payload ->> 'evidence_meeting_id'))
  where entity_type = 'resolution';
