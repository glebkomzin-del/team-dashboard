"""Generate a verified, paused PostgreSQL restore; never connect to a database.

Targets an empty memory space with an existing Supabase owner. A single
transaction preserves exact journal/call identities and refuses overwrite.
Automation and the restored space remain disabled until an explicit cutover.
"""
import argparse,json,os,re
from pathlib import Path
from uuid import UUID
from canonical_backup import verify,FrozenStore,read_rows,private_json,checksum
from memory import ValidationError

TABLES=('wm_spaces','wm_source_versions','wm_archive_documents','wm_archive_notes',
        'wm_journal','wm_processing_config','wm_jobs','wm_pipeline_recoveries','wm_model_calls','wm_job_isolations','wm_job_decisions','wm_generation_reviews','wm_search_documents','wm_search_snapshots','wm_search_results','wm_conversations','wm_questions','wm_question_calls',
        'wm_source_deletions','wm_source_deletion_versions','wm_source_deletion_checks','wm_source_reimport_authorizations')
KINDS={'config':'wm_processing_config','job':'wm_jobs','call':'wm_model_calls','job_isolation':'wm_job_isolations','job_decision':'wm_job_decisions','generation_review':'wm_generation_reviews','search_document':'wm_search_documents','search_snapshot':'wm_search_snapshots','search_result':'wm_search_results','question':'wm_questions','question_call':'wm_question_calls',
       'source_deletion':'wm_source_deletions','source_deletion_version':'wm_source_deletion_versions','source_deletion_check':'wm_source_deletion_checks','source_reimport_authorization':'wm_source_reimport_authorizations','conversation':'wm_conversations','pipeline_recovery':'wm_pipeline_recoveries'}


def prepared_rows(folder,restore_ledger=None):
    proof=verify(folder);store=FrozenStore(folder);space=store.space()
    manifest=json.loads((Path(folder)/'manifest.json').read_text())
    if manifest.get('format')!='working-memory-backup-v2' or type(space.get('deletion_revision')) is not int:
        raise ValidationError('Restore refuses a backup without a deletion-ledger watermark')
    from deletion_ledger import read as read_deletion_ledger
    restore_ledger=restore_ledger or os.environ.get('MEMORY_RESTORE_DELETION_LEDGER')
    if not restore_ledger:raise ValidationError('A current external deletion ledger is required for restore')
    current_ledger=read_deletion_ledger(restore_ledger,space_id=space['id'])
    if space['deletion_revision']<current_ledger['minimum_deletion_revision']:
        raise ValidationError('Backup predates the current external deletion watermark')
    UUID(space['id']);UUID(space['owner_id'])
    rows={name:[] for name in TABLES}
    # These two explicit safety changes are the only changes to backed-up rows.
    rows['wm_spaces'].append({**space,'state':'draft'})
    for name,table in [('documents','wm_archive_documents'),('notes','wm_archive_notes')]:
        rows[table]=list(read_rows(Path(folder)/(name+'.jsonl')))
    source_rows={}
    def keep_source(source):
        source={**source,'space_id':space['id']}
        previous=source_rows.get(source['id'])
        if previous is not None and previous!=source:
            from datetime import datetime
            a={**previous,'observed_at':datetime.fromisoformat(previous['observed_at'].replace('Z','+00:00')).isoformat()}
            b={**source,'observed_at':datetime.fromisoformat(source['observed_at'].replace('Z','+00:00')).isoformat()}
            if a!=b:raise ValidationError('Conflicting source version in backup generations')
        else:source_rows[source['id']]=source
    for entry in store.entries():
        if not re.fullmatch('[0-9a-f]{64}',entry.get('request_hash','')):
            raise ValidationError('This backup lacks exact journal retry hashes; use a newer complete backup')
        source=entry.get('source')
        if source:keep_source(source)
        if entry['kind']=='generation':
            for new_source in entry['payload'].get('new_sources',[]):keep_source(new_source)
        rows['wm_journal'].append({'space_id':space['id'],**{k:v for k,v in entry.items() if k!='source'}})
    rows['wm_source_versions']=list(source_rows.values())
    for entry in read_rows(Path(folder)/'queue.jsonl'):
        value=json.loads(entry['record_json'])
        if entry['kind']=='config':value['enabled']=False
        rows[KINDS[entry['kind']]].append(value)
    for table,values in rows.items():
        for value in values:
            if (value.get('id') if table=='wm_spaces' else value.get('space_id'))!=space['id']:
                raise ValidationError('Restore contains a row from another space')
    return rows,proof


