#!/bin/bash
cd /root/v2replay-20261013
KEY=""
for c in $(docker ps --format '{{.Names}}'); do
  v=$(docker exec "$c" printenv OPENAI_API_KEY 2>/dev/null || true)
  if [ -n "$v" ]; then KEY="$v"; break; fi
done
if [ -z "$KEY" ]; then echo KEIN_SCHLUESSEL > /root/v2replay-20261013/go.log; exit 3; fi
export OPENAI_API_KEY="$KEY"
echo "start $(date -u +%FT%TZ)" > /root/v2replay-20261013/go.log
sh ./run_on_server.sh > /root/v2replay-20261013/run.out 2>&1
echo "run exit=$?" >> /root/v2replay-20261013/go.log
echo FERTIG >> /root/v2replay-20261013/go.log
