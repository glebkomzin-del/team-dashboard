-- Synthetic, rollback-only checks for staging and source-id reimport blocking.
begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
insert into auth.users(id) values
 ('11111111-1111-4111-8111-111111111111'),
 ('22222222-2222-4222-8222-222222222222');
insert into public.wm_spaces(id,owner_id,label) values
 ('33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111','Original deletion check');

set local role service_role;
do $$
declare
 s uuid:='33333333-3333-4333-8333-333333333333';
 owner uuid:='11111111-1111-4111-8111-111111111111';
 deletion uuid:='44444444-4444-4444-8444-444444444444';
 src text:='drive:delete-fixture'; body text:='Synthetic private original';
 body_hash text; version_id text; package jsonb; result jsonb; changed_hash text;
begin
 body_hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 version_id:=encode(extensions.digest(convert_to(src||':'||body_hash,'UTF8'),'sha256'),'hex');
 insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
 values(s,version_id,src,body_hash,'2026-09-19','Synthetic original',body,'2026-09-19T10:00:00Z');
 package:=jsonb_build_object(
  'format','wm-redacted-source-v1','package_sha256',repeat('a',64),
  'source',jsonb_build_object('id',version_id,'source_id',src,'content_hash',body_hash,
    'event_date','2026-09-19','title','Synthetic original','observed_at','2026-09-19T10:00:00Z'),
  'evidence_manifest',jsonb_build_object('entries','[]'::jsonb));
 result:=public.wm_source_deletion_stage(s,deletion,owner,src,jsonb_build_array(package));
 perform pg_temp.expect(result->>'state'='prepared' and result->>'repeated'='false','stage creates ledger');
 result:=public.wm_source_deletion_status(s,deletion,owner);
 perform pg_temp.expect(result->>'source_id'=src and jsonb_array_length(result->'packages')=1
  and result->'checks'='{}'::jsonb,'restart status retains evidence-only package and check state');
 result:=public.wm_source_deletion_stage(s,deletion,owner,src,jsonb_build_array(package));
 perform pg_temp.expect(result->>'repeated'='true','stage retry is idempotent');
 perform pg_temp.expect((select required_scopes @> array['backup_sets','model_receipts','local_caches']
  from public.wm_source_deletions where space_id=s and id=deletion),'all purge scopes are durable');
 begin
  changed_hash:=encode(extensions.digest(convert_to('Changed private original','UTF8'),'sha256'),'hex');
  insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
  values(s,encode(extensions.digest(convert_to(src||':'||changed_hash,'UTF8'),'sha256'),'hex'),
   src,changed_hash,'2026-09-20','Changed original','Changed private original','2026-09-20T10:00:00Z');
  raise exception 'Source-id tombstone allowed changed content';
 exception when unique_violation then null; end;
 begin
  perform public.wm_source_reimport_authorize(s,'55555555-5555-4555-8555-555555555555',owner,
   src,changed_hash,'Owner requests a deliberate restore');
  raise exception 'Prepared deletion allowed reimport';
 exception when invalid_parameter_value then null; end;
 begin
  perform public.wm_source_deletion_stage(s,'66666666-6666-4666-8666-666666666666',
   '22222222-2222-4222-8222-222222222222',src,jsonb_build_array(package));
  raise exception 'Other actor staged deletion';
 exception when insufficient_privilege then null; end;
end $$;
reset role;

-- A future purge finalizer owns this transition. The test changes only synthetic
-- data to exercise the explicit post-verification reimport exception.
update public.wm_source_deletions set state='verified',completed_at=clock_timestamp()
 where id='44444444-4444-4444-8444-444444444444';
set local role service_role;
do $$
declare
 s uuid:='33333333-3333-4333-8333-333333333333';
 owner uuid:='11111111-1111-4111-8111-111111111111';
 src text:='drive:delete-fixture'; body text:='Explicit restored version';
 body_hash text; version_id text; result jsonb;
begin
 body_hash:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 version_id:=encode(extensions.digest(convert_to(src||':'||body_hash,'UTF8'),'sha256'),'hex');
 result:=public.wm_source_reimport_authorize(s,'55555555-5555-4555-8555-555555555555',owner,
  src,body_hash,'Owner requests a deliberate restore');
 perform pg_temp.expect(result->>'repeated'='false','verified source accepts explicit authorization');
 insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
 values(s,version_id,src,body_hash,'2026-09-20','Restored original',body,'2026-09-20T10:00:00Z');
 perform pg_temp.expect((select count(*)=2 from public.wm_source_versions v where v.space_id=s and v.source_id=src),
  'exact authorized hash can reimport');
 begin
  insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
  values(s,repeat('f',64),src,repeat('e',64),'2026-09-21','Unapproved original',
   'Unapproved body','2026-09-21T10:00:00Z');
  raise exception 'Authorization leaked to another hash';
 exception when unique_violation then null; end;
