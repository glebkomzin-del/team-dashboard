-- Run only against a disposable PostgreSQL 17 database with no production data.
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create table public.wm_spaces(id uuid primary key,state text,revision bigint);
create table public.wm_processing_config(space_id uuid primary key,enabled boolean,pipeline text,automatic_from date);
create table public.wm_jobs(space_id uuid,id text,document_id text,source_id text,event_date date,
 pipeline text,state text,reason text,expected_revision bigint,lease_token uuid,lease_until timestamptz,
 prepared_payload jsonb,redaction_id uuid,updated_at timestamptz,primary key(space_id,id));
create table public.wm_archive_documents(space_id uuid,id text,source_id text,body_hash text,body text,
 redaction_id uuid,primary key(space_id,id));
create table public.wm_model_calls(space_id uuid,job_id text);
create table public.wm_source_versions(space_id uuid,source_id text);
grant usage on schema public,extensions to service_role;
grant all on all tables in schema public to service_role;

\ir supabase/migrations/20261005133858_archive_verified_image_placeholder_job.sql

create function pg_temp.expect(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAILED: %',label; end if; end $$;
create function pg_temp.add_job(label text,body text) returns text language plpgsql as $$
declare s uuid:='66666666-6666-4666-8666-666666666666'; source text:='synthetic:'||label;
 h text; id text; doc text;
begin
 h:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 id:=encode(extensions.digest(convert_to(source||':'||h,'UTF8'),'sha256'),'hex');
 doc:=encode(extensions.digest(convert_to(label||':document','UTF8'),'sha256'),'hex');
 insert into public.wm_archive_documents values(s,doc,source,h,body,null);
 insert into public.wm_jobs values(s,id,doc,source,'2026-09-23','test-v1','running',null,0,
  '11111111-1111-4111-8111-111111111111',clock_timestamp()+interval '10 minutes',null,null,clock_timestamp());
 return id;
end $$;
insert into public.wm_spaces values('66666666-6666-4666-8666-666666666666','draft',0);
insert into public.wm_processing_config values('66666666-6666-4666-8666-666666666666',true,'test-v1','2026-09-08');

set role service_role;
do $$
declare s uuid:='66666666-6666-4666-8666-666666666666';
 lease uuid:='11111111-1111-4111-8111-111111111111';
 header text:=E'Meeting Titel: Beispiel\nTeilnehmer: \nDatum: 2026-09-23\nBeginn: 2026-09-23 10:35:55\n';
 body text; job_key text; h text; result jsonb; label text; first_update timestamptz;
begin
 foreach label in array array['image','Bild'] loop
  body:=header||'[10:35:55] Unknown: '||label||E'\n';
  job_key:=pg_temp.add_job('positive-'||label,body);
  h:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
  result:=public.wm_archive_image_placeholder_job(s,job_key,lease,h);
  perform pg_temp.expect(result->>'state'='archived' and result->>'reason'='verified_image_placeholder','known image marker archives');
  perform pg_temp.expect((select d.body from public.wm_archive_documents d where d.space_id=s and d.source_id='synthetic:positive-'||label)=body,'original retained');
  perform pg_temp.expect((select count(*) from public.wm_model_calls where space_id=s and job_id=job_key)=0,'no provider call');
  select j.updated_at into first_update from public.wm_jobs j where j.space_id=s and j.id=job_key;
  begin
   perform public.wm_archive_image_placeholder_job(s,job_key,lease,h);
   raise exception 'FAILED: repeat archive succeeded';
  exception when serialization_failure then null; end;
  perform pg_temp.expect((select j.updated_at from public.wm_jobs j where j.space_id=s and j.id=job_key)=first_update,'repeat makes no second state transition');
 end loop;
end $$;

do $$
declare s uuid:='66666666-6666-4666-8666-666666666666';
 lease uuid:='11111111-1111-4111-8111-111111111111';
 header text:=E'Meeting Titel: Beispiel\nTeilnehmer: \nDatum: 2026-09-23\nBeginn: 2026-09-23 10:35:55\n';
 body text; job_key text; h text; label text; cases text[]:=array[
  '[10:35:55] Alex: Ja.',
  E'[10:35:55] Unknown: image\n[10:35:56] Alex: Ja.',
  '[10:35:55] Unknown: Moin',
  '[10:35:55] Unknown: Mo Di Mi Do Fr Sa So',
  '[10:35:55] Unknown: output.png',
  '[10:35:55] Unknown: unbekannt'];
begin
 for n in 1..array_length(cases,1) loop
  label:='negative-'||n;
  body:=header||cases[n]||E'\n';
  job_key:=pg_temp.add_job(label,body);
  h:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
  begin
   perform public.wm_archive_image_placeholder_job(s,job_key,lease,h);
   raise exception 'FAILED: non-placeholder archived %',label;
  exception when serialization_failure then null; end;
  perform pg_temp.expect((select j.state from public.wm_jobs j where j.space_id=s and j.id=job_key)='running','unknown or spoken original remains running');
 end loop;
 body:=header||E'[10:35:55] Unknown: image\n';
 job_key:=pg_temp.add_job('changed-hash',body);
 h:=encode(extensions.digest(convert_to(body,'UTF8'),'sha256'),'hex');
 begin
  perform public.wm_archive_image_placeholder_job(s,job_key,lease,repeat('0',64));
  raise exception 'FAILED: changed hash archived';
 exception when serialization_failure then null; end;
 update public.wm_jobs j set state='review' where j.space_id=s and j.id=job_key;
 begin
  perform public.wm_archive_image_placeholder_job(s,job_key,lease,h);
  raise exception 'FAILED: changed state archived';
 exception when serialization_failure then null; end;
 job_key:=pg_temp.add_job('paid',body);
 insert into public.wm_model_calls values(s,job_key);
 begin
  perform public.wm_archive_image_placeholder_job(s,job_key,lease,h);
  raise exception 'FAILED: paid job archived';
 exception when serialization_failure then null; end;
 perform pg_temp.expect((select j.state from public.wm_jobs j where j.space_id=s and j.id=job_key)='running','paid job retained');
 foreach label in array array['null-lease','expired-lease','wrong-lease','null-token',
    'null-hash-argument','null-stored-hash','null-body','missing-document-link',
    'null-expected-revision','source-mismatch','redacted'] loop
  job_key:=pg_temp.add_job(label,body);
  if label='null-lease' then
   update public.wm_jobs j set lease_until=null where j.space_id=s and j.id=job_key;
  elsif label='expired-lease' then
   update public.wm_jobs j set lease_until=clock_timestamp()-interval '1 second' where j.space_id=s and j.id=job_key;
  elsif label='redacted' then
   update public.wm_archive_documents d set redaction_id=gen_random_uuid() where d.space_id=s and d.source_id='synthetic:'||label;
  elsif label='null-token' then
   update public.wm_jobs j set lease_token=null where j.space_id=s and j.id=job_key;
  elsif label='null-stored-hash' then
   update public.wm_archive_documents d set body_hash=null where d.space_id=s and d.source_id='synthetic:'||label;
  elsif label='null-body' then
   update public.wm_archive_documents d set body=null where d.space_id=s and d.source_id='synthetic:'||label;
  elsif label='missing-document-link' then
   update public.wm_jobs j set document_id=null where j.space_id=s and j.id=job_key;
  elsif label='null-expected-revision' then
   update public.wm_jobs j set expected_revision=null where j.space_id=s and j.id=job_key;
  elsif label='source-mismatch' then
   update public.wm_archive_documents d set source_id='synthetic:other' where d.space_id=s and d.source_id='synthetic:'||label;
  end if;
  begin
   perform public.wm_archive_image_placeholder_job(s,job_key,
    case when label='wrong-lease' then gen_random_uuid() when label='null-token' then null else lease end,
    case when label='null-hash-argument' then null else h end);
   raise exception 'FAILED: invalid lease or redacted original archived %',label;
  exception when serialization_failure then null; end;
  perform pg_temp.expect((select j.state from public.wm_jobs j where j.space_id=s and j.id=job_key)='running','invalid lease/redacted remains running');
 end loop;
 job_key:=pg_temp.add_job('null-space-revision',body);
 update public.wm_spaces set revision=null where id=s;
 begin
  perform public.wm_archive_image_placeholder_job(s,job_key,lease,h);
  raise exception 'FAILED: unknown space revision archived';
 exception when serialization_failure then null; end;
 update public.wm_spaces set revision=0 where id=s;
 job_key:=pg_temp.add_job('null-policy-date',body);
 update public.wm_processing_config set automatic_from=null where space_id=s;
 begin
  perform public.wm_archive_image_placeholder_job(s,job_key,lease,h);
  raise exception 'FAILED: unknown processing policy archived';
 exception when serialization_failure then null; end;
 update public.wm_processing_config set automatic_from='2026-09-08' where space_id=s;
end $$;

reset role;
set role anon;
do $$ begin
 begin
  perform public.wm_archive_image_placeholder_job('66666666-6666-4666-8666-666666666666','x',gen_random_uuid(),'x');
  raise exception 'FAILED: anon may execute archive';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
