"""One approved final run of the existing backup; never modify installed files.

This file is prepared only. Execution requires the Lead's explicit start message.
"""
import argparse
import fcntl
import hashlib
import importlib
import json
import pathlib
import sys

ROOT = pathlib.Path('/opt/dashboard-memory-canonical-draft')
INSTALLED_SHA = '954e5f163387952b6b7074e5ec3d6938cd9fbedc0473044f3fecd5d8c56d29ec'
MANIFEST_SHA = 'e8e50bea00f5ba529e797e699307bb43b12110f2c27b2107f6c9eccb86c2044f'
P2_IMAGE = 'sha256:b71191a2b8d9f68cae700915ea119ded9c7bccc4c09fe9dc9f5c38dbd04e8cbe'
TABLES = ('wm_archive_documents', 'wm_archive_notes', 'wm_source_versions', 'wm_journal', 'wm_model_calls', 'wm_question_calls',
          'wm_jobs', 'wm_job_isolations', 'wm_generation_reviews', 'wm_job_decisions',
          'wm_source_deletions', 'wm_source_deletion_versions', 'wm_source_deletion_checks',
          'wm_source_deletion_plan', 'wm_source_reimport_authorizations', 'wm_processing_config')
FUNCTIONS = ('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)',
             'public.wm_processing_status(uuid)', 'public.wm_job_isolation_valid(uuid,text)')


def enriched_sql(original):
    # Same bounded full-row SHA/newline method as capture-inventory.sql schema2;
    # aggregate only fixed-size SHA strings, never all JSON rows at once.
    pairs = []
    for table in TABLES:
        body = """(with row_hashes as materialized (
          select encode(extensions.digest(convert_to(to_jsonb(t)::text,'UTF8'),'sha256'),'hex') row_hash
          from public.%s t)
          select jsonb_build_object('rows',count(*),'sha256',encode(extensions.digest(
            convert_to(coalesce(string_agg(row_hash,E'\\n' order by row_hash COLLATE "C"),''),'UTF8'),
            'sha256'),'hex')) from row_hashes)""" % table
        pairs.extend(["'%s'" % table, body])
    signatures = ','.join("'%s'::regprocedure" % value for value in FUNCTIONS)
    functions = """(select jsonb_object_agg(p.oid::regprocedure::text,jsonb_build_object(
      'definition_sha256',encode(extensions.digest(convert_to(pg_get_functiondef(p.oid),'UTF8'),'sha256'),'hex'),
      'definition_md5',md5(pg_get_functiondef(p.oid)),
      'acl',p.proacl,'security_definer',p.prosecdef,'config',p.proconfig,
      'service_execute',has_function_privilege('service_role',p.oid,'EXECUTE'),
      'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),
      'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),
      'sql49_status_materialized',case when p.oid='public.wm_processing_status(uuid)'::regprocedure
        then position('STATUS_ISOLATIONS AS MATERIALIZED' in upper(pg_get_functiondef(p.oid)))>0
        else null end)) from pg_proc p where p.oid in (%s))""" % signatures
    # No quiescence, unknown-provider or processing-enabled acceptance assertions:
    # these fields are faithfully captured, not interpreted as maintenance gates.
    return ("set work_mem='2MB'; set max_parallel_workers_per_gather=0; set statement_timeout='180s';\n"
            "select (" + original.strip().rstrip(';') + ")::jsonb || jsonb_build_object("
            "'row_integrity_method','sha256-fullrow-jsonb-text-utf8-rowhash-newline-aggregate-v2',"
            "'row_integrity',jsonb_build_object(" + ','.join(pairs) + "),'functions47_49'," + functions + ");")


def prepare(module):
    module.SELFHOST_FINGERPRINT_SQL = enriched_sql(module.SELFHOST_FINGERPRINT_SQL)
    original_run = module.run
    original_restore = module.selfhost_restore

    def evidenced_restore(folder, database, expected):
        assert set(expected['row_integrity']) == set(TABLES)
        assert len(expected['functions47_49']) == len(FUNCTIONS)
        assert expected['row_integrity_method'] == 'sha256-fullrow-jsonb-text-utf8-rowhash-newline-aggregate-v2'
        # Existing restore returns only after actual == expected for the entire
        # augmented snapshot JSON, including every full-row digest and function.
        receipt = original_restore(folder, database, expected)
        return {**receipt, 'fullrow_integrity_verified': True,
                'fullrow_tables_verified': list(TABLES), 'functions47_49_verified': True,
                'fingerprint_sql_sha256': hashlib.sha256(module.SELFHOST_FINGERPRINT_SQL.encode()).hexdigest()}

    def isolated_memory(args, **kwargs):
        args = list(args)
        if (args[:2] == ['docker', 'run'] and '--name' in args
                and args[args.index('--name') + 1].startswith('dashboard-selfhost-restore-')):
            assert '--network' in args and args[args.index('--network') + 1] == 'none'
            assert '--memory=1g' in args
            args[args.index('--memory=1g')] = '--memory=2g'
        return original_run(args, **kwargs)

    module.run = isolated_memory
    module.selfhost_restore = evidenced_restore
    module.prune = lambda now: None  # Explicit mandate: retain every existing backup.
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-approved-final-backup', action='store_true')
    args = parser.parse_args()
    assert hashlib.sha256((ROOT / 'scheduled_backup.py').read_bytes()).hexdigest() == INSTALLED_SHA
    assert hashlib.sha256((ROOT / 'build-manifest.json').read_bytes()).hexdigest() == MANIFEST_SHA
    sys.path.insert(0, str(ROOT))
    module = prepare(importlib.import_module('scheduled_backup'))
    assert module.container('dashboard-memory-canonical-draft-canonical-draft-1')['Image'] == P2_IMAGE
    database = module.container(module.SELFHOST_CONTAINER)
    assert database['HostConfig']['Memory'] == 2147483648
    assert database['HostConfig']['MemorySwap'] == 2147483648
    contract = json.loads(module.selfhost_psql(database['Id'], """select json_build_object(
      'function47_md5',md5(pg_get_functiondef('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure)),
      'function49_md5',md5(pg_get_functiondef('public.wm_processing_status(uuid)'::regprocedure)),
      'service_execute',has_function_privilege('service_role','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE'),
      'anon_execute',has_function_privilege('anon','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE'),
      'authenticated_execute',has_function_privilege('authenticated','public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)','EXECUTE'))"""))
    assert contract == {'function47_md5': '52e542324b17616d1f912cb0f3ef14f7',
                        'function49_md5': '009bedd05991c6eaf46a5cbc1ca72717',
                        'service_execute': True, 'anon_execute': False, 'authenticated_execute': False}
    if not args.execute_approved_final_backup:
        print(json.dumps({'result': 'PREPARED_NOT_EXECUTED', 'installed_sha256': INSTALLED_SHA,
                          'fingerprint_sql_sha256': hashlib.sha256(module.SELFHOST_FINGERPRINT_SQL.encode()).hexdigest(),
                          'fullrow_tables': list(TABLES), 'functions': list(FUNCTIONS),
                          'restored_memory_bytes': 2147483648, 'prune_disabled_for_this_run': True}))
        return
    with open('/run/lock/dashboard-job-backup.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = module.backup()
    print(json.dumps({key: result[key] for key in ('state', 'archive', 'bytes', 'sha256', 'selfhost', 'n8n')}))


if __name__ == '__main__':
    main()
