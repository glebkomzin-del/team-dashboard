-- Derive recovery costs from compact metadata already retained in accepted
-- generation payloads. No request/response body and no extra mutable ledger.
create function public.wm_generation_recovery_accounted(p_space_id uuid)
returns bigint language plpgsql stable security invoker set search_path='' as $$
declare
  g public.wm_generation_reviews%rowtype;
  provenance jsonb;
  receipt jsonb;
  usage_block jsonb;
  metadata jsonb;
  effective_payload jsonb;
  seen jsonb:='{}'::jsonb;
  seen_indices integer[];
  blocks integer;
  usage_blocks integer;
  receipt_count integer;
  call_index_value integer;
  actual_value bigint;
  reserved_value bigint;
  input_value bigint;
  declared_total bigint;
  receipt_total bigint;
  total bigint:=0;
  identity_key text;
  wrapper_deletion_id text;
  wrapper_depth integer;
begin
  for g in select * from public.wm_generation_reviews
      where space_id=p_space_id and state='accepted' order by id loop
    effective_payload:=g.payload;
    wrapper_depth:=0;
    while effective_payload->>'format'='wm-redacted-generation-v1' loop
      wrapper_depth:=wrapper_depth+1;
      wrapper_deletion_id:=coalesce(effective_payload->>'deletion_id','');
      if wrapper_depth>1024
         or wrapper_deletion_id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
         or jsonb_typeof(effective_payload->'sanitized_payload') is distinct from 'object'
         or not exists(select 1 from public.wm_source_deletions d
              where d.space_id=g.space_id and d.id=wrapper_deletion_id::uuid
                and d.state in ('purging','verified')) then
        raise exception 'Invalid redacted generation review envelope' using errcode='23514';
      end if;
      if wrapper_depth=1 and (g.redaction_id is null
          or wrapper_deletion_id is distinct from g.redaction_id::text
          or coalesce(g.original_payload_hash,'') !~ '^[0-9a-f]{64}$') then
        raise exception 'Generation review redaction metadata is inconsistent' using errcode='23514';
      end if;
      effective_payload:=effective_payload->'sanitized_payload';
    end loop;
    if (wrapper_depth=0 and (g.redaction_id is not null or g.original_payload_hash is not null))
       or (wrapper_depth>0 and g.redaction_id is null) then
      raise exception 'Generation review redaction metadata is inconsistent' using errcode='23514';
    end if;
    if effective_payload->>'review_sha256' is distinct from g.review_sha256 then
      raise exception 'Generation review hash metadata changed' using errcode='23514';
    end if;
    blocks:=0;usage_blocks:=0;receipt_count:=0;receipt_total:=0;declared_total:=null;seen_indices:=array[]::integer[];
    for usage_block in select value from jsonb_path_query(effective_payload,'strict $.**.usage') as q(value) loop
      if usage_block ? 'recovery_actual_micro_usd' then
        usage_blocks:=usage_blocks+1;
        if jsonb_typeof(usage_block->'recovery_actual_micro_usd')!='number'
           or (usage_block->>'recovery_actual_micro_usd') !~ '^[0-9]+$' then
          raise exception 'Invalid generation recovery usage total' using errcode='23514';
        end if;
        declared_total:=(usage_block->>'recovery_actual_micro_usd')::bigint;
      end if;
    end loop;
    for provenance in select value from jsonb_path_query(effective_payload,'strict $.**.provenance') as q(value) loop
      if provenance->>'mode'='bounded_recovery_generation' then
        blocks:=blocks+1;
        if g.job_id is null or provenance->>'job_id' is distinct from g.job_id
           or jsonb_typeof(provenance->'recovery_receipts')!='array'
           or jsonb_array_length(provenance->'recovery_receipts') not between 1 and 32 then
          raise exception 'Invalid generation recovery provenance' using errcode='23514';
        end if;
        for receipt in select value from jsonb_array_elements(provenance->'recovery_receipts') as q(value) loop
          if jsonb_typeof(receipt)!='object'
             or not(receipt ?& array['call_index','request_hash','response_hash','model','usage','reserved_micro_usd','actual_micro_usd','provider_input_tokens'])
             or jsonb_typeof(receipt->'call_index')!='number' or (receipt->>'call_index') !~ '^[0-9]+$'
             or coalesce(receipt->>'request_hash','') !~ '^[0-9a-f]{64}$'
             or coalesce(receipt->>'response_hash','') !~ '^[0-9a-f]{64}$'
             or coalesce(length(receipt->>'model'),0) not between 1 and 200 or jsonb_typeof(receipt->'usage')!='object'
             or jsonb_typeof(receipt->'reserved_micro_usd')!='number' or (receipt->>'reserved_micro_usd') !~ '^[1-9][0-9]*$'
             or jsonb_typeof(receipt->'actual_micro_usd')!='number' or (receipt->>'actual_micro_usd') !~ '^[0-9]+$'
             or jsonb_typeof(receipt->'provider_input_tokens')!='number' or (receipt->>'provider_input_tokens') !~ '^[0-9]+$' then
            raise exception 'Invalid generation recovery call metadata' using errcode='23514';
          end if;
          call_index_value:=(receipt->>'call_index')::integer;
          reserved_value:=(receipt->>'reserved_micro_usd')::bigint;
          actual_value:=(receipt->>'actual_micro_usd')::bigint;
          input_value:=(receipt->>'provider_input_tokens')::bigint;
          if call_index_value not between 0 and 1023 or call_index_value=any(seen_indices) then
            raise exception 'Duplicate or out-of-range generation recovery call' using errcode='23514';
          end if;
          seen_indices:=array_append(seen_indices,call_index_value);
          receipt_count:=receipt_count+1;receipt_total:=receipt_total+actual_value;
          identity_key:=g.job_id||':'||call_index_value||':'||(receipt->>'request_hash')||':'||(receipt->>'response_hash');
          metadata:=jsonb_build_object('model',receipt->>'model','usage',receipt->'usage',
            'reserved_micro_usd',reserved_value,'actual_micro_usd',actual_value,'provider_input_tokens',input_value);
          if seen ? identity_key then
            if seen->identity_key is distinct from metadata then
              raise exception 'Recovery call identity reused with changed accounting' using errcode='23514';
            end if;
            continue;
          end if;
          seen:=seen||jsonb_build_object(identity_key,metadata);
          if not exists(select 1 from public.wm_model_calls m
              where m.space_id=g.space_id and m.job_id=g.job_id and m.call_index=call_index_value
                and m.request_hash=receipt->>'request_hash' and m.response_hash=receipt->>'response_hash'
                and m.actual_micro_usd=actual_value) then
            total:=total+actual_value;
          end if;
        end loop;
      end if;
    end loop;
    if blocks>0 and (blocks!=1 or usage_blocks!=1 or receipt_count=0 or declared_total is distinct from receipt_total) then
      raise exception 'Generation recovery accounting does not reconcile' using errcode='23514';
    elsif blocks=0 and usage_blocks!=0 then
      raise exception 'Recovery usage exists without recovery provenance' using errcode='23514';
    end if;
  end loop;
  return total;