end $$;
reset role;

set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
select pg_temp.expect((select count(*)=1 from public.wm_source_deletions),'owner sees deletion ledger');
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
select pg_temp.expect((select count(*)=0 from public.wm_source_deletions),'other account cannot read deletion ledger');
do $$ begin
 begin
  insert into public.wm_source_reimport_authorizations(space_id,id,source_id,content_hash,actor_id,reason)
  values('33333333-3333-4333-8333-333333333333',gen_random_uuid(),'drive:delete-fixture',
   repeat('a',64),'22222222-2222-4222-8222-222222222222','forged');
  raise exception 'Browser inserted authorization';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
rollback;

-- Full purge remains rollback-only: summaries and independent chat content stay,
-- original canaries leave every active technical candidate, and a later
-- explicitly reimported version can enter a second deletion epoch.
begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
insert into auth.users(id) values ('71111111-1111-4111-8111-111111111111');
insert into public.wm_spaces(id,owner_id,label,revision,archive_revision) values
 ('73333333-3333-4333-8333-333333333333','71111111-1111-4111-8111-111111111111','Purge E2E',1,2);
-- The live edge uses service_role. Exercise stage, purge and finalize under
-- that role so SECURITY INVOKER table grants cannot be masked by postgres.
set local role service_role;
do $$
declare s uuid:='73333333-3333-4333-8333-333333333333'; owner uuid:='71111111-1111-4111-8111-111111111111';
 deletion uuid:='74444444-4444-4444-8444-444444444444'; src text:='drive:purge-e2e';
 prior_deletion uuid:='75555555-5555-4555-8555-555555555555'; prior_src text:='drive:previously-deleted';
 original text:='PRIVATE ORIGINAL CANARY sentence copied into context'; body_hash text; version_id text;
 doc_id text:=repeat('d',64); note_id text:=repeat('e',64); package jsonb; c record; replacement jsonb;
 snapshot jsonb; result jsonb; q uuid:='76666666-6666-4666-8666-666666666666'; new_body text; new_hash text; new_version text; second_package jsonb;
