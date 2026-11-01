#!/bin/bash
cd /root/v13-delta-20261013
KEY=""
for c in $(docker ps --format '{{.Names}}'); do
  v=$(docker exec "$c" printenv OPENAI_API_KEY 2>/dev/null || true)
  if [ -n "$v" ]; then KEY="$v"; break; fi
done
if [ -z "$KEY" ]; then echo KEIN_SCHLUESSEL > go.log; exit 3; fi
export OPENAI_API_KEY="$KEY"
echo "start $(date -u +%FT%TZ)" > go.log
sh ./run_delta_on_server.sh > run.out 2>&1
echo "run exit=$?" >> go.log
echo FERTIG >> go.log
