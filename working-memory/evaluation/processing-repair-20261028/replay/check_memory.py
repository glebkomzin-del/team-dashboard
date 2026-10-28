"""Run existing memory regressions against the candidate, never the source tree."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'overlay'),str(ROOT/'private/runtime')];sys.dont_write_bytecode=True
import memory
assert Path(memory.__file__).resolve()==ROOT/'overlay/memory.py'
print('loaded candidate overlay/memory.py',flush=True)
suite=unittest.defaultTestLoader.discover(str(ROOT.parents[2]),pattern='test_memory.py')
result=unittest.TextTestRunner().run(suite)
raise SystemExit(not result.wasSuccessful())
