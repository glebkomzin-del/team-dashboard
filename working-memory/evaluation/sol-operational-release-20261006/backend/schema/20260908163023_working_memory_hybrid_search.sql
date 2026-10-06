-- Separate immutable navigation index; canonical journal remains authoritative.
create extension if not exists vector with schema extensions;
create table public.wm_search_documents (
 space_id uuid not null references public.wm_spaces(id), id text not null check(id ~ '^[a-f0-9]{64}$'),
 kind text not null check(kind in ('knowledge','work','passage','summary','feedback')),
 target_id text not null, source_id text not null, source_version text not null,
 event_date date not null, observed_at timestamptz, body text not null check(length(body)>0 and octet_length(body)<=8000),
 metadata jsonb not null check(jsonb_typeof(metadata)='object'),
 content_hash text not null check(content_hash ~ '^[a-f0-9]{64}$'),
 embedding_model text not null check(embedding_model='text-embedding-3-small'),
 embedding extensions.vector(1536) not null,
 fts tsvector generated always as (to_tsvector('german'::regconfig,body)) stored,
 primary key(space_id,id)
);
create index wm_search_fts on public.wm_search_documents using gin(fts);
create index wm_search_hash on public.wm_search_documents(space_id,content_hash);
create table public.wm_search_snapshots (
 space_id uuid not null references public.wm_spaces(id), id text not null check(id ~ '^[a-f0-9]{64}$'),
 document_ids text[] not null, created_at timestamptz not null default now(),primary key(space_id,id)
);
alter table public.wm_search_documents enable row level security;
alter table public.wm_search_snapshots enable row level security;
revoke all on public.wm_search_documents,public.wm_search_snapshots from public,anon,authenticated;
grant all on public.wm_search_documents,public.wm_search_snapshots to service_role;

create function public.wm_search_missing(p_space_id uuid,p_document_ids text[]) returns jsonb language sql stable set search_path='' as $$
 select coalesce(jsonb_agg(i),'[]'::jsonb) from unnest(p_document_ids) i where not exists
 (select 1 from public.wm_search_documents d where d.space_id=p_space_id and d.id=i);
$$;
create function public.wm_search_cached(p_space_id uuid,p_content_hashes text[]) returns jsonb language sql stable set search_path='' as $$
 select coalesce(jsonb_object_agg(content_hash,embedding::text::jsonb),'{}'::jsonb) from
 (select distinct on(content_hash) content_hash,embedding from public.wm_search_documents
 where space_id=p_space_id and content_hash=any(p_content_hashes) order by content_hash,id) d;
$$;
create function public.wm_search_put(p_space_id uuid,p_documents jsonb) returns jsonb language plpgsql set search_path='' as $$
declare d jsonb; existing public.wm_search_documents; n integer:=0;
begin
 if jsonb_typeof(p_documents)<>'array' or jsonb_array_length(p_documents)>32 then raise exception 'Invalid search batch' using errcode='22023'; end if;
 for d in select value from jsonb_array_elements(p_documents) loop
  if encode(extensions.digest(d->>'text','sha256'),'hex')<>d->>'content_hash' or jsonb_array_length(d->'embedding')<>1536 then
    raise exception 'Search content checksum/dimension mismatch' using errcode='22023'; end if;
  select * into existing from public.wm_search_documents where space_id=p_space_id and id=d->>'id';
  if found then
   if existing.body<>d->>'text' or existing.metadata<>d->'metadata' or existing.target_id<>d->>'target_id'
    or existing.kind<>d->>'kind' or existing.source_version<>d->>'source_version' then raise exception 'Immutable search document conflict' using errcode='40001'; end if;
  else
   insert into public.wm_search_documents(space_id,id,kind,target_id,source_id,source_version,event_date,observed_at,body,metadata,content_hash,embedding_model,embedding)
    values(p_space_id,d->>'id',d->>'kind',d->>'target_id',d->>'source_id',d->>'source_version',(d->>'event_date')::date,
      (d->>'observed_at')::timestamptz,d->>'text',d->'metadata',d->>'content_hash',d->>'embedding_model',(d->'embedding')::text::extensions.vector);
  end if;
  n:=n+1;
 end loop;
 return jsonb_build_object('saved',n);