begin
 update public.wm_spaces set deletion_revision=1 where id=s;
 insert into public.wm_source_deletions(space_id,id,source_id,actor_id,request_hash,ledger_revision,state,
  archive_document_ids,original_content_hashes,required_scopes,completed_at)
 values(s,prior_deletion,prior_src,owner,repeat('0',64),1,'verified','{}','{}','{}',clock_timestamp());
 body_hash:=encode(extensions.digest(convert_to(original,'UTF8'),'sha256'),'hex');
 version_id:=encode(extensions.digest(convert_to(src||':'||body_hash,'UTF8'),'sha256'),'hex');
 insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
 values(s,version_id,src,body_hash,'2026-09-19','Private',original,'2026-09-19T10:00:00Z');
 insert into public.wm_journal(space_id,revision,command_id,request_hash,kind,source_version,payload)
 values(s,1,'70000000-0000-4000-8000-000000000001',repeat('a',64),'source',version_id,
  jsonb_build_object('format','wm-source-batch-v1','pipeline','fixture','model','fixture','proposal',jsonb_build_object('observations','[]'::jsonb,'coverage_notes','[]'::jsonb),'result_sha256',repeat('b',64)));
 insert into public.wm_archive_documents values(s,doc_id,src,'2026-09-19','2026-09-19T10:00:00Z','Private',body_hash,
  encode(extensions.digest(convert_to('header'||original,'UTF8'),'sha256'),'hex'),original,'header'||original,
  jsonb_build_object('source_id',src,'event_date','2026-09-19','title','Private','body_sha256',body_hash,
   'export_sha256',encode(extensions.digest(convert_to('header'||original,'UTF8'),'sha256'),'hex'),'body_offset_characters',6)::text,1);
 insert into public.wm_archive_notes values(s,note_id,doc_id,'source_summary','summary',
  jsonb_build_object('ai_summary','Derived summary remains','legacy_record',jsonb_build_object('raw_transcript',original))::text,
  repeat('c',64),2);
 insert into public.wm_questions(space_id,id,actor_id,revision,archive_revision,deletion_revision,request_json,request_hash,response_json,response_hash,completed_at)
 values(s,q,owner,1,2,1,jsonb_build_object('question','Keep this user question','context',original)::text,
  encode(extensions.digest(convert_to(jsonb_build_object('question','Keep this user question','context',original)::text,'UTF8'),'sha256'),'hex'),
  jsonb_build_object('answer','Independent answer remains','source_copy',original)::text,
  encode(extensions.digest(convert_to(jsonb_build_object('answer','Independent answer remains','source_copy',original)::text,'UTF8'),'sha256'),'hex'),clock_timestamp());
 package:=jsonb_build_object('format','wm-redacted-source-v1','package_sha256',repeat('f',64),
  'source',jsonb_build_object('id',version_id,'source_id',src,'content_hash',body_hash,'event_date','2026-09-19','title','Private','observed_at','2026-09-19T10:00:00Z'),
  'evidence_manifest',jsonb_build_object('entries','[]'::jsonb),
  'retained_payload',jsonb_build_object('format','wm-source-batch-v1','pipeline','fixture','model','fixture','proposal',jsonb_build_object('observations','[]'::jsonb,'coverage_notes','[]'::jsonb),'result_sha256',repeat('b',64)),
  'attestation',jsonb_build_object('accepted_payload_sha256',repeat('a',64),'accepted_result_sha256',repeat('b',64),'original_content_sha256',body_hash));
 perform public.wm_source_deletion_stage(s,deletion,owner,src,jsonb_build_array(package));
 for c in select * from public.wm_source_deletion_candidate_rows(s) loop
  replacement:=c.data;
  if c.scope='archive_note' then replacement:=jsonb_build_object('note_json',jsonb_build_object('ai_summary','Derived summary remains')::text); end if;
  if c.scope='question' then replacement:=jsonb_build_object('request_json',jsonb_build_object('question','Keep this user question','context','[Originalpassage entfernt]')::text,
    'response_json',jsonb_build_object('answer','Independent answer remains','source_copy','[Originalpassage entfernt]')::text); end if;
  perform public.wm_source_deletion_plan_put(s,deletion,owner,c.scope,c.record_key,
   encode(extensions.digest(convert_to(c.data::text,'UTF8'),'sha256'),'hex'),replacement,
   jsonb_build_object('changed',replacement is distinct from c.data,'removed_characters',case when replacement is distinct from c.data then length(original) else 0 end));
 end loop;
 snapshot:=jsonb_build_object('format','wm-projection-snapshot-v1','snapshot_sha256',repeat('1',64),'rows_sha256',repeat('2',64),'state_sha256',repeat('4',64),
  'logical_basis_sha256',repeat('3',64),'through_revision',1,'tables','{}'::jsonb,'logical_basis','[]'::jsonb,
  'deletions',jsonb_build_array(jsonb_build_object('deletion_id',deletion,'source_id',src)));
 begin
  perform public.wm_source_deletion_purge(s,deletion,owner,'78888888-8888-4888-8888-888888888888',snapshot);
  raise exception 'Incomplete cumulative deletion checkpoint accepted';
 exception when invalid_parameter_value then null; end;
 perform pg_temp.expect((select transcript=original and redaction_id is null from public.wm_source_versions where space_id=s and id=version_id),
  'incomplete cumulative checkpoint is rejected before mutation');
 snapshot:=jsonb_set(snapshot,'{deletions}',jsonb_build_array(
  jsonb_build_object('deletion_id',deletion,'source_id',src),
  jsonb_build_object('deletion_id',prior_deletion,'source_id',prior_src)));
 result:=public.wm_source_deletion_purge(s,deletion,owner,'78888888-8888-4888-8888-888888888888',snapshot);
 perform pg_temp.expect(result->>'state'='purging','hash-bound purge completed');
 perform pg_temp.expect((select transcript is null and redaction_id=deletion from public.wm_source_versions where space_id=s and id=version_id),'projection original removed');
 perform pg_temp.expect((select body is null and export is null and redaction_id=deletion from public.wm_archive_documents where space_id=s and id=doc_id),'archive original removed');
 perform pg_temp.expect((select note_json::jsonb->>'ai_summary'='Derived summary remains' and position(original in note_json)=0
   and sanitized_note_hash=encode(extensions.digest(convert_to(note_json,'UTF8'),'sha256'),'hex')
   from public.wm_archive_notes where space_id=s and id=note_id),'derived summary retained with sanitized checksum and without original');
 perform pg_temp.expect((select request_json::jsonb->>'question'='Keep this user question' and response_json::jsonb->>'answer'='Independent answer remains' and position(original in request_json||response_json)=0 from public.wm_questions where space_id=s and id=q),'independent chat retained without source copy');
 perform pg_temp.expect(not exists(select 1 from public.wm_source_deletion_candidate_rows(s) where position(original in data::text)>0),'technical candidate canary scan clear');
 perform public.wm_source_deletion_check(s,deletion,owner,'local_caches',jsonb_build_object('rebuilt',true,'canary_scan_clear',true));
 begin
  perform public.wm_source_deletion_check(s,deletion,owner,'backup_sets',jsonb_build_object('restore_ledger_persisted',true,'retention_policy','14-latest-plus-8-observed-weeks','minimum_deletion_revision',2));
  raise exception 'Pre-purge restore watermark accepted';
 exception when invalid_parameter_value then null; end;
 perform public.wm_source_deletion_check(s,deletion,owner,'backup_sets',jsonb_build_object('restore_ledger_persisted',true,'retention_policy','14-latest-plus-8-observed-weeks','minimum_deletion_revision',3));
 result:=public.wm_source_deletion_finalize(s,deletion,owner);
 perform pg_temp.expect(result->>'state'='verified','purge finalizes only after all scopes');
 result:=public.wm_generation_stage(s,'77777777-7777-4777-8777-777777777777',2,'Checkpoint generation',
  jsonb_build_object('format','wm-generation-review-v1','review_sha256',repeat('8',64),'base_sha256',repeat('9',64),
   'state_sha256',repeat('a',64),'entries',jsonb_build_array(jsonb_build_object('kind','redacted_source','package',package)),
   'new_sources','[]'::jsonb,'source_reviews','{}'::jsonb,'identity_links','[]'::jsonb,'diff','[]'::jsonb,
   'observation_diff','[]'::jsonb,'reason','Verified checkpoint remains a valid generation base'));
 perform pg_temp.expect(result->>'state'='pending','generation can stage after verified privacy checkpoint');
 new_body:='Explicitly new source body';new_hash:=encode(extensions.digest(convert_to(new_body,'UTF8'),'sha256'),'hex');new_version:=encode(extensions.digest(convert_to(src||':'||new_hash,'UTF8'),'sha256'),'hex');
 perform public.wm_source_reimport_authorize(s,'79999999-9999-4999-8999-999999999999',owner,src,new_hash,'Owner explicitly reimports a new hash');
 insert into public.wm_source_versions(space_id,id,source_id,content_hash,event_date,title,transcript,observed_at)
 values(s,new_version,src,new_hash,'2026-09-20','New source',new_body,'2026-09-20T10:00:00Z');
 select value into result from jsonb_array_elements(public.wm_source_deletion_ledger(s,owner)) value
  where value->>'deletion_id'=deletion::text;
 perform pg_temp.expect((result->>'superseded_by_reimport')::boolean,
  'verified deletion is not the current UI state after actual authorized reimport');
 second_package:=package||jsonb_build_object('source',(package->'source')||jsonb_build_object('id',new_version,'content_hash',new_hash,'event_date','2026-09-20','title','New source','observed_at','2026-09-20T10:00:00Z'),
  'attestation',(package->'attestation')||jsonb_build_object('original_content_sha256',new_hash));
 begin
  perform public.wm_source_deletion_stage(s,'7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',owner,src,
   jsonb_build_array(jsonb_set(second_package,'{evidence_manifest,entries}','[{"quote":"tampered","quote_sha256":"bad"}]'::jsonb)));
  raise exception 'Tampered package accepted';
 exception when invalid_parameter_value then null; end;
 result:=public.wm_source_deletion_stage(s,'7bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',owner,src,jsonb_build_array(second_package));
 perform pg_temp.expect(result->>'state'='prepared','reimported source can enter a second deletion epoch');
 select value into result from jsonb_array_elements(public.wm_source_deletion_ledger(s,owner)) value
  where value->>'deletion_id'='7bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
 perform pg_temp.expect(result->>'state'='prepared' and not (result->>'superseded_by_reimport')::boolean,
  'active second deletion remains the current UI state');
 for c in select * from public.wm_source_deletion_candidate_rows(s) loop
  perform public.wm_source_deletion_plan_put(s,'7bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',owner,c.scope,c.record_key,
   encode(extensions.digest(convert_to(c.data::text,'UTF8'),'sha256'),'hex'),c.data,
   jsonb_build_object('changed',false,'removed_characters',0));
 end loop;
 snapshot:=jsonb_build_object('format','wm-projection-snapshot-v1','snapshot_sha256',repeat('5',64),
  'rows_sha256',repeat('6',64),'state_sha256',repeat('7',64),'logical_basis_sha256',repeat('8',64),
  'through_revision',2,'tables','{}'::jsonb,'logical_basis','[]'::jsonb,
  'deletions',jsonb_build_array(
    jsonb_build_object('deletion_id',prior_deletion,'source_id',prior_src),
    jsonb_build_object('deletion_id','7bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','source_id',src)));
 result:=public.wm_source_deletion_purge(s,'7bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',owner,
  '7ccccccc-cccc-4ccc-8ccc-cccccccccccc',snapshot);
 perform pg_temp.expect(result->>'state'='purging','second deletion epoch reaches the atomic purge boundary');
 perform pg_temp.expect((select transcript is null and redaction_id='7bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
  from public.wm_source_versions where space_id=s and id=new_version),
  'second deletion epoch removes the explicitly reimported original');
end $$;
rollback;
