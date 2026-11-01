"""Offline deployment guards. No server mutations or provider requests."""
import ast,base64,importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
def load(name):
 spec=importlib.util.spec_from_file_location('repair_'+name,HERE/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
class DeployTests(unittest.TestCase):
 def test_no_shell_or_secret_environment_export(self):
  for name in ('run.py','remote.py'):
   source=(HERE/name).read_text();ast.parse(source);self.assertNotIn('shell=True',source);self.assertNotIn("['Config']['Env']",source);self.assertNotIn('api_key(',source)
 def test_literal_encodes_shell_and_sql_metacharacters(self):
  value="' $$ ; $(touch /tmp/no) \\ 日本語";result=load('remote').lit(value);self.assertEqual(base64.b64decode(result.split("'")[1]).decode(),value);self.assertNotIn('$(',result)
 def test_reviewed_bundle(self):
  value=load('run').bundle('preflight');self.assertEqual(set(value['files']),{'memory.py','openai_provider.py'});self.assertEqual(len(value['steps']),2);self.assertEqual(value['steps'][0]['stage_request']['expected_revision'],338);self.assertNotEqual(value['new_pipeline'],value['original_config']['pipeline'])
 def test_unreviewed_code_rejected(self):
  original=Path.read_bytes
  def altered(path):return original(path)+(b'\n' if str(path).endswith('/replay/overlay/memory.py') else b'')
  with patch.object(Path,'read_bytes',altered),self.assertRaisesRegex(AssertionError,'Reviewed candidate changed'):load('run').bundle('preflight')
 def test_revision_busy_and_pause_drift_rejected_without_commands(self):
  value=load('run').bundle('preflight');remote=load('remote')
  baseline={'space':{'revision':338},'config':{**value['original_config'],'enabled':False},'busy':0}
  cases=[{**baseline,'space':{'revision':339}},{**baseline,'busy':1},{**baseline,'config':value['original_config']}]
  for state in cases:
   with self.subTest(state=list(state)),patch.object(remote,'snapshot',return_value=state),patch.object(remote,'verify_code'),patch.object(remote,'verify_routines'),patch.object(remote,'call',side_effect=AssertionError('Unexpected command')),self.assertRaises(AssertionError):remote.run(value)
 def test_hold_satisfies_actual_original_deletion_startup_guard(self):
  remote=load('remote');source=(HERE.parent/'replay/private/runtime/server.py').read_text();tree=ast.parse(source)
  guard=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='ORIGINAL_DELETION_ENABLED')
  code=compile(ast.fix_missing_locations(ast.Module(body=[guard],type_ignores=[])),'actual-server-startup','exec')
  with self.assertRaisesRegex(SystemExit,'Original deletion requires the writable canonical journal'):
   exec(code,{'ORIGINAL_DELETION_ENABLED':True,'JOURNAL':object(),'READ_ONLY':True})
  self.assertEqual(remote.HOLD_FLAGS['MEMORY_ORIGINAL_DELETION_ENABLED'],'0')
  self.assertIn('MEMORY_ORIGINAL_DELETION_ENABLED: "0"',remote.hold_yaml())
  exec(code,{'ORIGINAL_DELETION_ENABLED':remote.HOLD_FLAGS['MEMORY_ORIGINAL_DELETION_ENABLED']=='1','JOURNAL':object(),'READ_ONLY':True})
 def test_retry_preserves_first_original_flags_and_gets_missing_from_compose(self):
  remote=load('remote');original={'MEMORY_READ_ONLY':'0','MEMORY_AUTOMATIC_ENABLED':'1','MEMORY_INTAKE_ENABLED':'1','MEMORY_QA_ENABLED':'1'};record={'original_flags':dict(original)}
  config={'services':{'canonical-draft':{'environment':{'MEMORY_ORIGINAL_DELETION_ENABLED':'1'}}}}
  with patch.object(remote,'flags',return_value=dict(remote.HOLD_FLAGS)) as held,patch.object(remote,'call',return_value=json.dumps(config).encode()):
   remote.preserve_original_flags(record);held.assert_not_called()
  self.assertEqual(record['original_flags'],{**original,'MEMORY_ORIGINAL_DELETION_ENABLED':'1'})
if __name__=='__main__':unittest.main()
