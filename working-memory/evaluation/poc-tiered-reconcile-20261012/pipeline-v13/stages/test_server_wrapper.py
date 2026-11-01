"""Shell orchestration checks with a fake python executable, never a provider."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
FAKE_PYTHON = '''#!/bin/sh
case "$*" in
  *"--max-usd 0.80"*) : ;;
  *) exit 9 ;;
esac
case "$*" in
  *"--execute"*) printf '2\\n'; printf '1\\n' > stage-results.jsonl ;;
  *) printf '1\\n'; exit "${MOCK_DRY_EXIT:-0}" ;;
esac
'''


class ServerWrapperTests(unittest.TestCase):
    def setup_run(self, code=0):
        directory = tempfile.TemporaryDirectory(dir=ROOT, prefix='.wrapper-test-')
        self.addCleanup(directory.cleanup)
        folder = Path(directory.name)
        shutil.copyfile(ROOT/'run_stage_on_server.sh', folder/'run_stage_on_server.sh')
        python = folder/'python3'
        python.write_text(FAKE_PYTHON)
        python.chmod(0o700)
        environment = {'PATH':str(folder)+':/usr/bin:/bin', 'MOCK_DRY_EXIT':str(code)}
        return folder, environment

    def run_script(self, folder, env):
        return subprocess.run(['/bin/sh',str(folder/'run_stage_on_server.sh')],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_dry_zero_then_execute_same_cap(self):
        folder, env = self.setup_run()
        result = self.run_script(folder, env)
        self.assertEqual(result.returncode,0)
        self.assertEqual((folder/'stage.log').read_text(),'1\n2\n')
        self.assertTrue((folder/'stage-results.jsonl').exists())

    def test_dry_failure_no_execute(self):
        folder, env = self.setup_run(2)
        result = self.run_script(folder, env)
        self.assertEqual(result.returncode,2)
        self.assertEqual((folder/'stage.log').read_text(),'1\n')
        self.assertFalse((folder/'stage-results.jsonl').exists())

    def test_existing_results_no_replay(self):
        folder, env = self.setup_run()
        (folder/'stage-results.jsonl').write_text('1\n')
        self.assertEqual(self.run_script(folder,env).returncode,1)
        self.assertFalse((folder/'stage.log').exists())

    def test_existing_log_preserved(self):
        folder, env = self.setup_run()
        (folder/'stage.log').write_text('3\n')
        self.assertEqual(self.run_script(folder,env).returncode,1)
        self.assertEqual((folder/'stage.log').read_text(),'3\n')


if __name__ == '__main__':
    unittest.main()