end $$;
revoke all on function public.wm_generation_recovery_accounted(uuid) from public,anon,authenticated;
grant execute on function public.wm_generation_recovery_accounted(uuid) to service_role;

-- Preserve the currently installed worker guards byte-for-byte. This migration
-- patches only the one confirmed durable-cost expression and fails closed if
-- the active function body no longer has that exact shape.
do $migration$
declare
  signature regprocedure:='public.wm_reserve_call(uuid,text,uuid,integer,text,bigint)'::regprocedure;
  original text;
  updated text;
  verified text;
  needle text:=$needle$select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) into total from public.wm_model_calls where space_id=p_space_id;$needle$;
  replacement text:=$replacement$select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0)+public.wm_generation_recovery_accounted(p_space_id) into total from public.wm_model_calls where space_id=p_space_id;$replacement$;
begin
  original:=pg_get_functiondef(signature);
  if original is null or (length(original)-length(replace(original,needle,'')))/length(needle)!=1 then
    raise exception 'wm_reserve_call cost expression changed; manual merge required' using errcode='55000';
  end if;
  updated:=replace(original,needle,replacement);
  execute updated;
  verified:=pg_get_functiondef(signature);
  if replace(verified,replacement,needle) is distinct from original then
    raise exception 'wm_reserve_call changed beyond recovery accounting' using errcode='55000';
  end if;
end $migration$;

-- The status response receives the same total without replacing any other
-- current fields or filters in wm_processing_status.
do $migration$
declare
  signature regprocedure:='public.wm_processing_status(uuid)'::regprocedure;
  original text;
  updated text;
  verified text;
  needle text:=$needle$'accounted_micro_usd',(select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) from public.wm_model_calls where space_id=p_space_id),$needle$;
  replacement text:=$replacement$'accounted_micro_usd',(select coalesce(sum(coalesce(actual_micro_usd,reserved_micro_usd)),0) from public.wm_model_calls where space_id=p_space_id)+public.wm_generation_recovery_accounted(p_space_id),$replacement$;
begin
  original:=pg_get_functiondef(signature);
  if original is null or (length(original)-length(replace(original,needle,'')))/length(needle)!=1 then
    raise exception 'wm_processing_status cost expression changed; manual merge required' using errcode='55000';
  end if;
  updated:=replace(original,needle,replacement);
  execute updated;
  verified:=pg_get_functiondef(signature);
  if replace(verified,replacement,needle) is distinct from original then
    raise exception 'wm_processing_status changed beyond recovery accounting' using errcode='55000';
  end if;
end $migration$;
