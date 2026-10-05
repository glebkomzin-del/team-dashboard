#!/bin/sh
set -eu
if [ "${1:-}" != "--go" ]; then
  echo "Explicit Lead production GO required: pass --go" >&2
  exit 2
fi
cd "$(dirname "$0")/candidate"
shasum -a 256 -c SHA256SUMS
if [ "$(python3 -c 'import json;print(json.load(open(".vercel/project.json"))["projectId"])')" != 'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5' ]; then
  echo 'Vercel project mismatch' >&2
  exit 3
fi
vercel deploy --prebuilt --prod --yes
