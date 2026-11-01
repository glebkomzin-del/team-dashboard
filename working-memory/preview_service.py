"""Launch the existing private service against a saved DB without writes or workers."""
import argparse
import json
import os
from pathlib import Path
import runpy
import secrets
from review_api import open_readonly

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8794)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('port outside local service range')
    open_readonly(args.db).close()
    config_path = Path(__file__).parent / '.local/preview-service.json'
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    token = secrets.token_urlsafe(48)
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as out: json.dump({'port': args.port, 'token': token}, out)
    os.environ.update(MEMORY_DB=str(args.db.resolve()), MEMORY_READ_ONLY='1', MEMORY_API_TOKEN=token, MEMORY_BIND='127.0.0.1', PORT=str(args.port))
    print(f'Read-only preview service on 127.0.0.1:{args.port}', flush=True)
    runpy.run_path(str(Path(__file__).with_name('server.py')), run_name='__main__')
