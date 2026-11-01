begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;

insert into auth.users(id) values('a2111111-1111-4111-8111-111111111111');
insert into public.wm_spaces(id,owner_id,label)
values('b2222222-2222-4222-8222-222222222222','a2111111-1111-4111-8111-111111111111','Recovery cost accounting');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd)
values('b2222222-2222-4222-8222-222222222222',true,'2026-09-08','recovery-cost-test',1250);

set local role service_role;
do $$
declare
 s uuid:='b2222222-2222-4222-8222-222222222222';
 owner uuid:='a2111111-1111-4111-8111-111111111111';
 body text:='Synthetic recovery cost fixture.'; h text; metadata text; document_id text; j jsonb;
 lease uuid:='c3333333-3333-4333-8333-333333333333'; fixture_payload jsonb; status jsonb; reserved jsonb;
 deletion_one uuid:='d4444444-4444-4444-8444-444444444444';
 deletion_two uuid:='e5555555-5555-4555-8555-555555555555';
 review_id uuid:='f6666666-6666-4666-8666-666666666666';
 review_hash text:=repeat('f',64); job_id text;
begin
 h:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 metadata:=jsonb_build_object('source_id','synthetic:recovery-cost','event_date','2026-09-09',
   'title','Recovery cost fixture','body_sha256',h,'export_sha256',h,'body_offset_characters',0)::text;
 document_id:=encode(extensions.digest(convert_to('synthetic:recovery-cost:'||metadata,'UTF8'),'sha256'),'hex');
 perform public.wm_archive_put(s,jsonb_build_object('id',document_id,'source_id','synthetic:recovery-cost',
   'event_date','2026-09-09','observed_at','2026-09-09T10:00:00Z','title','Recovery cost fixture',
   'body_hash',h,'export_hash',h,'body',body,'export',body,'metadata_json',metadata));
 j:=public.wm_enqueue(s,document_id,'recovery-cost-test');job_id:=j->>'id';
 update public.wm_jobs set state='running',expected_revision=0,lease_token=lease,
   lease_until=clock_timestamp()+interval '10 minutes',attempts=1 where space_id=s and id=job_id;
 perform public.wm_reserve_call(s,job_id,lease,0,'{"fixture":"central"}',1000);
 perform public.wm_receive_call(s,job_id,lease,0,'{"fixture":"central-response"}',1000);

 fixture_payload:=jsonb_build_object('format','wm-generation-review-v1','review_sha256',review_hash,
  'entries',jsonb_build_array(jsonb_build_object('payload',jsonb_build_object(
   'provenance',jsonb_build_object('mode','bounded_recovery_generation','job_id',job_id,
    'recovery_receipts',jsonb_build_array(
     jsonb_build_object('call_index',22,'request_hash',repeat('1',64),'response_hash',repeat('2',64),
      'model','model-a','usage',jsonb_build_object('input_tokens',10),'reserved_micro_usd',200,
      'actual_micro_usd',100,'provider_input_tokens',10),
     jsonb_build_object('call_index',23,'request_hash',repeat('3',64),'response_hash',repeat('4',64),
      'model','model-b','usage',jsonb_build_object('input_tokens',20),'reserved_micro_usd',300,
      'actual_micro_usd',200,'provider_input_tokens',20))),
   'usage',jsonb_build_object('recovery_actual_micro_usd',300)))));
 insert into public.wm_generation_reviews(space_id,id,expected_revision,label,payload,review_sha256,
   job_id,job_updated_at,state,decision_command_id,decision_actor_id,decision_reason,decision_hash,decision_result,decided_at)
 select s,review_id,0,'Recovery cost fixture',fixture_payload,review_hash,job_id,updated_at,'accepted',
   gen_random_uuid(),owner,'accepted',repeat('9',64),'{}'::jsonb,clock_timestamp()
 from public.wm_jobs where space_id=s and id=job_id;

 perform pg_temp.expect(public.wm_generation_recovery_accounted(s)=300,'metadata recovery cost derived');
 status:=public.wm_processing_status(s);
 perform pg_temp.expect((status->>'accounted_micro_usd')::bigint=1300,'status includes recovery cost');
 reserved:=public.wm_reserve_call(s,job_id,lease,1,'{"fixture":"blocked"}',100);
 perform pg_temp.expect(reserved->>'state'='budget_exceeded' and
   (reserved->>'accounted_micro_usd')::bigint=1300,'reservation budget includes recovery cost');

 insert into public.wm_source_deletions(space_id,id,source_id,actor_id,request_hash,ledger_revision,state,
   archive_document_ids,original_content_hashes,required_scopes,completed_at)
 values
  (s,deletion_one,'synthetic:deleted-one',owner,repeat('5',64),1,'verified','{}','{}',array['generation_payloads'],clock_timestamp()),
  (s,deletion_two,'synthetic:deleted-two',owner,repeat('6',64),2,'verified','{}','{}',array['generation_payloads'],clock_timestamp());
 update public.wm_generation_reviews set original_payload_hash=repeat('7',64),redaction_id=deletion_one,
  payload=jsonb_build_object('format','wm-redacted-generation-v1','deletion_id',deletion_one,'sanitized_payload',payload)
  where space_id=s and id=review_id;
 perform pg_temp.expect(public.wm_generation_recovery_accounted(s)=300,'single sanitized wrapper remains accountable');
 update public.wm_generation_reviews set original_payload_hash=repeat('8',64),redaction_id=deletion_two,
  payload=jsonb_build_object('format','wm-redacted-generation-v1','deletion_id',deletion_two,'sanitized_payload',payload)
  where space_id=s and id=review_id;
 perform pg_temp.expect(public.wm_generation_recovery_accounted(s)=300,'nested sanitized wrappers remain accountable');

 update public.wm_generation_reviews set payload=jsonb_set(payload,'{deletion_id}',to_jsonb(deletion_one::text))
  where space_id=s and id=review_id;
 begin
  perform public.wm_generation_recovery_accounted(s);
  raise exception 'FAILED: mismatched current redaction identity accepted';
 exception when check_violation then null; end;
 update public.wm_generation_reviews set payload=jsonb_set(payload,'{deletion_id}',to_jsonb(deletion_two::text))
  where space_id=s and id=review_id;

 insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd,
   actual_micro_usd,response_json,response_hash,received_at)
 values
  (s,job_id,22,'{}',repeat('1',64),200,100,'{}',repeat('2',64),clock_timestamp()),
  (s,job_id,23,'{}',repeat('3',64),300,200,'{}',repeat('4',64),clock_timestamp());
 perform pg_temp.expect(public.wm_generation_recovery_accounted(s)=0,'exact durable receipts are deduplicated');
 status:=public.wm_processing_status(s);
 perform pg_temp.expect((status->>'accounted_micro_usd')::bigint=1300,'deduplication does not change total cost');

 update public.wm_generation_reviews set payload=jsonb_set(payload,
  '{sanitized_payload,sanitized_payload,entries,0,payload,usage,recovery_actual_micro_usd}','301'::jsonb)
  where space_id=s and id=review_id;
 begin
  perform public.wm_generation_recovery_accounted(s);
  raise exception 'FAILED: mismatched recovery total accepted';
 exception when check_violation then null; end;
