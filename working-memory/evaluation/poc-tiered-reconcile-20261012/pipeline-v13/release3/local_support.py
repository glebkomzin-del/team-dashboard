"""Read-only source resolver for the incomplete prod2 local export."""
import contextlib
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
PROD = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/prod2')
RELEASE2 = ROOT.parent / 'release2'
BASE_OVERLAY = RELEASE2 / 'overlay'
ASSETS = ROOT.parents[2]  # working-memory/evaluation
OVERLAY = ROOT / 'overlay'

def guard(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.spawn')):
        raise RuntimeError('offline restriction')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if writing and not path.is_relative_to(ROOT):
            raise RuntimeError('write restriction')
        if path.name.startswith('.env') or path.name == 'model-keys.json':
            raise RuntimeError('secret restriction')
    if event == 'sqlite3.connect' and args[0] != ':memory:':
        value = str(args[0])
        if not value.startswith('file:') and not Path(value).resolve().is_relative_to(ROOT):
            raise RuntimeError('sqlite write restriction')
    if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.truncate', 'os.rename'):
        paths = args[:2] if event == 'os.rename' else args[:1]
        for value in paths:
            if isinstance(value, (str, bytes, os.PathLike)) and not Path(os.fsdecode(value)).resolve().is_relative_to(ROOT):
                raise RuntimeError('write restriction')

def configure(before=False):
    os.environ.clear()
    os.environ.update(MEMORY_PROMPT_VERSION='v4', MEMORY_ACTION_GATE='1')
    sys.dont_write_bytecode = True
    sys.path[:0] = ([str(BASE_OVERLAY), str(PROD)] if before else [str(OVERLAY), str(BASE_OVERLAY), str(PROD)]) + [str(ROOT), str(ROOT/'tests'), str(RELEASE2/'tests')]
    os.chdir(ROOT)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    tempfile.tempdir = str(ROOT / 'tmp')
    sys.addaudithook(guard)

@contextlib.contextmanager
def sources(before=False):
    original_text, original_bytes = Path.read_text, Path.read_bytes
    roots = (PROD, OVERLAY, BASE_OVERLAY, ROOT / 'runtime')
    def resolve(path):
        for root in roots:
            if path.is_relative_to(root):
                rel = path.relative_to(root)
                if len(rel.parts) == 1:
                    choices = ([BASE_OVERLAY/rel, PROD/rel] if before else [OVERLAY/rel, BASE_OVERLAY/rel, PROD/rel])
                elif rel.parts[0] == 'evaluation':
                    choices = [PROD/rel, ASSETS/Path(*rel.parts[1:])]
                else:
                    return path
                return next((p for p in choices if p.is_file()), path)
        return path
    with patch.object(Path, 'read_text', lambda p,*a,**k: original_text(resolve(p),*a,**k)), patch.object(Path, 'read_bytes', lambda p: original_bytes(resolve(p))):
        yield

