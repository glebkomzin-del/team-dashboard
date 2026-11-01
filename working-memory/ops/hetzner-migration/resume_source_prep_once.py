"""Fresh PREP evidence only: offline old archive and optional read-only Source catalog."""
import argparse
import json
import os
import subprocess
from final_phase_common import PRIVATE, HERE, digest, save, sql
from final_quiescence_once import EFFECTIVE_PRIVILEGES_SQL, acl_query
from vault_copy_codec import verify_vault_copy


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-preflight',action='store_true')
    parser.add_argument('--cycle',type=int,choices=[1,2],default=1)
    args=parser.parse_args()
    os.umask(0o077)
    evidence=PRIVATE/('current-evidence/resume-source-prep-'+str(args.cycle))
    evidence.mkdir(mode=0o700)
    old=PRIVATE/'final-export-20261003T205500Z/readonly-export-followup-1'
    before=json.loads((old/'metadata-before-private.json').read_text())
    after=json.loads((old/'metadata-after-private.json').read_text())
    assert before==after, 'Historical metadata changed'
    copy_sql=(old/'vault-copy-private.sql').read_text()
    assert verify_vault_copy(copy_sql,after['vault'])
    # Bind saved COPY sidecar to the actual archive, without DB connections/restores.
    with (evidence/'archive-vault-copy-private.sql').open('xb') as output, (evidence/'archive-extract-private.stderr').open('xb') as errors:
        result=subprocess.run(['/opt/homebrew/bin/pg_restore','--data-only','--schema=vault','--table=secrets','--file=-',str(old/'full.dump')],stdout=output,stderr=errors,timeout=600)
    assert result.returncode==0, 'Historical Vault extraction failed; private stderr retained'
    extracted=(evidence/'archive-vault-copy-private.sql').read_text()
    assert extracted==copy_sql, 'Historical sidecar not archive-bound'
    assert verify_vault_copy(extracted,after['vault'])
    receipt={'status':'PREP_OFFLINE_VALIDATED','historical_archive_only':True,
             'fresh_source_snapshot_required':True,'source_mutations':0,'new_leases':0,'new_dumps':0,
             'dump_sha256':digest(old/'full.dump'),'dump_bytes':(old/'full.dump').stat().st_size,
             'before_after_metadata_equal':True,'vault_cipher_nonce_full_metadata_equal':True,
             'archive_sidecar_byte_equal':True,'repair_cycles_completed':args.cycle,
             'legacy_sidecar_key_id_absent_actual_archive_key_id_null':True,
             'files':{name:digest(HERE/name) for name in ['final_quiescence_once.py','final_export_once.py','final_phase_common.py','vault_copy_codec.py','test_resume_source_export.py','resume_source_prep_once.py']}}
    if args.source_preflight:
        acl=sql(acl_query())
        expected=json.loads((PRIVATE/'source/freeze-business-original-acl.json').read_text())
        assert acl==expected, 'Actual Source ACL differs from original'
        effective=sql(EFFECTIVE_PRIVILEGES_SQL)
        assert [r['role'] for r in effective]==['anon','authenticated','service_role']
        # Writers are naturally enabled before freeze. This proves query validity only.
        catalog=sql("SELECT p.oid,format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS object FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proowner='postgres'::regrole AND p.provolatile='v' AND p.prorettype<>'trigger'::regtype ORDER BY p.oid")
        assert {r['object'] for r in catalog}=={r['object'] for r in expected if r['kind']=='FUNCTION'}, 'Writer catalog differs from reversible freeze scope'
        save(evidence/'source-catalog-private.json',{'acl':acl,'effective':effective,'writers':catalog})
        receipt.update({'source_read_only_queries':3,'source_acl_exact_original':True,
                        'source_catalog_query_valid':True,'catalog_writers_equal_freeze_scope':True,
                        'catalog_writer_count':len(catalog),'pre_freeze_effective':effective,
                        'frozen_zero_verification_pending':True})
    else:receipt['source_read_only_queries']=0
    save(evidence/'resume-source-prep-receipt.json',receipt)
    print(json.dumps(receipt))


if __name__=='__main__':main()
