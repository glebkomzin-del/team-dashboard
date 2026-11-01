begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;

insert into auth.users(id) values('f1111111-1111-4111-8111-111111111111');
insert into public.wm_spaces(id,owner_id,label)
 values('f2222222-2222-4222-8222-222222222222','f1111111-1111-4111-8111-111111111111','Search work candidates');

set local role service_role;
do $$
declare s uuid:='f2222222-2222-4222-8222-222222222222'; ids text[]; snapshot text:=repeat('a',64);
begin
 select array_agg(lpad(i::text,64,'0') order by i) into ids from generate_series(1,1200) i;
 insert into public.wm_search_documents(space_id,id,kind,target_id,source_id,source_version,event_date,observed_at,body,metadata,content_hash,embedding_model,embedding)
 select s,lpad(i::text,64,'0'),'work','target-'||i,'source-'||i,'v1','2026-09-20',null,
   'alpha work candidate '||i,jsonb_build_object('fixture',true),lpad(to_hex(i),64,'0'),'text-embedding-3-small',
   array_prepend(i::real,array_fill(1::real,array[1535]))::extensions.vector
 from generate_series(1,1200) i;
 insert into public.wm_search_snapshots(space_id,id,document_ids) values(s,snapshot,ids);
end $$;

set local statement_timeout = '5s';
do $$
declare s uuid:='f2222222-2222-4222-8222-222222222222'; snapshot text:=repeat('a',64);
 result jsonb; repeated jsonb; definition text;
begin
 result:=public.wm_search_query(s,snapshot,'alpha',array_prepend(1::real,array_fill(1::real,array[1535]))::extensions.vector,array['work'],40);
 perform pg_temp.expect(jsonb_array_length(result)=40,'exact work search returns requested limit');
 perform pg_temp.expect(not exists(select 1 from jsonb_array_elements(result) hit where hit->>'kind'<>'work'),'exact work search retains work scope');
 perform pg_temp.expect((select array_agg(hit->>'id' order by hit->>'id') from jsonb_array_elements(result) hit)
   =(select array_agg(lpad(i::text,64,'0') order by lpad(i::text,64,'0')) from generate_series(1,40) i),'exact vector ranking retains the closest work candidates');
 repeated:=public.wm_search_query(s,snapshot,'alpha',array_prepend(1::real,array_fill(1::real,array[1535]))::extensions.vector,array['work'],40);
 perform pg_temp.expect(repeated=result and (select count(*) from public.wm_search_results where space_id=s and snapshot_id=snapshot)=1,
   'unchanged cache identity reuses the existing search result');
 definition:=pg_get_functiondef('public.wm_search_query(uuid,text,text,extensions.vector,text[],integer)'::regprocedure);
 perform pg_temp.expect(position('work_documents as materialized' in definition)>0 and position('work_members as materialized' in definition)>0,
   'work candidates are materialized before snapshot membership');
 perform pg_temp.expect(position('hnsw-plan-v2' in definition)>0,'cache hash namespace remains unchanged');
end $$;
reset role;
rollback;
