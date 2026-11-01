-- Evaluate each complete isolation proof once per status statement.
-- MATERIALIZED is statement-local: no persisted cache and no weakened proof.
-- Keep the existing function attributes, ACL and every unrelated status field.
do $migration$
declare
 sig regprocedure:='public.wm_processing_status(uuid)'::regprocedure;
 original text; changed text; verified text; n integer;
 needles text[]:=array[
 $n$ select jsonb_build_object$n$,
 $n$from public.wm_job_isolations i
    where i.space_id=p_space_id and public.wm_job_isolation_valid(i.space_id,i.job_id)$n$,
 $n$not public.wm_job_isolation_valid(j0.space_id,j0.id)$n$,
 $n$public.wm_job_isolation_valid(j.space_id,j.id) as technical_isolation$n$
 ];
 replacements text[]:=array[
 $r$ with status_isolations as materialized (
   select i.space_id,i.job_id,public.wm_job_isolation_valid(i.space_id,i.job_id) as valid
   from public.wm_job_isolations i where i.space_id=p_space_id
 )
 select jsonb_build_object$r$,
 $r$from status_isolations i where i.valid$r$,
 $r$not exists(select 1 from status_isolations i
          where i.space_id=j0.space_id and i.job_id=j0.id and i.valid)$r$,
 $r$exists(select 1 from status_isolations i
        where i.space_id=j.space_id and i.job_id=j.id and i.valid) as technical_isolation$r$
 ];
begin
 original:=pg_get_functiondef(sig);
 changed:=original;
 if original is null or position('status_isolations' in original)>0 then
   raise exception 'wm_processing_status changed; bounded isolation merge required' using errcode='55000';
 end if;
 for n in 1..array_length(needles,1) loop
   if (length(original)-length(replace(original,needles[n],'')))/length(needles[n])!=1 then
     raise exception 'wm_processing_status isolation branch % changed; manual merge required',n using errcode='55000';
   end if;
   changed:=replace(changed,needles[n],replacements[n]);
 end loop;
 execute changed;
 verified:=pg_get_functiondef(sig);
 for n in reverse array_length(needles,1)..1 loop
   verified:=replace(verified,replacements[n],needles[n]);
 end loop;
 if verified is distinct from original then
   raise exception 'wm_processing_status changed beyond statement-local isolation reuse' using errcode='55000';
 end if;
end $migration$;
