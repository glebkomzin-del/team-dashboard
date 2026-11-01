import json
from pathlib import Path
from memory import connect
from generation_review import compile_generation
from test_generation_review import entry,TEXT
from canonical_restore import sql_json
p=connect(':memory:');first=entry(p,'synthetic:generation',day='2026-09-07');p.close()
g1=compile_generation([], [first],source_reviews={'synthetic:generation':'Synthetisches geprüftes Original'},identity_links=[],reason='Synthetische Freigabe')
p=connect(':memory:');second=entry(p,'synthetic:generation',TEXT+'\nZusätzlicher Originaltext.',day='2026-09-07');p.close()
g2=compile_generation([first],[second],source_reviews={'synthetic:generation':'Geänderte synthetische Originalfassung'},identity_links=[],reason='Synthetischer Abgleich')
head='''begin;
create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$ begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end; $$;
create function pg_temp.doc(s uuid,source jsonb) returns text language plpgsql as $$
declare m text; identifier text;
begin
 m:=jsonb_build_object('source_id',source->>'source_id','event_date',source->>'event_date','title',source->>'title','body_sha256',source->>'content_hash','export_sha256',source->>'content_hash','body_offset_characters',0)::text;
 identifier:=encode(extensions.digest(convert_to((source->>'source_id')||':'||m,'UTF8'),'sha256'),'hex');
 perform public.wm_archive_put(s,jsonb_build_object('id',identifier,'source_id',source->>'source_id','event_date',source->>'event_date','title',source->>'title','observed_at',source->>'observed_at','body_hash',source->>'content_hash','export_hash',source->>'content_hash','body',source->>'transcript','export',source->>'transcript','metadata_json',m));
 return identifier;
end; $$;
create temp table generation_fixture(id integer,payload jsonb);
grant select on generation_fixture to service_role;
'''
head+='insert into generation_fixture values (1,'+sql_json(g1)+'),(2,'+sql_json(g2)+');\n'
body='''
insert into auth.users(id) values('55555555-5555-4555-8555-555555555555');
insert into public.wm_spaces(id,owner_id,label) values('66666666-6666-4666-8666-666666666666','55555555-5555-4555-8555-555555555555','Synthetic generation');
insert into public.wm_processing_config(space_id,enabled,automatic_from,pipeline,budget_micro_usd) values('66666666-6666-4666-8666-666666666666',true,'2026-09-07','test-v1',1000000);
set local role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; owner uuid:='55555555-5555-4555-8555-555555555555';
 p1 jsonb; p2 jsonb; bad jsonb; d text; j jsonb; lease uuid:=gen_random_uuid(); rid uuid:=gen_random_uuid(); rid2 uuid:=gen_random_uuid(); cmd uuid:=gen_random_uuid(); cmd2 uuid:=gen_random_uuid(); snap uuid:=gen_random_uuid(); result jsonb;
begin
 select payload into p1 from generation_fixture where id=1;select payload into p2 from generation_fixture where id=2;
 d:=pg_temp.doc(s,p1->'new_sources'->0);
 j:=public.wm_enqueue(s,d,'test-v1');j:=public.wm_claim_job(s,'test-v1',lease);
 perform public.wm_reserve_call(s,j->>'id',lease,0,'{"model":"synthetic"}',500000);
 perform public.wm_pause_job(s,j->>'id',lease,'provider_outcome_unknown');
 result:=public.wm_generation_stage(s,rid,0,'Synthetic review',p1,j->>'id');
 perform pg_temp.expect(result->>'state'='pending','draft staged without journal mutation');
 perform pg_temp.expect((select revision=0 from public.wm_spaces where id=s),'stage does not publish');
 perform pg_temp.expect((public.wm_generation_stage(s,rid,0,'Synthetic review',p1,j->>'id')->>'repeated')::boolean,'stage retry identity');
 begin
  perform public.wm_generation_stage(s,rid,0,'Changed label',p1,j->>'id');raise exception 'Changed stage identity reused';
 exception when unique_violation then null;end;
 bad:=jsonb_set(p2,'{new_sources,0,content_hash}',to_jsonb(repeat('0',64)));
 begin
  perform public.wm_generation_stage(s,gen_random_uuid(),0,'Bad original',bad);raise exception 'Forged original staged';
 exception when invalid_parameter_value then null;end;
 begin
  perform public.wm_generation_decide(s,rid,gen_random_uuid(),cmd,0,p1->>'review_sha256','accept','Wrong owner');raise exception 'Wrong owner accepted generation';
 exception when insufficient_privilege then null;end;
 begin
  perform public.wm_generation_decide(s,rid,owner,cmd,0,repeat('0',64),'accept','Wrong preview');raise exception 'Changed preview accepted';
 exception when serialization_failure then null;end;
 perform public.wm_backup_begin(s,snap);
 perform pg_temp.expect(exists(select 1 from public.wm_backup_records where snapshot_id=snap and kind='generation_review' and record_json::jsonb->>'state'='pending'),'snapshot contains pending review');
 result:=public.wm_generation_decide(s,rid,owner,cmd,0,p1->>'review_sha256','accept','Alle Änderungen am Original geprüft');
 perform pg_temp.expect(result->>'state'='accepted' and (result->>'revision')::integer=1,'one atomic accepted revision');
 perform pg_temp.expect((select count(*)=1 from public.wm_journal where space_id=s and kind='generation'),'one immutable generation entry');
 perform pg_temp.expect((select count(*)=1 from public.wm_source_versions where space_id=s),'new pinned source stored');
 perform pg_temp.expect(public.wm_job_detail(s,j->>'id')->'job'->>'state'='applied','reviewed job applied in same transaction');
 perform pg_temp.expect((public.wm_processing_status(s)->>'accounted_micro_usd')::bigint=500000,'unknown paid reservation retained');
 perform pg_temp.expect((public.wm_generation_decide(s,rid,owner,cmd,0,p1->>'review_sha256','accept','Alle Änderungen am Original geprüft')->>'repeated')::boolean,'lost acceptance acknowledgement repeats');
 begin
  perform public.wm_generation_decide(s,rid,owner,cmd,0,p1->>'review_sha256','accept','Different reason');raise exception 'Changed acceptance reused';
 exception when unique_violation then null;end;
 perform public.wm_receive_call(s,j->>'id',lease,0,'{"saved":"complete late response"}',12345);
 perform pg_temp.expect((public.wm_processing_status(s)->>'accounted_micro_usd')::bigint=12345,'late response settles cost after acceptance');
 perform pg_temp.expect(public.wm_job_detail(s,j->>'id')->'job'->>'state'='applied','late response cannot revive source processing');
 perform pg_temp.expect(exists(select 1 from public.wm_backup_records where snapshot_id=snap and kind='generation_review' and record_json::jsonb->>'state'='pending'),'snapshot remains pinned despite decision');
 perform public.wm_backup_release(s,snap);
 d:=pg_temp.doc(s,p2->'new_sources'->0);
 perform public.wm_generation_stage(s,rid2,1,'Second review',p2);
 perform public.wm_append(s,1,gen_random_uuid(),'human','{"action":"correct","target_id":"synthetic","reason":"Concurrent personal correction","patch":{"title":"Changed"},"event_date":"2026-09-07"}'::jsonb,null,owner);
 begin
  perform public.wm_generation_decide(s,rid2,owner,cmd2,1,p2->>'review_sha256','accept','Stale view');raise exception 'Stale generation accepted';
 exception when serialization_failure then null;end;
 perform pg_temp.expect((select count(*)=1 from public.wm_source_versions where space_id=s),'failed acceptance inserts no source');
 result:=public.wm_generation_decide(s,rid2,owner,cmd2,1,p2->>'review_sha256','reject','Veralteten Prüfstand verwerfen');
 perform pg_temp.expect(result->>'state'='rejected' and (result->>'revision')::integer=2,'stale draft can be explicitly rejected without changing memory');
 perform pg_temp.expect((public.wm_generation_decide(s,rid2,owner,cmd2,1,p2->>'review_sha256','reject','Veralteten Prüfstand verwerfen')->>'repeated')::boolean,'reject retry identity');
 perform pg_temp.expect((select count(*)=2 from public.wm_generation_reviews where space_id=s),'both decisions retained');
end; $$;
reset role;
set local role authenticated;
do $$ begin
 begin
  perform public.wm_generation_stage('66666666-6666-4666-8666-666666666666',gen_random_uuid(),0,'Bypass','{}'::jsonb);raise exception 'Browser bypassed staging boundary';
 exception when insufficient_privilege then null;end;
 begin
  perform public.wm_generation_decide('66666666-6666-4666-8666-666666666666',gen_random_uuid(),'55555555-5555-4555-8555-555555555555',gen_random_uuid(),0,repeat('a',64),'accept','Bypass');raise exception 'Browser bypassed decision boundary';
 exception when insufficient_privilege then null;end;
end; $$;
reset role;
rollback;
'''
Path('test_generation_reviews.sql').write_text(head+body)
