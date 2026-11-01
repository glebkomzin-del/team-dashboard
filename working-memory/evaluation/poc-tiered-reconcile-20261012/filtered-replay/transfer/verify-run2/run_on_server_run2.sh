#!/bin/sh
# Caller exports OPENAI_API_KEY; no credential files are read.
set -eu
script_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
cd "$script_dir"
exec >> run2.log 2>&1
python3 -I -B run_filtered.py --requests selected_requests-run2.jsonl --skip-done run1-completed.jsonl --max-usd 3.20
: "${OPENAI_API_KEY:?OPENAI_API_KEY must already be set in the environment}"
python3 -I -B run_filtered.py --requests selected_requests-run2.jsonl --skip-done run1-completed.jsonl --execute --max-usd 3.20 --results results-filtered-run2.jsonl
