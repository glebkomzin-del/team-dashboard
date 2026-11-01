#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")"
# A fresh unpack directory is required; do not repay an earlier attempt.
for output in synth.log synth-dry-run.jsonl synth-results.jsonl; do
    if [ -e "$output" ]; then exit 2; fi
done
exec > synth.log 2>&1
: "${OPENAI_API_KEY:?}"
python3 -I -B synthesize.py synth-input-0[1-5].json --max-usd 1.00 --results synth-dry-run.jsonl
python3 -I -B synthesize.py synth-input-0[1-5].json --execute --max-usd 1.00 --results synth-results.jsonl