end; $$;

do $$
declare reserve_def text:=pg_get_functiondef('public.wm_reserve_call(uuid,text,uuid,integer,text,bigint)'::regprocedure);
 status_def text:=pg_get_functiondef('public.wm_processing_status(uuid)'::regprocedure);
begin
 perform pg_temp.expect(position('p_call_index > 1023' in reserve_def)>0 or position('p_call_index>1023' in reserve_def)>0,
  'reserve retains the 1023 call-index bound');
 perform pg_temp.expect(position('lease_until = (clock_timestamp() + ''00:10:00''::interval)' in reserve_def)>0
  or position('lease_until=clock_timestamp()+interval ''10 minutes''' in reserve_def)>0,
  'reserve retains idempotent lease refresh');
 perform pg_temp.expect((length(reserve_def)-length(replace(reserve_def,
  'public.wm_generation_recovery_accounted(p_space_id)','')))/length('public.wm_generation_recovery_accounted(p_space_id)')=1,
  'reserve has exactly one recovery accounting patch');
 perform pg_temp.expect((length(status_def)-length(replace(status_def,
  'public.wm_generation_recovery_accounted(p_space_id)','')))/length('public.wm_generation_recovery_accounted(p_space_id)')=1,
  'status has exactly one recovery accounting patch');
end $$;
reset role;
rollback;
