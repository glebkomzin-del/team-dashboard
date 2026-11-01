"""Run unchanged Release-2 tests and synthetic Release-3 tests offline."""
import contextlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_support import ROOT, RELEASE2, configure, sources

class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.outcomes = {}
        self.locations = {}
    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.setdefault(test.id(), 'passed')
    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, err, 'error')
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, err, 'failure')
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[test.id()] = 'skipped'
    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.record(test, err, 'failure' if issubclass(err[0], test.failureException) else 'error')
    def record(self, test, err, status):
        self.outcomes[test.id()] = status
        tb = err[2]
        locations = []
        while tb:
            locations.append([Path(tb.tb_frame.f_code.co_filename).name, tb.tb_lineno])
            tb = tb.tb_next
        self.locations[test.id()] = {'type': err[0].__name__, 'locations': locations}

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'new'
    if mode not in ('before', 'after', 'new'):
        raise SystemExit(2)
    before = mode == 'before'
    configure(before)
    result = Result()
    with sources(before), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        # Imports bind the chosen overlay before legacy tests insert their paths.
        import candidate_filter, hybrid_pipeline, compact_reconcile, hybrid_schema, canonical_worker
        manifest_path = (RELEASE2 if before else ROOT) / 'make_manifest.py'
        spec = importlib.util.spec_from_file_location('make_manifest', manifest_path)
        manifest = importlib.util.module_from_spec(spec)
        sys.modules['make_manifest'] = manifest
        spec.loader.exec_module(manifest)
        import processor
        processor.ROOT = hybrid_pipeline.ROOT = ROOT / 'runtime'
        suite = unittest.TestSuite()
        if mode in ('before', 'after'):
            for path in sorted((RELEASE2 / 'tests').glob('test_*.py')):
                module = importlib.import_module(path.stem)
                # Only temp-output/overlay root is redirected; tests stay unchanged.
                if path.stem == 'test_hotset':
                    module.ROOT = ROOT
                if path.stem == 'test_release_artifacts' and not before:
                    module.ROOT = ROOT
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        else:
            suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
        suite.run(result)
    counts = {'passed': sum(v == 'passed' for v in result.outcomes.values()),
              'total': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped)}
    (ROOT / (mode + '-tests.json')).write_text(json.dumps(
        {**counts, 'outcomes': result.outcomes, 'locations': result.locations}, indent=2) + '\n')
    print(json.dumps(counts, sort_keys=True))
    for key, value in result.locations.items():
        print(key, json.dumps(value, sort_keys=True))
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
