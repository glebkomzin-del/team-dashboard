set work_mem='2MB'; set max_parallel_workers_per_gather=0; set statement_timeout='180s';
select (SELECT json_build_object(
 'tables', (SELECT json_object_agg(format('%I.%I',n.nspname,c.relname),
   (xpath('/row/n/text()',query_to_xml(format('select count(*) as n from %I.%I',n.nspname,c.relname),false,true,'')))[1]::text::bigint)
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relkind IN ('r','p') AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
   AND NOT EXISTS (SELECT 1 FROM pg_depend d JOIN pg_extension e ON e.oid=d.refobjid
     WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e'
       AND NOT c.oid=ANY(coalesce(e.extconfig,ARRAY[]::oid[])))),
 'auth_users', (SELECT md5(coalesce(string_agg(md5(to_jsonb(u)::text),'' ORDER BY id),'')) FROM auth.users u),
 'vault', (SELECT md5(coalesce(string_agg(id::text||md5(decrypted_secret),'' ORDER BY id),'')) FROM vault.decrypted_secrets),
 'roles', (SELECT json_object_agg(rolname,json_build_array(rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls,md5(rolpassword)))
   FROM pg_authid WHERE rolname NOT LIKE 'pg_%')))::jsonb || jsonb_build_object('row_integrity_method','sha256-fullrow-jsonb-text-utf8-rowhash-newline-aggregate-v2','row_integrity',jsonb_build_object('wm_archive_documents',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_archive_documents t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_archive_notes',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_archive_notes t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_source_versions',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_source_versions t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_journal',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_journal t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_model_calls',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_model_calls t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_question_calls',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_question_calls t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_jobs',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_jobs t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_job_isolations',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_job_isolations t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_generation_reviews',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_generation_reviews t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_job_decisions',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_job_decisions t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_source_deletions',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_source_deletions t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_source_deletion_versions',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_source_deletion_versions t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_source_deletion_checks',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_source_deletion_checks t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_source_deletion_plan',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_source_deletion_plan t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_source_reimport_authorizations',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_source_reimport_authorizations t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes),'wm_processing_config',(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.wm_processing_config t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes)),'functions47_49',(select jsonb_object_agg(p.oid::regprocedure::text,jsonb_build_object(
      'definition_sha256',encode(extensions.digest(convert_to(pg_get_functiondef(p.oid),'UTF8'),'sha256'),'hex'),
      'definition_md5',md5(pg_get_functiondef(p.oid)),
      'acl',p.proacl,'security_definer',p.prosecdef,'config',p.proconfig,
      'service_execute',has_function_privilege('service_role',p.oid,'EXECUTE'),
      'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),
      'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),
      'sql49_status_materialized',case when p.oid='public.wm_processing_status(uuid)'::regprocedure
        then position('STATUS_ISOLATIONS AS MATERIALIZED' in upper(pg_get_functiondef(p.oid)))>0
        else null end)) from pg_proc p where p.oid in ('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure,'public.wm_processing_status(uuid)'::regprocedure,'public.wm_job_isolation_valid(uuid,text)'::regprocedure)));