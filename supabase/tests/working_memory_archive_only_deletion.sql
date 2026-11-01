-- Synthetic, rollback-only archive-only deletion contract. No model call.
begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
insert into auth.users(id) values ('d1111111-1111-4111-8111-111111111111');
insert into public.wm_spaces(id,owner_id,label,revision) values ('d2222222-2222-4222-8222-222222222222','d1111111-1111-4111-8111-111111111111','Archive-only deletion',1);
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
 values('d2222222-2222-4222-8222-222222222222',true,'2026-01-01','fixture',1);
set local role service_role;
do $$
declare s uuid:='d2222222-2222-4222-8222-222222222222'; owner uuid:='d1111111-1111-4111-8111-111111111111';
 deletion uuid:='d3333333-3333-4333-8333-333333333333'; src text:='drive:archive-only'; body text:='ARCHIVE ONLY ORIGINAL CANARY';
 body_hash text; doc text:=repeat('a',64); job text:=repeat('b',64); note text:=repeat('c',64); result jsonb; inputs jsonb; c record; replacement jsonb; snapshot jsonb;
 generated_body text:='GENERATION ACCEPTED ORIGINAL CANARY'; generated_hash text; generated_id text; generated_source text:='drive:generation-only'; generated jsonb;
begin
 body_hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 insert into public.wm_archive_documents(space_id,id,source_id,event_date,observed_at,title,body_hash,export_hash,body,export,metadata_json,registered_revision)
 values(s,doc,src,'2026-09-20','2026-09-20T10:00:00Z','Deleted title remains',body_hash,body_hash,body,body,'{}',1);
 insert into public.wm_archive_notes(space_id,id,document_id,origin,origin_id,note_json,note_hash,registered_revision)
 values(s,note,doc,'legacy_meetings','legacy-note','{"ai_summary":"independent retained summary"}',encode(extensions.digest(convert_to('{"ai_summary":"independent retained summary"}','UTF8'),'sha256'),'hex'),1);
 insert into public.wm_jobs(space_id,id,document_id,source_id,event_date,pipeline,state,prepared_payload)
 values(s,job,doc,src,'2026-09-20','fixture','review',jsonb_build_object('result','independent retained','context',body));
 inputs:=public.wm_source_deletion_inputs(s,src,owner);
 perform pg_temp.expect(jsonb_array_length(inputs)=1 and inputs->0->>'kind'='archive_only' and inputs->0->'source'->>'transcript'=body,'archive-only body is supplied without an accepted source');
 generated_hash:=encode(extensions.digest(convert_to(generated_body,'UTF8'),'sha256'),'hex');
 generated_id:=encode(extensions.digest(convert_to(generated_source||':'||generated_hash,'UTF8'),'sha256'),'hex');
 generated:=jsonb_build_object('id',generated_id,'source_id',generated_source,'content_hash',generated_hash,
  'event_date','2026-09-20','title','Generated original','transcript',generated_body,'observed_at','2026-09-20T11:00:00Z');
 insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
 values(s,generated_id,generated_source,generated_hash,'2026-09-20','Generated original',generated_body,'2026-09-20T11:00:00Z');
 insert into public.wm_journal(space_id,revision,command_id,request_hash,kind,actor_id,payload)
 values(s,1,'d6666666-6666-4666-8666-666666666666',repeat('d',64),'generation',owner,
  jsonb_build_object('entries',jsonb_build_array(jsonb_build_object('new',jsonb_build_object('kind','source','source',generated,
   'payload',jsonb_build_object('pipeline','accepted-generation'))))));
 inputs:=public.wm_source_deletion_inputs(s,generated_source,owner);
 perform pg_temp.expect(jsonb_array_length(inputs)=1 and inputs->0->>'kind'='source' and inputs->0->'payload'->>'pipeline'='accepted-generation','generation-accepted source keeps its immutable payload reference');
 result:=public.wm_source_deletion_stage(s,deletion,owner,src,'[]'::jsonb);
 perform pg_temp.expect(result->>'state'='prepared' and result->>'processed_versions'='0' and result->>'active_backup_snapshots'='0','archive-only source stages without a fabricated package and retains snapshot status');
 perform pg_temp.expect(public.wm_source_deletion_stage(s,deletion,owner,src,'[]'::jsonb)->>'active_backup_snapshots'='0','stage retry retains snapshot status');
 perform pg_temp.expect((select state='archived' and redaction_id is null and prepared_payload=jsonb_build_object('result','independent retained','context',body) from public.wm_jobs where space_id=s and id=job),'review source is fenced while its receipt remains available for sanitization');
 perform pg_temp.expect(public.wm_claim_job(s,'fixture','d4444444-4444-4444-8444-444444444444')->>'state'='idle','fenced source can never be claimed');
 perform pg_temp.expect(public.wm_enqueue(s,doc,'fixture')->>'reason'='source_deletion_in_progress','stage fences a later enqueue before it can create work');
 begin
  perform public.wm_source_deletion_stage(s,'d5555555-5555-4555-8555-555555555555',owner,'drive:no-original','[]'::jsonb);
  raise exception 'missing archive original staged';
 exception when invalid_parameter_value then null; end;
 for c in select * from public.wm_source_deletion_candidate_rows(s) loop
  replacement:=c.data;
  if c.scope='prepared_job' and c.record_key=job then replacement:=jsonb_build_object('prepared_payload',jsonb_build_object('result','independent retained','context','[Originalpassage entfernt]')); end if;
  perform public.wm_source_deletion_plan_put(s,deletion,owner,c.scope,c.record_key,
   encode(extensions.digest(convert_to(c.data::text,'UTF8'),'sha256'),'hex'),replacement,
   jsonb_build_object('changed',replacement is distinct from c.data,'removed_characters',0));
 end loop;
 snapshot:=jsonb_build_object('format','wm-projection-snapshot-v1','snapshot_sha256',repeat('1',64),'rows_sha256',repeat('2',64),
  'state_sha256',repeat('3',64),'logical_basis_sha256',repeat('4',64),'through_revision',1,'tables','{}'::jsonb,
  'logical_basis','[]'::jsonb,'deletions',jsonb_build_array(jsonb_build_object('deletion_id',deletion,'source_id',src)));
 result:=public.wm_source_deletion_purge(s,deletion,owner,'d7777777-7777-4777-8777-777777777777',snapshot);
 perform pg_temp.expect(result->>'state'='purging','archive-only source purges without a fabricated accepted source');
 perform pg_temp.expect(public.wm_enqueue(s,doc,'fixture')->>'reason'='source_deleted','redacted document cannot be enqueued from its retained hash');
 perform pg_temp.expect((select redaction_id=deletion and note_json='{"ai_summary":"independent retained summary"}' and sanitized_note_hash=encode(extensions.digest(convert_to(note_json,'UTF8'),'sha256'),'hex') from public.wm_archive_notes where space_id=s and id=note),'note follows deleted parent without losing retained summary');
 perform pg_temp.expect((select title='Deleted title remains' and metadata_json='{}' from public.wm_archive_documents where space_id=s and id=doc),'deleted document keeps title and metadata only');
 perform pg_temp.expect((select redaction_id=deletion and prepared_payload->>'result'='independent retained' and position(body in prepared_payload::text)=0 from public.wm_jobs where space_id=s and id=job),'paid review receipt is sanitized only during purge while its independent result remains');
 perform public.wm_source_deletion_check(s,deletion,owner,'local_caches',jsonb_build_object('rebuilt',true,'canary_scan_clear',true));
 perform public.wm_source_deletion_check(s,deletion,owner,'backup_sets',jsonb_build_object('restore_ledger_persisted',true,'retention_policy','14-latest-plus-8-observed-weeks','minimum_deletion_revision',2));
 result:=public.wm_source_deletion_finalize(s,deletion,owner);
 perform pg_temp.expect(result->>'state'='verified','archive-only source finalizes after its required checks');
end $$;
reset role;
rollback;
