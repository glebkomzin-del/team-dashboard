#!/bin/sh
# OPENAI_API_KEY must be exported by the caller; no credential files are read.
set -eu
script_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
cd "$script_dir"
exec >> run.log 2>&1
python3 -I -B run_filtered.py --max-usd 3.50
: "${OPENAI_API_KEY:?OPENAI_API_KEY must already be set in the environment}"
python3 -I -B run_filtered.py --execute --max-usd 3.50 --results results-filtered.jsonl
