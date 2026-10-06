-- A reservation estimate is admission control at first send, not call identity.
-- Replays retain the immutable stored reservation and never send again.
do $migration$
declare
 signature regprocedure:='public.wm_reserve_call(uuid,text,uuid,integer,text,bigint)'::regprocedure;
 original text;
 updated text;
 verified text;
 needle text:=$needle$if r.request_hash!=h or r.reserved_micro_usd!=p_reserved_micro_usd then raise exception 'Call identity changed' using errcode='23505'; end if;$needle$;
 replacement text:=$replacement$if r.request_hash!=h or r.request_json is distinct from p_request_json then raise exception 'Call identity changed' using errcode='23505'; end if;$replacement$;
begin
 original:=pg_get_functiondef(signature);
 if original is null or (length(original)-length(replace(original,needle,'')))/length(needle)!=1 then
   raise exception 'wm_reserve_call replay guard changed; manual merge required' using errcode='55000';
 end if;
 updated:=replace(original,needle,replacement);
 execute updated;
 verified:=pg_get_functiondef(signature);
 if replace(verified,replacement,needle) is distinct from original then
   raise exception 'wm_reserve_call changed beyond replay identity' using errcode='55000';
 end if;
end $migration$;
