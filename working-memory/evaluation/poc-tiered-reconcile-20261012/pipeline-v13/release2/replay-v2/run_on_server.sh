#!/bin/sh
cd "$(dirname "$0")" || exit 1
exec >run.out 2>&1
python3 -I -B replay_v2.py --max-usd 1.30
dry_status=$?
if [ "$dry_status" -ne 0 ]; then
    exit "$dry_status"
fi
python3 -I -B replay_v2.py --execute --max-usd 1.30
execute_status=$?
python3 -I -B compare_v2.py > comparison.json
compare_status=$?
cat comparison.json
if [ "$execute_status" -ne 0 ]; then
    exit "$execute_status"
fi
exit "$compare_status"
