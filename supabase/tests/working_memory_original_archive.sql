-- Synthetic original/summary, no model calls; every row rolled back.
begin;
insert into auth.users(id) values ('00000000-0000-4000-8000-000000000001');
insert into public.wm_spaces(id,owner_id,label) values ('30000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','Archive test');
set local role service_role;
do $test$
declare
  target_space uuid:='30000000-0000-4000-8000-000000000001';
  doc jsonb:=$doc${"id": "00626ecacb1dd450e819da0fe6d80bd65211f5f93da9499ca00f0d4df65ae5a6", "source_id": "drive:archive-fixture", "event_date": "2026-06-02", "observed_at": "2026-09-06T20:00:00Z", "title": "Archivprüfung", "body_hash": "c40ee1d17f91d3c757641db5faa98739281168347a751f77530a15f97c87cc28", "export_hash": "e56864929e7a48b9a14ca9785354c96b155c2265a51c6429ee63cc0206b0c2dd", "body": "00:01 Gleb: Zusammenfassung bleibt erhalten. ÄÖÜ 👋\n", "export": "Meeting\n00:01 Gleb: Zusammenfassung bleibt erhalten. ÄÖÜ 👋\n", "metadata_json": "{\"body_offset_characters\": 8, \"body_sha256\": \"c40ee1d17f91d3c757641db5faa98739281168347a751f77530a15f97c87cc28\", \"event_date\": \"2026-06-02\", \"export_sha256\": \"e56864929e7a48b9a14ca9785354c96b155c2265a51c6429ee63cc0206b0c2dd\", \"source_id\": \"drive:archive-fixture\", \"title\": \"Archivprüfung\"}"}$doc$::jsonb;
  note jsonb:=$note${"document_id": "00626ecacb1dd450e819da0fe6d80bd65211f5f93da9499ca00f0d4df65ae5a6", "origin": "legacy_meetings", "origin_id": "meeting-fixture", "note_json": "{\"ai_summary\": \"Vorhandene Zusammenfassung unverändert.\", \"executive_summary\": \"Kurzfassung\", \"key_decisions\": [\"Besprochene Entscheidung als Notiz erhalten.\"]}", "note_hash": "28b8701f387b46d1ca12c33b2882657484479a8ce0c852c8d713905dd8fd74ad", "id": "77124626f00653844c43566687844a94d4a411e79051e70e3a4d24f822bf8b26"}$note$::jsonb;
  receipt jsonb;
begin
  receipt:=public.wm_archive_put(target_space,doc);
  if receipt->>'archive_revision'!='1' or receipt->>'repeated'!='false' then raise exception 'First original not saved'; end if;
  receipt:=public.wm_archive_put(target_space,doc);
  if receipt->>'archive_revision'!='1' or receipt->>'repeated'!='true' then raise exception 'Original retry not idempotent'; end if;
  receipt:=public.wm_archive_note_put(target_space,note);
  if receipt->>'archive_revision'!='2' or receipt->>'repeated'!='false' then raise exception 'Summary not saved'; end if;
  receipt:=public.wm_archive_note_put(target_space,note);
  if receipt->>'archive_revision'!='2' or receipt->>'repeated'!='true' then raise exception 'Summary retry not idempotent'; end if;
  begin
    perform public.wm_archive_put(target_space,doc||jsonb_build_object('redaction_id',null));
    raise exception 'Internal document tombstone field accepted on active wire envelope';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.wm_archive_note_put(target_space,note||jsonb_build_object('redaction_id',null));
    raise exception 'Internal note tombstone field accepted on active wire envelope';
  exception when invalid_parameter_value then null; end;
  if exists(select 1 from public.wm_journal where wm_journal.space_id=target_space) then raise exception 'Archive accidentally created actions'; end if;
  if (select revision from public.wm_spaces where id=target_space)!=0 then raise exception 'Archive changed working state'; end if;
  begin
    perform public.wm_archive_put(target_space,jsonb_set(doc,'{body}','"changed"'));
    raise exception 'Tampered original accepted';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.wm_archive_put(target_space,jsonb_set(doc,'{observed_at}','"2026-09-07T20:00:00Z"'));
    raise exception 'Changed same identity accepted';
  exception when unique_violation then null; end;
  begin
    perform public.wm_archive_put(target_space,jsonb_set(doc,'{observed_at}','"2026-09-06T20:00:00"'));
    raise exception 'Naive observation time accepted';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.wm_archive_note_put(target_space,jsonb_set(note,'{note_json}','"{}"'));
    raise exception 'Tampered summary accepted';
  exception when invalid_parameter_value then null; end;
  if (select count(*) from public.wm_archive_documents where wm_archive_documents.space_id=target_space)!=1 then raise exception 'Original duplicated'; end if;
  if (select count(*) from public.wm_archive_notes where wm_archive_notes.space_id=target_space)!=1 then raise exception 'Summary duplicated'; end if;
  if has_table_privilege('service_role','public.wm_archive_documents','UPDATE') or has_table_privilege('service_role','public.wm_archive_notes','DELETE') then raise exception 'Mutable history privileges'; end if;
