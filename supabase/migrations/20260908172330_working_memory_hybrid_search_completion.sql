create or replace function public.wm_search_query(p_space_id uuid,p_search_snapshot_id text,p_query_text text,p_query_embedding extensions.vector(1536),p_kinds text[],p_match_count integer default 20)
 returns jsonb language plpgsql set search_path='' set plan_cache_mode='force_custom_plan' as $$
declare ids text[]; result jsonb; request_hash text;
begin
 -- Load pgvector before its custom settings on a fresh pooled connection.
 perform extensions.vector_dims(p_query_embedding);
 perform set_config('hnsw.ef_search','200',true);
 perform set_config('hnsw.iterative_scan','strict_order',true);
 if p_match_count not in (20,40) or length(p_query_text)<1 or octet_length(p_query_text)>7500 then raise exception 'Invalid search query' using errcode='22023'; end if;
 request_hash:=encode(extensions.digest(jsonb_build_array(p_query_text,p_query_embedding::text,p_kinds,p_match_count)::text,'sha256'),'hex');
 select results into result from public.wm_search_results where space_id=p_space_id and snapshot_id=p_search_snapshot_id and query_hash=request_hash;
 if found then return result; end if;
 select document_ids into ids from public.wm_search_snapshots where space_id=p_space_id and id=p_search_snapshot_id;
 if not found then raise exception 'Search snapshot unavailable' using errcode='22023'; end if;
 -- Snapshot membership is hashed once; work keeps exact vector ranking.
 -- The lexical branch uses OR terms so a multi-keyword query retains partial matches.
 with members as materialized (select unnest(ids) id),
 query as (select to_tsquery('german'::regconfig,coalesce(nullif((select string_agg(quote_literal(term),' | ') from unnest(tsvector_to_array(to_tsvector('german'::regconfig,p_query_text))) term),''),'''''')) q),
 lex_top as (select d.id,ts_rank_cd(d.fts,q) score from public.wm_search_documents d join members m on m.id=d.id cross join query where d.space_id=p_space_id and d.kind=any(p_kinds) and d.fts@@q order by score desc,d.id limit p_match_count),
 lex as(select id,row_number() over(order by score desc,id) rank from lex_top),
 vec_candidates as materialized (
  -- Work has a small exact branch. The complete corpus uses its vector index.
  (select d.id,d.embedding operator(extensions.<=>) p_query_embedding distance from public.wm_search_documents d
   where p_kinds=array['work']::text[] and d.space_id=p_space_id and d.kind='work' and d.id in (select id from members)
   order by (d.embedding operator(extensions.<=>) p_query_embedding)+0 limit p_match_count)
  union all
  (select d.id,d.embedding operator(extensions.<=>) p_query_embedding distance from public.wm_search_documents d
   where p_kinds<>array['work']::text[] and d.space_id=p_space_id and d.kind=any(p_kinds) and d.id in (select id from members)
   order by d.embedding operator(extensions.<=>) p_query_embedding limit p_match_count)
 ),
 vec_top as(select * from vec_candidates order by distance,id limit p_match_count),
 vec as(select id,row_number() over(order by distance,id) rank from vec_top),
 scores as(select coalesce(l.id,v.id) id,coalesce(1.0/(60+l.rank),0)+coalesce(1.0/(60+v.rank),0) score,l.rank lexical_rank,v.rank vector_rank from lex l full join vec v using(id)),
 hits as(select d.id,d.kind,d.target_id,d.source_id,d.source_version,d.event_date,d.observed_at,d.body as text,d.metadata,s.score,s.lexical_rank,s.vector_rank
 from scores s join public.wm_search_documents d using(id) where d.space_id=p_space_id order by s.score desc,d.id)
 select coalesce(jsonb_agg(to_jsonb(hits)),'[]'::jsonb) into result from hits;
 insert into public.wm_search_results values(p_space_id,p_search_snapshot_id,request_hash,result,now()) on conflict do nothing;
 select results into result from public.wm_search_results where space_id=p_space_id and snapshot_id=p_search_snapshot_id and query_hash=request_hash;
 return result;
end $$;



alter table public.wm_backup_records drop constraint wm_backup_records_kind_check;
alter table public.wm_backup_records add constraint wm_backup_records_kind_check check(kind in ('config','job','call','job_decision','generation_review','search_document','search_snapshot','search_result'));
do $$ declare definition text; begin
 select pg_get_functiondef(oid) into definition from pg_proc where pronamespace='public'::regnamespace and proname='wm_backup_begin';
 if definition not like '%search_snapshot%' or definition like '%search_result%' then raise exception 'Unexpected backup function version'; end if;
 execute replace(definition,' ) x;', $replacement$
  union all select 'search_result',to_jsonb(r)::text from public.wm_search_results r where r.space_id=p_space_id
 ) x;$replacement$);
end $$;
-- Keep large model receipts alone; page small vector rows within a byte bound.
create or replace function public.wm_backup_page(p_space_id uuid,p_snapshot_id uuid,p_after bigint)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if p_after is null or p_after<0 or not exists(select 1 from public.wm_backup_snapshots where id=p_snapshot_id and space_id=p_space_id) then
  raise exception 'Snapshot unavailable' using errcode='22023'; end if;
 return coalesce((with candidates as (select sequence,kind,record_json,record_hash from public.wm_backup_records where snapshot_id=p_snapshot_id and sequence>p_after order by sequence limit 32),
 sized as(select *,row_number() over(order by sequence) n,sum(octet_length(record_json)) over(order by sequence) bytes from candidates)
 select jsonb_agg(jsonb_build_object('sequence',sequence,'kind',kind,'record_json',record_json,'record_hash',record_hash) order by sequence) from sized where n=1 or bytes<1000000),'[]'::jsonb);
end $$;
