-- Restore the durable replay identity field while preserving recovery diagnostics.
do $migration$
declare
 signature regprocedure:='public.wm_job_detail(uuid,text)'::regprocedure;
 original text;
 updated text;
 verified text;
 needle text:=$needle$jsonb_build_object('index',c.call_index,'received'$needle$;
 replacement text:=$replacement$jsonb_build_object('index',c.call_index,'request_hash',c.request_hash,'received'$replacement$;
begin
 original:=pg_get_functiondef(signature);
 if original is null or position('transport_failures' in original)=0
    or position('request_hash'',c.request_hash' in original)>0
    or (length(original)-length(replace(original,needle,'')))/length(needle)!=1 then
   raise exception 'wm_job_detail contract changed; manual merge required' using errcode='55000';
 end if;
 updated:=replace(original,needle,replacement);
 execute updated;
 verified:=pg_get_functiondef(signature);
 if replace(verified,replacement,needle) is distinct from original
    or position('transport_failures' in verified)=0 then
   raise exception 'wm_job_detail changed beyond request-hash restoration' using errcode='55000';
 end if;
end $migration$;
