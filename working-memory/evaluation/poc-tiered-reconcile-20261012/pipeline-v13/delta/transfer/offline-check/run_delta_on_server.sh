#!/bin/sh
set -eu
# Extract this bundle in a new directory. No credential files are read.
cd "$(dirname "$0")"
python3 -I -B replay_delta.py --max-usd 1.00
: "${OPENAI_API_KEY:?OPENAI_API_KEY must already be exported}"
python3 -I -B replay_delta.py --execute --max-usd 1.00
python3 -I -B compare_delta.py
