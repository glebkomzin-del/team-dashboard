#!/bin/sh
# Human-run server entry point. Credentials only via OPENAI_API_KEY environment.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -e stage-results.jsonl ] || [ -e stage.log ]; then
    printf '%s\n' 'Existing run files: refusing to repeat paid identities.' >&2
    exit 1
fi
# Exclusive log creation also prevents concurrent wrapper starts.
set -C
exec > stage.log 2>&1
if python3 -I -B replay_stage.py --requests selected_requests.jsonl --stage both --model gpt-6-luna --select all --limit 12 --max-usd 0.80; then
    python3 -I -B replay_stage.py --requests selected_requests.jsonl --stage both --model gpt-6-luna --select all --limit 12 --max-usd 0.80 --execute --results stage-results.jsonl
else
    exit "$?"
fi
