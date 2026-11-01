begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
insert into auth.users(id) values('f1111111-1111-4111-8111-111111111112');
insert into public.wm_spaces(id,owner_id,label)
values('f2222222-2222-4222-8222-222222222223','f1111111-1111-4111-8111-111111111112','Lexical candidate fixture');
set local role service_role;
insert into public.wm_search_documents(space_id,id,kind,target_id,source_id,source_version,event_date,observed_at,body,metadata,content_hash,embedding_model,embedding)
select 'f2222222-2222-4222-8222-222222222223',lpad(i::text,64,'0'),
case when i%2=0 then 'knowledge' else 'passage' end,'target-'||i,'source-'||i,'v1','2026-09-20',null,
case when i>100 then 'projekt projekt projekt projekt' else 'projekt' end,
'{}'::jsonb,lpad(to_hex(i),64,'0'),'text-embedding-3-small',
array_prepend(i::real,array_fill(1::real,array[1535]))::extensions.vector
from generate_series(1,140) i;
insert into public.wm_search_snapshots(space_id,id,document_ids)
select 'f2222222-2222-4222-8222-222222222223',repeat('b',64),array_agg(lpad(i::text,64,'0') order by i)
from generate_series(1,100) i;
set local statement_timeout='5s';
do $$
declare r jsonb; repeated jsonb;
begin
r:=public.wm_search_query('f2222222-2222-4222-8222-222222222223',repeat('b',64),'projekt',
array_prepend(1::real,array_fill(1::real,array[1535]))::extensions.vector,array['knowledge'],20);
perform pg_temp.expect(jsonb_array_length(r)=20,'requested result count');
perform pg_temp.expect(not exists(select 1 from jsonb_array_elements(r) h
where h->>'kind'<>'knowledge' or (h->>'target_id')::text !~ '^target-[0-9]+$'
or substring(h->>'target_id' from 8)::integer>100),'kind and pinned snapshot enforced before limiting');
perform pg_temp.expect((select array_agg(h->>'target_id' order by substring(h->>'target_id' from 8)::integer) from jsonb_array_elements(r) h)
=(select array_agg('target-'||i order by i) from generate_series(2,40,2) i),'lexical rank and exact vector ranking preserved');
repeated:=public.wm_search_query('f2222222-2222-4222-8222-222222222223',repeat('b',64),'projekt',
array_prepend(1::real,array_fill(1::real,array[1535]))::extensions.vector,array['knowledge'],20);
perform pg_temp.expect(repeated=r and (select count(*) from public.wm_search_results
where space_id='f2222222-2222-4222-8222-222222222223')=1,'same cache identity reuses receipt');
end $$;
reset role;
rollback;
