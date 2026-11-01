begin;
create function pg_temp.expect(ok boolean, label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid, source text, day date, body text) returns text language plpgsql as $$
declare m text; h text; identifier text; result jsonb;
begin
 h:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 m:=jsonb_build_object('source_id',source,'event_date',day,'title','Synthetic queue check',
   'body_sha256',h,'export_sha256',h,'body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to(source||':'||m,'UTF8'),'sha256'),'hex');
 result:=public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source,'event_date',day::text,
   'observed_at','2026-09-07T12:00:00Z','title','Synthetic queue check','body_hash',h,'export_hash',h,
   'body',body,'export',body,'metadata_json',m));
 return identifier;
end; $$;
insert into auth.users(id) values('55555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Synthetic queue');
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666667','55555555-5555-4555-8555-555555555555','Synthetic concurrent decision');
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666668','55555555-5555-4555-8555-555555555555','Synthetic deletion intake block');
insert into public.wm_processing_config(space_id) values('66666666-6666-4666-8666-666666666666');
insert into public.wm_processing_config(space_id) values('66666666-6666-4666-8666-666666666667');
insert into public.wm_processing_config(space_id) values('66666666-6666-4666-8666-666666666668');
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; old text; fresh text; changed text; response jsonb;
begin
 old:=pg_temp.doc(s,'synthetic:old','2026-06-01','Historical original.');
 fresh:=pg_temp.doc(s,'synthetic:future','2026-09-07','First future version.');
 perform pg_temp.expect(jsonb_array_length(public.wm_drive_manifest(s))=2,'disabled unconfigured sources remain archive-only');
 update public.wm_processing_config set automatic_from='2026-09-07',pipeline='test-v1' where space_id=s;
 response:=public.wm_drive_manifest(s);
 perform pg_temp.expect(jsonb_array_length(response)=1 and response->0->>'document_id'=old,'future archive without queue registration must be read again');
 perform public.wm_enqueue(s,fresh,'test-v1');
 perform pg_temp.expect(jsonb_array_length(public.wm_drive_manifest(s))=2,'queue receipt makes original safe to skip');
 changed:=pg_temp.doc(s,'synthetic:future','2026-09-07','Changed future version.');
 perform pg_temp.expect(jsonb_array_length(public.wm_drive_manifest(s))=1,'latest changed version cannot fall back to older receipt');
 perform public.wm_enqueue(s,changed,'test-v1');
 response:=public.wm_drive_manifest(s);
 perform pg_temp.expect(jsonb_array_length(response)=2,'held changed-source job preserves receipt');
 perform pg_temp.expect(exists(select 1 from jsonb_array_elements(response) x where x->>'document_id'=changed),'latest exact metadata version selected');
 perform pg_temp.expect(not exists(select 1 from jsonb_array_elements(response) x where x->>'document_id'=fresh),'older version not advertised');
 perform pg_temp.expect(not exists(select 1 from public.wm_model_calls where space_id=s),'inventory and enqueue make zero model calls');
end; $$;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666668'; archive_only text; queued text; response jsonb;
begin
 archive_only:=pg_temp.doc(s,'drive:deleted-archive-only','2026-09-08','Deleted archive-only original.');
 update public.wm_processing_config set automatic_from='2026-09-08',pipeline='test-v1' where space_id=s;
 perform pg_temp.expect(jsonb_array_length(public.wm_drive_manifest(s))=0,
   'unregistered future archive is normally retried');
 update public.wm_archive_documents set body=null,export=null,redaction_id='69999999-9999-4999-8999-999999999999'
  where space_id=s and id=archive_only;
 response:=public.wm_drive_manifest(s);
 perform pg_temp.expect(jsonb_array_length(response)=1 and (response->0->>'intake_blocked')::boolean,
   'deleted archive-only source remains an intake tombstone after policy activation');
 queued:=pg_temp.doc(s,'drive:deleted-queued','2026-09-09','Deleted queued original.');
 perform public.wm_enqueue(s,queued,'test-v1');
 update public.wm_archive_documents set body=null,export=null,redaction_id='69999999-9999-4999-8999-999999999998'
  where space_id=s and id=queued;
 response:=public.wm_drive_manifest(s);
 perform pg_temp.expect(jsonb_array_length(response)=2 and not exists(
   select 1 from jsonb_array_elements(response) item where item->>'intake_blocked'!='true'),
   'deleted queued and archive-only sources both stay blocked in the manifest');
end; $$;
set local role authenticated;
do $$ begin
 begin
  perform public.wm_drive_manifest('66666666-6666-4666-8666-666666666666');
  raise exception 'FAILED: browser called private manifest';
 exception when insufficient_privilege then null; end;
end; $$;
reset role;
rollback;
