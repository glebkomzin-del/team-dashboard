"""Read-only catalog diagnostic: preserve full response before assertions."""
import json,os
import final_phase_common as common
QUERY="""SELECT p.oid,format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS object,p.proacl::text AS acl,
 has_function_privilege('anon',p.oid,'EXECUTE') AS anon_execute,
 has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated_execute,
 has_function_privilege('service_role',p.oid,'EXECUTE') AS service_execute,
 (SELECT array_agg(e.extname ORDER BY e.extname) FROM pg_depend d JOIN pg_extension e ON d.refobjid=e.oid WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.refclassid='pg_extension'::regclass AND d.deptype='e') AS extensions
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proowner='postgres'::regrole AND p.provolatile='v' AND p.prorettype<>'trigger'::regtype ORDER BY p.oid"""
def main():
 os.umask(0o077);evidence=common.PRIVATE/'current-evidence/catalog-reconcile-1';evidence.mkdir(mode=0o700);common.ERROR_DIR=evidence/'errors'
 common.save(evidence/'attempt.json',{'user_decision':'Suche Wege, bis es funktioniert und fahre den Umzug fort','source_readonly_query_budget':1,'source_mutations':0})
 rows=common.sql(QUERY);common.save(evidence/'actual-catalog-private.json',rows)
 expected=json.loads((common.PRIVATE/'source/freeze-business-original-acl.json').read_text());names={r['object'] for r in expected if r['kind']=='FUNCTION'};actual={r['object'] for r in rows}
 missing=sorted(names-actual);extra=[r for r in rows if r['object'] not in names];callable_extra=[r for r in extra if any(r[k] for k in ['anon_execute','authenticated_execute','service_execute'])]
 receipt={'status':'CATALOG_RECONCILED' if not missing and not callable_extra else 'ACTUAL_SCOPE_DIFFERENCE','actual_catalog_functions':len(rows),'original_granted_functions':len(names),'missing_original_functions':missing,'extra_function_count':len(extra),'extra_callable_by_public_roles_count':len(callable_extra),'extra_functions':extra,'source_mutations':0,'source_readonly_queries':1,'catalog_response_preserved':True,'private_catalog_sha256':common.digest(evidence/'actual-catalog-private.json'),'comparison_hypothesis':'Original ACL is a granted-object subset of a broader catalog, not necessarily the entire catalog'}
 common.save(evidence/'receipt.json',receipt);print(json.dumps(receipt))
if __name__=='__main__':main()
