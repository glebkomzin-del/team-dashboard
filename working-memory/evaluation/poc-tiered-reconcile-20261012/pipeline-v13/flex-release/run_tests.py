"""Stdlib-only unittest entrypoint compatible with python3 -I -B."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f'{passed}/{result.testsRun}')
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