end;
$test$;
reset role;
update public.wm_archive_documents set body=null,export=null,redaction_id='90000000-0000-4000-8000-000000000001' where space_id='30000000-0000-4000-8000-000000000001';
update public.wm_archive_notes set redaction_id='90000000-0000-4000-8000-000000000001',sanitized_note_hash=encode(extensions.digest(convert_to(note_json,'UTF8'),'sha256'),'hex') where space_id='30000000-0000-4000-8000-000000000001';
set local role service_role;
do $test$
declare target_space uuid:='30000000-0000-4000-8000-000000000001';
 doc jsonb:=$doc${"id": "00626ecacb1dd450e819da0fe6d80bd65211f5f93da9499ca00f0d4df65ae5a6", "source_id": "drive:archive-fixture", "event_date": "2026-06-02", "observed_at": "2026-09-06T20:00:00Z", "title": "Archivprüfung", "body_hash": "c40ee1d17f91d3c757641db5faa98739281168347a751f77530a15f97c87cc28", "export_hash": "e56864929e7a48b9a14ca9785354c96b155c2265a51c6429ee63cc0206b0c2dd", "body": "00:01 Gleb: Zusammenfassung bleibt erhalten. ÄÖÜ 👋\n", "export": "Meeting\n00:01 Gleb: Zusammenfassung bleibt erhalten. ÄÖÜ 👋\n", "metadata_json": "{\"body_offset_characters\": 8, \"body_sha256\": \"c40ee1d17f91d3c757641db5faa98739281168347a751f77530a15f97c87cc28\", \"event_date\": \"2026-06-02\", \"export_sha256\": \"e56864929e7a48b9a14ca9785354c96b155c2265a51c6429ee63cc0206b0c2dd\", \"source_id\": \"drive:archive-fixture\", \"title\": \"Archivprüfung\"}"}$doc$::jsonb;
 note jsonb:=$note${"document_id": "00626ecacb1dd450e819da0fe6d80bd65211f5f93da9499ca00f0d4df65ae5a6", "origin": "legacy_meetings", "origin_id": "meeting-fixture", "note_json": "{\"ai_summary\": \"Vorhandene Zusammenfassung unverändert.\", \"executive_summary\": \"Kurzfassung\", \"key_decisions\": [\"Besprochene Entscheidung als Notiz erhalten.\"]}", "note_hash": "28b8701f387b46d1ca12c33b2882657484479a8ce0c852c8d713905dd8fd74ad", "id": "77124626f00653844c43566687844a94d4a411e79051e70e3a4d24f822bf8b26"}$note$::jsonb;
begin
 begin perform public.wm_archive_put(target_space,doc);raise exception 'Deleted original replay accepted';exception when unique_violation then null;end;
 begin perform public.wm_archive_note_put(target_space,note);raise exception 'Note attached to deleted original accepted';exception when foreign_key_violation then null;end;
end $test$;
reset role;
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000001',true);
do $test$ begin
  if (select count(*) from public.wm_archive_documents)!=1 or (select count(*) from public.wm_archive_notes)!=1 then raise exception 'Owner cannot read original and note'; end if;
  if has_function_privilege('authenticated','public.wm_archive_put(uuid,jsonb)','EXECUTE') or has_function_privilege('anon','public.wm_archive_note_put(uuid,jsonb)','EXECUTE') then raise exception 'Browser can write archive'; end if;
end; $test$;
select set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000002',true);
do $test$ begin
  if exists(select 1 from public.wm_archive_documents) or exists(select 1 from public.wm_archive_notes) then raise exception 'Other owner can read archive'; end if;
end; $test$;
rollback;
