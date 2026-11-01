-- Conversations contain metadata only; their messages are canonical question receipts.
alter table public.wm_backup_records drop constraint wm_backup_records_kind_check;
alter table public.wm_backup_records add constraint wm_backup_records_kind_check check(kind in
 ('config','job','call','job_decision','generation_review','search_document','search_snapshot','search_result',
  'conversation','pipeline_recovery','question','question_call','source_deletion','source_deletion_version','source_deletion_check','source_reimport_authorization'));
do $$ declare definition text; begin
 select pg_get_functiondef('public.wm_backup_begin(uuid,uuid)'::regprocedure) into definition;
 if position(') x;' in definition)=0 or position('union all select ''question'',to_jsonb(q)::text' in definition)=0
    or position('wm_conversations' in definition)>0 then
  raise exception 'Unexpected backup implementation for conversation extension';
 end if;
 definition:=replace(definition,') x;',$branch$
  union all select 'conversation',to_jsonb(c)::text from public.wm_conversations c where c.space_id=p_space_id
  union all select 'pipeline_recovery',to_jsonb(r)::text from public.wm_pipeline_recoveries r where r.space_id=p_space_id
 ) x;$branch$);
 execute definition;
end $$;
