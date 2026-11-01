"""Stdlib-only, offline test runner; every temporary write stays in this copy."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/existing'), str(ROOT / 'tests')]
os.chdir(ROOT)
os.environ.clear()
os.environ['MEMORY_PROMPT_VERSION'] = 'v9'
tempfile.tempdir = str(ROOT / 'evidence/tmp')
Path(tempfile.tempdir).mkdir(exist_ok=True)


def audit(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.spawn')):
        raise RuntimeError('Network and child processes are prohibited in this test run')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0]))
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if writing and not path.resolve().is_relative_to(ROOT):
            raise RuntimeError('Write outside pipeline-v12 prohibited')
        if path.name.startswith('.env') or path.name == 'model-keys.json':
            raise RuntimeError('Secret files are prohibited')
    if event in ('os.symlink', 'os.link'):
        raise RuntimeError('Link creation is prohibited in this test run')
    if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.truncate'):
        if isinstance(args[0], (str, bytes, os.PathLike)):
            if not Path(os.fsdecode(args[0])).resolve().is_relative_to(ROOT):
                raise RuntimeError('Filesystem mutation outside pipeline-v12 prohibited')


sys.addaudithook(audit)


def compact_module():
    # Root tests have evolved beyond this fixed release. Remove only the import
    # of an unavailable constant so all other original assertions can run.
    path = ROOT / 'tests/existing/test_compact_reconcile.py'
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'hybrid_pipeline':
            node.names = [a for a in node.names if a.name != 'GPT6_MAX_INPUT_TOKENS']
    module = types.ModuleType('test_compact_reconcile')
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    return module


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'acceptance'
    loader = unittest.TestLoader()
    import test_hybrid
    compact = compact_module()
    suite = unittest.TestSuite()
    if mode == 'legacy-full':
        suite.addTests(loader.loadTestsFromModule(test_hybrid))
        suite.addTests(loader.loadTestsFromModule(compact))
    else:
        suite.addTests(loader.loadTestsFromTestCase(test_hybrid.HybridTests))
        suite.addTest(test_hybrid.StageResumeTests('test_transport_error_never_triggers_semantic_model_retry'))
        for cls in (compact.CatalogTests, compact.CombinedContractTests, compact.PipelineIntegrationTests):
            suite.addTests(loader.loadTestsFromTestCase(cls))
        newer = {'test_terra_compact_budget_counts_utf8_schema_framing_and_output',
                 'test_gpt6_compact_accepts_420k_and_checks_input_separately',
                 'test_gpt6_noncompact_checks_encoded_input_and_schema'}
        for name in loader.getTestCaseNames(compact.PackingTests):
            if name not in newer:
                suite.addTest(compact.PackingTests(name))
        if mode == 'acceptance':
            suite.addTests(loader.discover(str(ROOT / 'tests'), pattern='test_hotset.py'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'mode': mode, 'passed': result.testsRun - len(result.errors) - len(result.failures) - len(result.skipped),
                      'total': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                      'skipped': len(result.skipped)}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
