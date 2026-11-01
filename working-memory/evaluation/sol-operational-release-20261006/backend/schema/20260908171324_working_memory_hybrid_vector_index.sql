-- High-recall ANN for source navigation; lexical union and exact work search remain.
create index wm_search_vector on public.wm_search_documents using hnsw(embedding extensions.vector_cosine_ops) with (m=16,ef_construction=128);
create table public.wm_search_results (
 space_id uuid not null,snapshot_id text not null,query_hash text not null,results jsonb not null,
 created_at timestamptz not null default now(),primary key(space_id,snapshot_id,query_hash),
 foreign key(space_id,snapshot_id) references public.wm_search_snapshots(space_id,id)
);
alter table public.wm_search_results enable row level security;
revoke all on public.wm_search_results from public,anon,authenticated;
grant all on public.wm_search_results to service_role;
-- Join snapshot members once; avoid a linear array scan for every document.
create or replace function public.wm_search_query(p_space_id uuid,p_search_snapshot_id text,p_query_text text,p_query_embedding extensions.vector(1536),p_kinds text[],p_match_count integer default 20)
 returns jsonb language plpgsql set search_path='' set hnsw.ef_search=200 set hnsw.iterative_scan='strict_order' as $$
declare ids text[]; result jsonb; request_hash text;
begin
 if p_match_count not in (20,40) or length(p_query_text)<1 or octet_length(p_query_text)>7500 then raise exception 'Invalid search query' using errcode='22023'; end if;
 request_hash:=encode(extensions.digest(jsonb_build_array(p_query_text,p_query_embedding::text,p_kinds,p_match_count)::text,'sha256'),'hex');
 select results into result from public.wm_search_results where space_id=p_space_id and snapshot_id=p_search_snapshot_id and query_hash=request_hash;
 if found then return result; end if;
 select document_ids into ids from public.wm_search_snapshots where space_id=p_space_id and id=p_search_snapshot_id;
 if not found then raise exception 'Search snapshot unavailable' using errcode='22023'; end if;
 -- Exact vector ranking inside the pinned scope avoids ANN filtering recall loss.
 -- The lexical branch uses OR terms so a multi-keyword query retains partial matches.
 with members as materialized (select unnest(ids) id),
 query as (select to_tsquery('german'::regconfig,coalesce(nullif((select string_agg(quote_literal(term),' | ') from unnest(tsvector_to_array(to_tsvector('german'::regconfig,p_query_text))) term),''),'''''')) q),
 lex_top as (select d.id,ts_rank_cd(d.fts,q) score from public.wm_search_documents d join members m on m.id=d.id cross join query where d.space_id=p_space_id and d.kind=any(p_kinds) and d.fts@@q order by score desc,d.id limit p_match_count),
 lex as(select id,row_number() over(order by score desc,id) rank from lex_top),
 vec_candidates as materialized (
  -- Work has a small exact branch. The complete corpus uses its vector index.
  (select d.id,d.embedding operator(extensions.<=>) p_query_embedding distance from public.wm_search_documents d
   where p_kinds=array['work']::text[] and d.space_id=p_space_id and d.kind='work' and d.id=any(ids)
   order by (d.embedding operator(extensions.<=>) p_query_embedding)+0 limit p_match_count)
  union all
  (select d.id,d.embedding operator(extensions.<=>) p_query_embedding distance from public.wm_search_documents d
   where p_kinds<>array['work']::text[] and d.space_id=p_space_id and d.kind=any(p_kinds) and d.id=any(ids)
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