end $$;
create function public.wm_search_snapshot(p_space_id uuid,p_search_snapshot_id text,p_document_ids text[]) returns jsonb language plpgsql set search_path='' as $$
declare ids text[]; previous text[];
begin
 select coalesce(array_agg(distinct i order by i),'{}'::text[]) into ids from unnest(p_document_ids) i;
 if cardinality(ids)<>cardinality(p_document_ids) or encode(extensions.digest(array_to_string(ids,','),'sha256'),'hex')<>p_search_snapshot_id then
 raise exception 'Invalid search snapshot identity' using errcode='22023'; end if;
 if exists(select 1 from unnest(ids) i where not exists(select 1 from public.wm_search_documents d where d.space_id=p_space_id and d.id=i)) then
 raise exception 'Incomplete search snapshot' using errcode='22023'; end if;
 select document_ids into previous from public.wm_search_snapshots where space_id=p_space_id and id=p_search_snapshot_id;
 if found and previous<>ids then raise exception 'Immutable snapshot conflict' using errcode='40001'; end if;
 insert into public.wm_search_snapshots values(p_space_id,p_search_snapshot_id,ids,now()) on conflict do nothing;
 return jsonb_build_object('count',cardinality(ids));
end $$;
create function public.wm_search_query(p_space_id uuid,p_search_snapshot_id text,p_query_text text,p_query_embedding extensions.vector(1536),p_kinds text[],p_match_count integer default 20)
 returns jsonb language plpgsql stable set search_path='' as $$
declare ids text[]; result jsonb;
begin
 if p_match_count not in (20,40) or length(p_query_text)<1 or octet_length(p_query_text)>7500 then raise exception 'Invalid search query' using errcode='22023'; end if;
 select document_ids into ids from public.wm_search_snapshots where space_id=p_space_id and id=p_search_snapshot_id;
 if not found then raise exception 'Search snapshot unavailable' using errcode='22023'; end if;
 -- Exact vector ranking inside the pinned scope avoids ANN filtering recall loss.
 -- The lexical branch uses OR terms so a multi-keyword query retains partial matches.
 with documents as materialized (select d.* from public.wm_search_documents d where d.space_id=p_space_id and d.id=any(ids) and d.kind=any(p_kinds)),
 query as (select to_tsquery('german'::regconfig,coalesce(nullif(array_to_string(tsvector_to_array(to_tsvector('german'::regconfig,p_query_text)),' | '),''),'''''')) q),
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

-- Capacity for small embedding batches, still bounded and reserved before calls.
alter table public.wm_model_calls drop constraint wm_model_calls_call_index_check;
alter table public.wm_model_calls add constraint wm_model_calls_call_index_check check(call_index between 0 and 1023);
do $$ declare definition text; begin
 select pg_get_functiondef(oid) into definition from pg_proc where pronamespace='public'::regnamespace and proname='wm_reserve_call';
 if definition not like '%p_call_index>31%' and definition not like '%p_call_index > 31%' then raise exception 'Unexpected reserve function version'; end if;
 execute replace(replace(definition,'p_call_index>31','p_call_index>1023'),'p_call_index > 31','p_call_index > 1023');
 select pg_get_functiondef(oid) into definition from pg_proc where pronamespace='public'::regnamespace and proname='wm_job_detail';
 if definition not like '%''index'',c.call_index%' then raise exception 'Unexpected job detail function version'; end if;
 execute replace(definition,'''index'',c.call_index','''index'',c.call_index,''request_hash'',c.request_hash');
end $$;

do $$ declare f record; begin
 for f in select oid::regprocedure signature from pg_proc where pronamespace='public'::regnamespace and proname like 'wm_search_%' loop
  execute format('revoke all on function %s from public,anon,authenticated',f.signature);
  execute format('grant execute on function %s to service_role',f.signature);
 end loop;
end $$;
