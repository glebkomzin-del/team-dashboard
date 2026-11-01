import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest

import offline_check


class OfflineHarnessTests(unittest.TestCase):
    def test_real_local_cli(self):
        result = subprocess.run([sys.executable, '-I', '-B',
                                 str(Path(__file__).parent / 'offline_check.py'), '--local'],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('14/14', result.stdout)
        self.assertIn('pipeline_local_asset_stub v11:compact1:gate1:gpt-6.1-sol:', result.stdout)
        self.assertNotIn('fail ', result.stdout)

    def test_failures_have_nonzero_exit_and_no_error_body(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = offline_check.run_checks(None, None, None, None)
        self.assertEqual(result, 1)
        self.assertIn('0/14', output.getvalue())
        self.assertNotIn('Traceback', output.getvalue())

    def test_network_guard(self):
        for event in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            with self.assertRaises(RuntimeError):
                offline_check.no_network(event, ())


if __name__ == '__main__':
    unittest.main()
