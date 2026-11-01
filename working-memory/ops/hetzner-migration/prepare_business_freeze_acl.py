"""Read-only source ACL receipt and exact reversible app freeze preparation."""
import base64,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/'.local/hetzner-migration-20261003/source'
os.umask(0o077)
token=subprocess.run(['/usr/bin/security','find-generic-password','-s','Supabase CLI','-a','supabase','-w'],capture_output=True,text=True,check=True).stdout.strip()
if token.startswith('go-keyring-base64:'):token=base64.b64decode(token.split(':',1)[1]).decode()
query="""SELECT 'TABLE' AS kind,format('%I.%I',n.nspname,c.relname) AS object,grantor.rolname AS grantor,a.privilege_type,a.is_grantable FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles grantee ON grantee.oid=a.grantee JOIN pg_roles grantor ON grantor.oid=a.grantor WHERE n.nspname='public' AND grantee.rolname='service_role' AND c.relkind IN ('r','p','v','m','f') AND c.relowner='postgres'::regrole AND grantor.rolname='postgres' AND a.privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE') UNION ALL SELECT 'FUNCTION',format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)),grantor.rolname,a.privilege_type,a.is_grantable FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles grantee ON grantee.oid=a.grantee JOIN pg_roles grantor ON grantor.oid=a.grantor WHERE n.nspname='public' AND grantee.rolname='service_role' AND p.proowner='postgres'::regrole AND grantor.rolname='postgres' AND p.provolatile='v' AND p.prorettype<>'trigger'::regtype ORDER BY 1,2,3,4"""
request=urllib.request.Request('https://api.supabase.com/v1/projects/lghwikeotbkmojyyjglz/database/query',data=json.dumps({'query':query}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=30) as response:rows=json.load(response)
if not isinstance(rows,list) or not rows:raise SystemExit('Unexpected ACL result')
path=ROOT/'freeze-business-original-acl.json'
with path.open('x') as stream:json.dump(rows,stream,indent=2)
def quote_role(value):return '"'+value.replace('"','""')+'"'
restore='BEGIN;\n'
for row in rows:
 if row['privilege_type'] not in ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','EXECUTE','MAINTAIN']:raise SystemExit('Unknown privilege')
 restore+='SET LOCAL ROLE '+quote_role(row['grantor'])+';\nGRANT '+row['privilege_type']+' ON '+row['kind']+' '+row['object']+' TO service_role'+(' WITH GRANT OPTION' if row['is_grantable'] else '')+';\n'
restore+='COMMIT;\n'
freeze='BEGIN;\n'
for row in rows:
 freeze+='REVOKE '+row['privilege_type']+' ON '+row['kind']+' '+row['object']+' FROM service_role;\n'
freeze+='COMMIT;\n'

(ROOT/'freeze-business-restore-acl.sql').write_text(restore);(ROOT/'freeze-business.sql').write_text(freeze)
receipt={'acl_entries':len(rows),'table_objects':len({r['object'] for r in rows if r['kind']=='TABLE'}),'function_objects':len({r['object'] for r in rows if r['kind']=='FUNCTION'}),'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['freeze-business-original-acl.json','freeze-business-restore-acl.sql','freeze-business.sql']},'executed':False,'source_grantor':'postgres','extension_functions_excluded':True,'read_only_stable_functions_excluded':True,'trigger_functions_excluded':True}
(ROOT/'freeze-business-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
