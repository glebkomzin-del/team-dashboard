"""Single Astra-reviewed offline archive proof then at most three readonly catalog queries."""
import ast, hashlib, json, os, subprocess
from pathlib import Path
import final_phase_common as common
from final_quiescence_once import EFFECTIVE_PRIVILEGES_SQL, acl_query
from vault_copy_codec import vault_copy_rows, verify_vault_copy
ARCHIVE_SHA='61cb1a551eab3c09001160cd0c8e2faea5ccbdb35add9780f887ce2e1433d1e8'
ARCHIVE_BYTES=321266826

def main():
    os.umask(0o077)
    evidence=common.PRIVATE/'current-evidence/resume-source-prep-followup-1'
    evidence.mkdir(mode=0o700)
    common.ERROR_DIR=evidence/'errors'
    common.save(evidence/'attempt.json',{'reviewer':'/root/resume_archive_gate','decision':'CHANGE_APPROACH','followup':1,'max_extractions':1,'max_source_readonly_queries':3,'source_mutations':0,'new_leases':0,'new_dumps':0})
    queries=0
    try:
        old=Path.home()/'Library/Application Support/Dashboard Job Backup/hetzner-migration-20261003/blocked-final-export-20261003T205500Z-evidence/readonly-export-followup-1'
        archive=old/'full.dump'
        assert archive.stat().st_size==ARCHIVE_BYTES and common.digest(archive)==ARCHIVE_SHA, 'Actual alternative archive identity differs'
        before=json.loads((old/'metadata-before-private.json').read_text())
        after=json.loads((old/'metadata-after-private.json').read_text())
        original=(old/'vault-copy-private.sql').read_text()
        assert before==after and verify_vault_copy(original,after['vault'])
        with (evidence/'archive-vault-copy-private.sql').open('xb') as output, (evidence/'archive-extract-private.stderr').open('xb') as errors:
            result=subprocess.run(['/opt/homebrew/bin/pg_restore','--data-only','--schema=vault','--table=secrets','--file=-',str(archive)],stdout=output,stderr=errors,timeout=600)
        assert result.returncode==0, 'Archive extraction failed; original stderr retained'
        actual=(evidence/'archive-vault-copy-private.sql').read_text()
        assert vault_copy_rows(actual)==vault_copy_rows(original), 'Full decoded archive COPY row differs'
        assert verify_vault_copy(actual,after['vault'])
        queries+=1;acl=common.sql(acl_query())
        expected=json.loads((common.PRIVATE/'source/freeze-business-original-acl.json').read_text())
        assert acl==expected, 'Actual Source ACL differs from original'
        queries+=1;effective=common.sql(EFFECTIVE_PRIVILEGES_SQL)
        assert [r['role'] for r in effective]==['anon','authenticated','service_role']
        queries+=1;catalog=common.sql("SELECT p.oid,format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS object FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proowner='postgres'::regrole AND p.provolatile='v' AND p.prorettype<>'trigger'::regtype ORDER BY p.oid")
        assert {r['object'] for r in catalog}=={r['object'] for r in expected if r['kind']=='FUNCTION'}, 'Actual writer catalog differs from reversible freeze scope'
        common.save(evidence/'source-catalog-private.json',{'acl':acl,'effective':effective,'writers':catalog})
        receipt={'status':'FOLLOWUP_PASSED','reviewer':'/root/resume_archive_gate','review_decision':'CHANGE_APPROACH','followup_attempts':1,'archive_extractions':1,'archive_sha256':ARCHIVE_SHA,'archive_bytes':ARCHIVE_BYTES,'all_decoded_copy_columns_rows_equal':True,'vault_cipher_nonce_full_metadata_equal':True,'source_readonly_queries':queries,'source_acl_exact_original':True,'source_catalog_query_valid':True,'catalog_writers_equal_freeze_scope':True,'catalog_writer_count':len(catalog),'source_mutations':0,'new_leases':0,'new_dumps':0,'historical_snapshot_only':True,'fresh_final_export_required':True,'frozen_zero_verification_pending':True,'script_hashes':{name:common.digest(common.HERE/name) for name in ['resume_source_prep_followup_once.py','final_quiescence_once.py','final_phase_common.py','vault_copy_codec.py']}}
        common.save(evidence/'receipt.json',receipt);print(json.dumps(receipt))
    except Exception as error:
        primary=common.private_failure('PREP_FOLLOWUP_ERROR',error_type=type(error).__name__,primary_error=str(error),stdout=getattr(error,'stdout',None),stderr=getattr(error,'stderr',None))
        common.save(evidence/'receipt.json',{'status':'FOLLOWUP_FAILED','source_readonly_queries_attempted':queries,'source_mutations':0,'new_leases':0,'new_dumps':0,'private_primary_error':str(primary),'no_automatic_retry':True})
        raise primary from None
if __name__=='__main__':main()
