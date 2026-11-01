"""Offline execution of the real partial recovery CLI with injected transports."""
import copy, hashlib, io, json, subprocess, sys, tempfile, unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import final_source_partial_rollback_once as recovery
import n8n_dashboard_pause_once as n8n

class SourceFixture:
    def __init__(self,root,case):
        self.local=root/'local';self.local.mkdir();self.remote=root/'remote';self.remote.mkdir()
        self.private=root/'private';(self.private/'source').mkdir(parents=True)
        self.original=[{'space_id':'00000000-0000-0000-0000-000000000001','enabled':True,'other':'unchanged'}]
        self.config=copy.deepcopy(self.original);self.acl=[{'entry':n} for n in range(82)]
        (self.private/'source/freeze-business-original-acl.json').write_text(json.dumps(self.acl))
        (self.local/'source-original-config-private.json').write_text(json.dumps(self.original))
        self.nginx=b'fixture original';self.maintenance=self.nginx+b' maintenance';self.current_nginx=self.nginx
        for name,value in [('nginx-original.conf',self.nginx),('nginx-maintenance.conf',self.maintenance)]: (self.local/name).write_bytes(value)
        flags=dict(zip(recovery.FLAGS,['0','1','1','0','0']))
        self.runtime={'image':recovery.IMAGE,'running':True,'flags':flags,'host_flags':flags,'origin':'https://lghwikeotbkmojyyjglz.supabase.co','host_origin':'https://lghwikeotbkmojyyjglz.supabase.co','env_sha256':'fixture-env','host_sha256':'fixture-host'}
        (self.local/'source-original-runtime-private.json').write_text(json.dumps(self.runtime))
        self.scopes=['workflow:read'];self.original_scopes=list(self.scopes);self.calls=[];self.target=False
        self.workflows={w:{'active':True,'versionId':v,'activeVersionId':v} for w,v in n8n.VERSIONS.items()}
        self.pause_case=case;self.rest_error=False;self.health_error=False
        if case!='preflight':
            self.stage('scopes');self.scopes+=['workflow:activate','workflow:deactivate']
            self.stage('n8n')
            with patch.object(n8n,'PRIVATE_ERRORS',self.remote/'private-errors'):
                result=n8n.sequence(self.remote,'pause',self.api)
                if case in ('secondfails','uncertain'):assert result['status']=='FAILED'
                else:assert result['status']=='PASSED'
        if case in ('configguard','drain','stop','acl','foreign-config','foreign-nginx','foreign-env','foreign-image','foreign-acl','foreign-version','healthfail','resume400','resumetimeout'):
            self.stage('nginx');self.current_nginx=self.maintenance;self.stage('config')
            if case!='configguard':self.config=[{**r,'enabled':False} for r in self.original]
        if case in ('stop','acl','healthfail'):self.stage('stop');self.runtime['running']=False
        if case=='acl':self.stage('acl');self.acl=[]
        if case=='foreign-config':self.config[0]['other']='foreign'
        if case=='foreign-nginx':self.current_nginx=b'foreign'
        if case=='foreign-env':self.runtime['host_sha256']='foreign'
        if case=='foreign-image':self.runtime['image']='foreign'
        if case=='foreign-acl':self.acl=[{'foreign':True}]
        if case=='foreign-version':next(iter(self.workflows.values()))['versionId']='foreign'
        if case=='healthfail':self.health_error=True
        if case in ('resume400','resumetimeout'):self.rest_error=True
        self.calls=[]
    def stage(self,stage):n8n.durable(self.local,'source-stage-'+stage+'-attempt.json',{'stage':stage})
    def api(self,w,op='',data=None):
        if not op:return copy.deepcopy(self.workflows[w])
        action='pause' if op=='/deactivate' else 'resume-partial'
        assert (self.remote/('n8n-'+action+'-'+w+'-attempt.json')).exists(), 'Mutation must have durable intent'
        if op=='/deactivate':
            if w==list(n8n.VERSIONS)[1] and self.pause_case in ('secondfails','uncertain'):
                if self.pause_case=='uncertain':self.workflows[w]['active']=False
                raise TimeoutError('synthetic original uncertain response')
            self.workflows[w]['active']=False
        else:
            self.calls.append('activate:'+w)
            if self.rest_error:
                error=urllib.error.HTTPError('http://fixture.invalid/',400,'synthetic primary',{'X-Original':'fixture'},io.BytesIO(b'whole HTTP400 primary body')) if self.pause_case=='resume400' else TimeoutError('whole primary timeout')
                with patch('urllib.request.urlopen',side_effect=error):
                    n8n.http_read(urllib.request.Request('http://fixture.invalid/',data=b'{}'),operation='fixture-resume',private_errors=self.remote/'private-errors')
            assert data=={'versionId':n8n.VERSIONS[w]}
            self.workflows[w]['active']=True;self.workflows[w]['activeVersionId']=data['versionId']
        return copy.deepcopy(self.workflows[w])
    def shell(self,command,*args,**kw):
        if command.startswith('test ! -e '):
            if self.target:raise RuntimeError('Target marker exists')
            return b''
        if command=='cat '+recovery.NGINX:return self.current_nginx
        if command.startswith('python3 -c '):
            if 'source-recovery-health' in command:
                self.calls.append('health')
                if self.health_error:raise TimeoutError('health failed')
                return b'{"status":"ok"}'
            return json.dumps(self.runtime).encode()
        if '--action ' in command:
            action=command.split('--action ')[1].split()[0]
            with patch.object(n8n,'PRIVATE_ERRORS',self.remote/'private-errors'):
                result=n8n.sequence(self.remote,action,self.api)
            if result['status']!='PASSED':raise RuntimeError('Private n8n sequence failure')
            return json.dumps(result).encode()
        if command.startswith('docker start '):
            assert not self.runtime['running'];self.calls.append('start');self.runtime['running']=True;return b'original'
        if command.startswith('cmp -s '):
            assert self.current_nginx==self.maintenance
            self.calls.append('ingress');self.current_nginx=self.nginx;return b''
        raise AssertionError('Unexpected transport '+command)
    def sql(self,query):
        if query==recovery.acl_query():return copy.deepcopy(self.acl)
        if 'GRANT ' in query:self.calls.append('acl');self.acl=[{'entry':n} for n in range(82)];return []
        if 'UPDATE public.wm_processing_config' in query:
            assert 'LOCK TABLE' in query and 'IS DISTINCT FROM' in query
            self.calls.append('config');self.config=copy.deepcopy(self.original);return []
        raise AssertionError('Unexpected SQL')
    def n8n_sql(self,query):
        if query=='fixture-restore-scopes':self.calls.append('scopes');self.scopes=list(self.original_scopes);return ''
        key={'id':'fixture-key','userId':'fixture-user','apiKey':'fixture-secret','scopes':self.original_scopes}
        return json.dumps({'scopes':self.scopes,'userId':key['userId'],'md5':hashlib.md5(key['apiKey'].encode()).hexdigest()})
    def execute(self):
        access=self.private/'current-evidence/n8n-pause-access-1';access.mkdir(parents=True)
        (access/'existing-api-key-private.json').write_text(json.dumps({'id':'fixture-key','userId':'fixture-user','apiKey':'fixture-secret','scopes':self.original_scopes}))
        scope=self.private/'current-evidence/n8n-scope-plan-1';scope.mkdir();(scope/'restore-scopes.sql').write_text('fixture-restore-scopes')
        expected_sha=hashlib.sha256(self.nginx).hexdigest()
        with patch.object(recovery,'paths',return_value=(self.local,str(self.remote))),patch.object(recovery,'gate_check',return_value={}),patch.object(recovery,'PRIVATE',self.private),patch.object(recovery,'NGINX_SHA',expected_sha),patch.object(recovery,'shell',side_effect=self.shell),patch.object(recovery,'sql',side_effect=self.sql),patch.object(recovery,'n8n_sql',side_effect=self.n8n_sql),patch.object(recovery,'state',side_effect=lambda:{'config':copy.deepcopy(self.config)}),patch.object(recovery,'digest',side_effect=lambda p:'c1fa6235bdee05964f84e3e06521278f7ffcdd463340e8d2bb2644d9492d589a' if p.name=='restore-scopes.sql' else '26c34f43afa8408e933589b6ce705bf09bd3e36234904de81166b26dd1955f02'),patch('final_phase_common.ERROR_DIR',self.local/'errors'),patch('sys.argv',['recovery','--name','final-export-20261003T220500Z','--gate-receipt','fixture']),patch('builtins.print'),patch('subprocess.run',side_effect=AssertionError('No process permitted')),patch('urllib.request.urlopen',side_effect=AssertionError('No network permitted')):
            recovery.main()