def sql_json(value):
    # Hex contains no SQL syntax. Quotes, backslashes, Unicode, psql meta-commands
    # and source text remain data even when deliberately malicious.
    raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode().hex()
    return "convert_from(decode('"+raw+"','hex'),'UTF8')::jsonb"


def generate(folder,target,*,restore_ledger=None,verification_only=False):
    rows,proof=prepared_rows(folder,restore_ledger);space=rows['wm_spaces'][0]
    owner=str(UUID(space['owner_id']));sid=str(UUID(space['id']))
    target=Path(target)
    with target.open('x') as stream:
        os.chmod(target,0o600)
        stream.write("-- Private backup restore. Existing owner required. Never overwrites a space.\n\\set ON_ERROR_STOP on\nBEGIN;\nSET LOCAL search_path='';\n")
        stream.write("DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM auth.users WHERE id='"+owner+"'::uuid) THEN RAISE EXCEPTION 'Restore owner does not exist'; END IF; IF EXISTS(SELECT 1 FROM public.wm_spaces WHERE id='"+sid+"'::uuid) THEN RAISE EXCEPTION 'Restore target already exists; overwrite refused'; END IF; END $$;\n")
        stream.write('CREATE TEMP TABLE wm_restore_expected(table_name text NOT NULL,row_json jsonb NOT NULL) ON COMMIT DROP;\n')
        for table in TABLES:
            for row in rows[table]:
                stream.write("INSERT INTO pg_temp.wm_restore_expected VALUES ('"+table+"',"+sql_json(row)+");\n")
            if table=='wm_search_documents':
                cols='space_id,id,kind,target_id,source_id,source_version,event_date,observed_at,body,metadata,content_hash,embedding_model,embedding'
                stream.write('INSERT INTO public.'+table+'('+cols+') SELECT '+','.join('r.'+c for c in cols.split(','))+' FROM pg_temp.wm_restore_expected e CROSS JOIN LATERAL jsonb_populate_record(NULL::public.'+table+",e.row_json) r WHERE e.table_name='"+table+"';\n")
            else:
                stream.write('INSERT INTO public.'+table+' SELECT (jsonb_populate_record(NULL::public.'+table+",row_json)).* FROM pg_temp.wm_restore_expected WHERE table_name='"+table+"';\n")
        stream.write('SET CONSTRAINTS ALL IMMEDIATE;\n')
        # Restore every historical audit byte-for-byte. Current skip authority
        # is checked independently by wm_job_isolation_valid at claim/publish.
        # Cast through the actual PostgreSQL type, so timestamp spelling and
        # numeric representation are compared according to database semantics.
        for table in TABLES:
            field='id' if table=='wm_spaces' else 'space_id'
            expected="SELECT to_jsonb(jsonb_populate_record(NULL::public."+table+",row_json)) AS data FROM pg_temp.wm_restore_expected WHERE table_name='"+table+"'"
            actual="SELECT to_jsonb(t) AS data FROM public."+table+" t WHERE "+field+"='"+sid+"'::uuid"
            if table=='wm_search_documents':
                expected=expected.replace(')) AS data',"))-'fts' AS data")
                actual=actual.replace('to_jsonb(t) AS data',"to_jsonb(t)-'fts' AS data")
            stream.write("DO $$ BEGIN IF EXISTS(("+expected+' EXCEPT ALL '+actual+') UNION ALL ('+actual+' EXCEPT ALL '+expected+")) THEN RAISE EXCEPTION 'Restore verification failed: "+table+"'; END IF; END $$;\n")
        stream.write('ROLLBACK;\n' if verification_only else 'COMMIT;\n')
        stream.flush();os.fsync(stream.fileno())
    receipt={**proof,'format':'working-memory-paused-restore-v1','sql_sha256':checksum(target),
             'tables':{t:len(v) for t,v in rows.items()},'state':'draft','processing_enabled':False,
             'overwrite':False,'verification_only':verification_only,'database_connections':0}
    private_json(target.with_suffix(target.suffix+'.receipt.json'),receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder');parser.add_argument('output_sql');parser.add_argument('--restore-ledger',required=True);parser.add_argument('--verification-only',action='store_true');args=parser.parse_args()
    print(json.dumps(generate(args.folder,args.output_sql,restore_ledger=args.restore_ledger,verification_only=args.verification_only)))
