#!/bin/sh
# Only the two dedicated selfhost subnets; never alters host INPUT/UFW.
set -eu
chain=DASHBOARD-SUPABASE-EGRESS
iptables -S DOCKER-USER >/dev/null
if ! iptables -S "$chain" >/dev/null 2>&1; then
  iptables -N "$chain"
  iptables -A "$chain" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  iptables -A "$chain" -s 172.28.80.2/32 -p tcp --dport 587 -j RETURN
  iptables -A "$chain" -j DROP
fi
for subnet in 172.28.80.0/29 172.28.81.0/29; do
  if ! iptables -C DOCKER-USER -s "$subnet" -j "$chain" 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "$subnet" -j "$chain"
  fi
done