class PartialRecovery(unittest.TestCase):
    def test_actual_entry_restores_all_partial_stages_exactly_once(self):
        for case in ['preflight','secondfails','uncertain','configguard','drain','stop','acl']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f=SourceFixture(Path(temp),case);f.execute()
                self.assertEqual(f.config,f.original);self.assertEqual(f.acl,[{'entry':n} for n in range(82)])
                self.assertEqual(f.current_nginx,f.nginx);self.assertEqual(f.scopes,f.original_scopes)
                self.assertTrue(f.runtime['running']);self.assertTrue(all(v['active'] and v['activeVersionId']==n8n.VERSIONS[w] for w,v in f.workflows.items()))
                self.assertEqual(f.calls.count('start'),int(case in ('stop','acl')))
                if 'ingress' in f.calls:self.assertLess(f.calls.index('health'),f.calls.index('ingress'))
                receipt=json.loads((f.local/'source-partial-recovery-receipt.json').read_text())
                self.assertEqual(receipt['source_freeze_budget'],1);self.assertEqual(receipt['target_writes'],0)
                self.assertEqual(receipt['lease_attempts']+receipt['dump_attempts'],0)
                if case in ('secondfails','uncertain'):
                    self.assertEqual(len([x for x in f.calls if x.startswith('activate:')]),1 if case=='secondfails' else 2)
                    self.assertTrue((f.remote/'n8n-pause-receipt.json').exists())
    def test_foreign_state_stops_before_any_recovery_mutation(self):
        for case in ['foreign-config','foreign-nginx','foreign-env','foreign-image','foreign-acl','foreign-version','target']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f=SourceFixture(Path(temp),case)
                if case=='target':f.target=True
                before=copy.deepcopy((f.config,f.acl,f.current_nginx,f.runtime,f.scopes,f.workflows))
                with self.assertRaises(RuntimeError):f.execute()
                self.assertEqual((f.config,f.acl,f.current_nginx,f.runtime,f.scopes,f.workflows),before)
                self.assertEqual(f.calls,[])
                self.assertTrue((f.local/'source-partial-recovery-failure.json').exists())
    def test_health_and_resume_failure_stop_no_speculative_retry(self):
        for case in ['healthfail','resume400','resumetimeout']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f=SourceFixture(Path(temp),case)
                with self.assertRaises(RuntimeError):f.execute()
                self.assertEqual(f.calls.count('start'),int(case=='healthfail'))
                if case=='healthfail':self.assertNotIn('ingress',f.calls)
                else:self.assertEqual(len([x for x in f.calls if x.startswith('activate:')]),1)
                self.assertNotEqual(f.scopes,f.original_scopes)
                self.assertFalse((f.local/'source-partial-recovery-receipt.json').exists())
                if case!='healthfail':
                    records=[json.loads(p.read_text()) for p in (f.remote/'private-errors').iterdir()]
                    primary=[r for r in records if r['operation']=='fixture-resume'];self.assertEqual(len(primary),1)
                    if case=='resume400':
                        self.assertEqual(primary[0]['status'],400)
                        self.assertEqual(__import__('base64').b64decode(primary[0]['body_b64']),b'whole HTTP400 primary body')
                    else:self.assertEqual(primary[0]['exception_text'],'whole primary timeout')

if __name__=='__main__':unittest.main(verbosity=2)
