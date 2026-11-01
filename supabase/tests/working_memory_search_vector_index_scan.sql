begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.plan(query text) returns setof text language plpgsql as $$
begin return query execute 'explain (costs off) '||query; end; $$;

insert into auth.users(id) values('f1111111-1111-4111-8111-111111111113');
insert into public.wm_spaces(id,owner_id,label)
 values('f2222222-2222-4222-8222-222222222224','f1111111-1111-4111-8111-111111111113','Vector index fixture');

set local role service_role;
insert into public.wm_search_documents(space_id,id,kind,target_id,source_id,source_version,event_date,observed_at,body,metadata,content_hash,embedding_model,embedding)
select 'f2222222-2222-4222-8222-222222222224',lpad(to_hex(i),64,'0'),
 (array['work','knowledge','passage','summary','feedback'])[1+(i%5)],
 'target-'||i,'source-'||i,'v1','2026-09-20',null,'synthetic vector fixture',
 '{}'::jsonb,lpad(to_hex(i),64,'0'),'text-embedding-3-small',
 array_prepend(1::real,array_prepend((i/10000.0)::real,array_fill(0::real,array[1534])))::extensions.vector
from generate_series(1,3001) i;
insert into public.wm_search_snapshots(space_id,id,document_ids)
select 'f2222222-2222-4222-8222-222222222224',repeat('c',64),array_agg(lpad(to_hex(i),64,'0') order by i)
from generate_series(2001,3001) i;
insert into public.wm_search_snapshots(space_id,id,document_ids)
select 'f2222222-2222-4222-8222-222222222224',repeat('d',64),array_agg(lpad(to_hex(i),64,'0') order by i)
from generate_series(2001,3000) i;

set local statement_timeout='15s';
set local enable_sort=off;
do $$
declare s uuid:='f2222222-2222-4222-8222-222222222224'; large_snapshot text:=repeat('c',64);
 small_snapshot text:=repeat('d',64); q extensions.vector:=array_prepend(1::real,array_fill(0::real,array[1535]))::extensions.vector;
 all_result jsonb; repeated jsonb; kind_result jsonb; exact_result jsonb; definition text; plan text;
begin
 select string_agg(line,E'\n') into plan from pg_temp.plan($plan$
  select d.id,d.embedding operator(extensions.<=>) array_prepend(1::real,array_fill(0::real,array[1535]))::extensions.vector distance
  from public.wm_search_documents d
  where d.space_id='f2222222-2222-4222-8222-222222222224'
   and d.kind=any(array['work','knowledge','passage','summary','feedback'])
   and array_position((select document_ids from public.wm_search_snapshots
    where space_id='f2222222-2222-4222-8222-222222222224' and id=repeat('c',64)),d.id) is not null
  order by d.embedding operator(extensions.<=>) array_prepend(1::real,array_fill(0::real,array[1535]))::extensions.vector limit 20
 $plan$) line;
 perform pg_temp.expect(plan like '%Index Scan using wm_search_vector%' and plan not like '%wm_search_documents_pkey%',
  'large filtered vector branch uses HNSW instead of primary-key full ranking');

 all_result:=public.wm_search_query(s,large_snapshot,'zzznomatch',q,array['work','knowledge','passage','summary','feedback'],20);
 perform pg_temp.expect(jsonb_array_length(all_result)=20,'iterative HNSW fills the requested limit for a sparse large snapshot');
 perform pg_temp.expect(not exists(select 1 from jsonb_array_elements(all_result) hit
  where substring(hit->>'target_id' from 8)::integer<2001 or substring(hit->>'target_id' from 8)::integer>3001),
  'large ANN results stay inside the pinned snapshot');

 kind_result:=public.wm_search_query(s,large_snapshot,'zzznomatch',q,array['knowledge'],20);
 perform pg_temp.expect(jsonb_array_length(kind_result)=20 and not exists(
  select 1 from jsonb_array_elements(kind_result) hit where hit->>'kind'<>'knowledge'),
  'large ANN results retain the requested kinds filter');

 exact_result:=public.wm_search_query(s,small_snapshot,'zzznomatch',q,array['knowledge'],20);
 perform pg_temp.expect(jsonb_array_length(exact_result)=20,'exact threshold path returns the requested limit');
 perform pg_temp.expect((select array_agg(hit->>'target_id' order by (hit->>'vector_rank')::integer) from jsonb_array_elements(exact_result) hit)
  =(select array_agg('target-'||i order by i) from generate_series(2001,2096,5) i),
  'snapshots at 1000 members retain exact vector ranking');

 repeated:=public.wm_search_query(s,large_snapshot,'zzznomatch',q,array['work','knowledge','passage','summary','feedback'],20);
 perform pg_temp.expect(repeated=all_result and (select count(*) from public.wm_search_results
  where space_id=s and snapshot_id=large_snapshot)=2,
  'unchanged cache identity reuses results and still separates kinds');
 definition:=pg_get_functiondef('public.wm_search_query(uuid,text,text,extensions.vector,text[],integer)'::regprocedure);
 perform pg_temp.expect(position('hnsw-plan-v2' in definition)>0,'cache hash namespace remains unchanged');
 perform pg_temp.expect(position('cardinality(ids)<=1000' in definition)>0 and position('array_position(ids,d.id) is not null' in definition)>0,
  'exact threshold and HNSW snapshot filter remain explicit');
end $$;
reset role;
rollback;
