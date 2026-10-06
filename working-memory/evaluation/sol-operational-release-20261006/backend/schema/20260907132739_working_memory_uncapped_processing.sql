begin;
alter table public.wm_processing_config alter column budget_micro_usd drop not null;
alter table public.wm_processing_config drop constraint wm_processing_config_check;
alter table public.wm_processing_config add constraint wm_processing_config_check check (
not enabled or (automatic_from is not null and pipeline is not null and length(pipeline)>0 and (budget_micro_usd is null or budget_micro_usd>0)));
comment on column public.wm_processing_config.budget_micro_usd is 'NULL means explicitly authorized uncapped processing; zero remains disabled by default. All calls retain cost accounting.';
CREATE OR REPLACE FUNCTION public.wm_reserve_call(p_space_id uuid, p_job_id text, p_lease_token uuid, p_call_index integer, p_request_json text, p_reserved_micro_usd bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare s public.wm_spaces%rowtype; c public.wm_processing_config%rowtype; j public.wm_jobs%rowtype;
 r public.wm_model_calls%rowtype; h text; total bigint;
begin
 select * into s from public.wm_spaces where id=p_space_id for update;
 if not found or s.state='retired' then raise exception 'Space unavailable' using errcode='22023'; end if;
 select * into c from public.wm_processing_config where space_id=p_space_id;
 if not found or not c.enabled then raise exception 'Processing disabled' using errcode='22023'; end if;
 select * into j from public.wm_jobs where space_id=p_space_id and id=p_job_id for update;
 if not found or j.state!='running' or j.lease_token is distinct from p_lease_token or j.lease_until<=clock_timestamp()
   or j.pipeline is distinct from c.pipeline or j.event_date<c.automatic_from or j.expected_revision!=s.revision then
   raise exception 'Job lease or context no longer valid' using errcode='40001';
 end if;
 if p_call_index is null or p_call_index<0 or p_call_index>15 or p_request_json is null
   or jsonb_typeof(p_request_json::jsonb)!='object' or p_reserved_micro_usd is null or p_reserved_micro_usd<=0 then
   raise exception 'Invalid call reservation' using errcode='22023';
 end if;
 h:=encode(extensions.digest(convert_to(p_request_json,'UTF8'),'sha256'),'hex');
 select * into r from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and call_index=p_call_index;
 if found then
   if r.request_hash!=h or r.reserved_micro_usd!=p_reserved_micro_usd then raise exception 'Call identity changed' using errcode='23505'; end if;
   -- A replay may consume an existing response, but must never send an unresolved call twice.
   return to_jsonb(r)||jsonb_build_object('send',false);
 end if;
 if p_call_index!=(select count(*) from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id)
   or exists(select 1 from public.wm_model_calls where space_id=p_space_id and job_id=p_job_id and response_json is null) then
   raise exception 'Previous call unresolved or missing' using errcode='22023';
 end if;
 select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) into total from public.wm_model_calls where space_id=p_space_id;
 if c.budget_micro_usd is not null and total+p_reserved_micro_usd>c.budget_micro_usd then
   return jsonb_build_object('send',false,'state','budget_exceeded','accounted_micro_usd',total);
 end if;
 insert into public.wm_model_calls(space_id,job_id,call_index,request_json,request_hash,reserved_micro_usd)
 values(p_space_id,p_job_id,p_call_index,p_request_json,h,p_reserved_micro_usd) returning * into r;
 update public.wm_jobs set lease_until=clock_timestamp()+interval '10 minutes',updated_at=now() where space_id=p_space_id and id=p_job_id;
 return to_jsonb(r)||jsonb_build_object('send',true);
end; $function$
;
commit;
