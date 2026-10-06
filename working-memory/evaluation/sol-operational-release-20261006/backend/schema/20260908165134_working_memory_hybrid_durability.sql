create or replace function public.wm_search_query(p_space_id uuid,p_search_snapshot_id text,p_query_text text,p_query_embedding extensions.vector(1536),p_kinds text[],p_match_count integer default 20)
 returns jsonb language plpgsql stable set search_path='' as $$
declare ids text[]; result jsonb;
begin
 if p_match_count not in (20,40) or length(p_query_text)<1 or octet_length(p_query_text)>7500 then raise exception 'Invalid search query' using errcode='22023'; end if;
 select document_ids into ids from public.wm_search_snapshots where space_id=p_space_id and id=p_search_snapshot_id;
 if not found then raise exception 'Search snapshot unavailable' using errcode='22023'; end if;
 -- Exact vector ranking inside the pinned scope avoids ANN filtering recall loss.
 -- The lexical branch uses OR terms so a multi-keyword query retains partial matches.
 with documents as materialized (select d.* from public.wm_search_documents d where d.space_id=p_space_id and d.id=any(ids) and d.kind=any(p_kinds)),
 query as (select to_tsquery('german'::regconfig,coalesce(nullif((select string_agg(quote_literal(term),' | ') from unnest(tsvector_to_array(to_tsvector('german'::regconfig,p_query_text))) term),''),'''''')) q),
 lex_top as (select id,ts_rank_cd(fts,q) score from documents,query where fts@@q order by score desc,id limit p_match_count),
 lex as(select id,row_number() over(order by score desc,id) rank from lex_top),
 vec_top as(select id,embedding operator(extensions.<=>) p_query_embedding distance from documents order by distance,id limit p_match_count),
 vec as(select id,row_number() over(order by distance,id) rank from vec_top),
 scores as(select coalesce(l.id,v.id) id,coalesce(1.0/(60+l.rank),0)+coalesce(1.0/(60+v.rank),0) score,l.rank lexical_rank,v.rank vector_rank from lex l full join vec v using(id)),
 hits as(select d.id,d.kind,d.target_id,d.source_id,d.source_version,d.event_date,d.observed_at,d.body as text,d.metadata,s.score,s.lexical_rank,s.vector_rank
 from scores s join documents d using(id) order by s.score desc,d.id)
 select coalesce(jsonb_agg(to_jsonb(hits)),'[]'::jsonb) into result from hits;
 return result;
end $$;


-- Keep paid vectors in the encrypted backup/verified restore path as well.
alter table public.wm_backup_records drop constraint wm_backup_records_kind_check;
alter table public.wm_backup_records add constraint wm_backup_records_kind_check check(kind in ('config','job','call','job_decision','generation_review','search_document','search_snapshot'));
do $$ declare definition text; begin
 select pg_get_functiondef(oid) into definition from pg_proc where pronamespace='public'::regnamespace and proname='wm_backup_begin';
 if definition not like '% ) x;%' then raise exception 'Unexpected backup function version'; end if;
 execute replace(definition,' ) x;',$replacement$
  union all select 'search_document',(to_jsonb(d)-'fts')::text from public.wm_search_documents d where d.space_id=p_space_id
  union all select 'search_snapshot',to_jsonb(s)::text from public.wm_search_snapshots s where s.space_id=p_space_id
 ) x;$replacement$);
 select pg_get_functiondef(oid) into definition from pg_proc where pronamespace='public'::regnamespace and proname='wm_reserve_call';
 execute replace(definition,'return to_jsonb(r)||jsonb_build_object(''send'',false);',
 'update public.wm_jobs set lease_until=clock_timestamp()+interval ''10 minutes'',updated_at=now() where space_id=p_space_id and id=p_job_id; return to_jsonb(r)||jsonb_build_object(''send'',false);');
end $$;
