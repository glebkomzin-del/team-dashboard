"""Offline unittest entry point, isolated imports and numeric-only result."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed_ids = {getattr(test, 'test_case', test).id() for test, _ in result.errors+result.failures}
    skipped_ids = {getattr(test, 'test_case', test).id() for test, _ in result.skipped}
    print(json.dumps({'total': result.testsRun, 'passed': result.testsRun-len(failed_ids|skipped_ids),
                      'failed_tests': len(failed_ids), 'errors': len(result.errors),
                      'failures': len(result.failures), 'skipped': len(skipped_ids)}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
