"""Offline unittest runner: python3 -I -B run_tests.py before|after|release."""
import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_support import ROOT, PROD, configure, sources

class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.outcomes = {}
    def addSuccess(self,test):
        super().addSuccess(test); self.outcomes[test.id()]='passed'
    def addError(self,test,err):
        super().addError(test,err); self.outcomes[test.id()]='error:'+err[0].__name__
    def addFailure(self,test,err):
        super().addFailure(test,err); self.outcomes[test.id()]='failure'
    def addSkip(self,test,reason):
        super().addSkip(test,reason); self.outcomes[test.id()]='skipped:'+reason
    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err is not None:
            self.outcomes[test.id()]='failure' if issubclass(err[0],test.failureException) else 'error:'+err[0].__name__

def main():
    mode = sys.argv[1] if len(sys.argv)>1 else 'release'
    if mode=='compare':
        before=json.loads((ROOT/'before-tests.json').read_text())
        after=json.loads((ROOT/'after-tests.json').read_text())
        same=before['outcomes']==after['outcomes'] and before['excluded_modules']==after['excluded_modules']
        print(json.dumps({'same':same,'before':before['passed'],'after':after['passed'],'total':after['total']},sort_keys=True))
        return 0 if same else 1
    configure(mode=='before')
    result = Result()
    excluded = {}
    with sources(mode=='before'), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import processor, hybrid_pipeline
        processor.ROOT=hybrid_pipeline.ROOT=ROOT/'runtime'
        suite=unittest.TestSuite()
        if mode in ('before','after'):
            for path in sorted(PROD.glob('test_*.py')):
                module=importlib.import_module(path.stem)
                tests=unittest.defaultTestLoader.loadTestsFromModule(module)
                if path.stem.endswith('_http') or path.stem=='test_transport':
                    excluded[path.stem]={'count':tests.countTestCases(),'reason':'server/network prohibited'}
                else:
                    suite.addTests(tests)
        else:
            suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        suite.run(result)
    counts={'passed':sum(status=='passed' for status in result.outcomes.values()),'total':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
    report={'mode':mode,**counts,'excluded_modules':excluded,'outcomes':result.outcomes}
    (ROOT/(mode+'-tests.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(counts,sort_keys=True))
    for key,status in result.outcomes.items():
        if status!='passed': print(key+' '+status)
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__': raise SystemExit(main())
