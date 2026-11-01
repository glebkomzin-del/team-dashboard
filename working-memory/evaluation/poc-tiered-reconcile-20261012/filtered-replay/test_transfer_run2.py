"""Shell flow tests use an inert fake python3, with no provider transport."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent


class TransferTests(unittest.TestCase):
    def run_script(self,dry_exit,key=True):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base=Path(directory)
            script=base/'run_on_server_run2.sh'
            shutil.copyfile(ROOT/'transfer/run_on_server_run2.sh',script)
            binary=base/'python3'
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> mock-calls.log\n'
                'case " $* " in *" --execute "*) exit 0;; esac\n'
                'exit '+str(dry_exit)+'\n')
            binary.chmod(0o700)
            env={'PATH':str(base)+':/usr/bin:/bin'}
            if key:env['OPENAI_API_KEY']='synthetic-mock-only'
            result=subprocess.run(['/bin/sh',str(script)],env=env,capture_output=True)
            return result.returncode,(base/'mock-calls.log').read_text().splitlines(),(base/'run2.log').read_text()

    def test_only_successful_dry_run_allows_execute(self):
        code,calls,log=self.run_script(0)
        self.assertEqual(code,0)
        self.assertEqual(len(calls),2)
        self.assertNotIn('--execute',calls[0])
        self.assertIn('--execute --max-usd 3.20 --results results-filtered-run2.jsonl',calls[1])
        for call in calls:
            self.assertTrue(call.startswith('-I -B run_filtered.py '))
            self.assertIn('--requests selected_requests-run2.jsonl --skip-done run1-completed.jsonl',call)
        self.assertNotIn('synthetic-mock-only',log)

    def test_failed_dry_run_blocks_execute(self):
        code,calls,_=self.run_script(2)
        self.assertEqual(code,2)
        self.assertEqual(len(calls),1)
        self.assertNotIn('--execute',calls[0])

    def test_missing_environment_key_blocks_execute_after_dry_run(self):
        code,calls,_=self.run_script(0,key=False)
        self.assertNotEqual(code,0)
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
