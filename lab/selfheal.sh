#!/usr/bin/env bash
# A pod dies under live traffic: the ReplicaSet replaces it, and readiness keeps users off the new pod until it can serve.
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/selfheal.log
source lab/common.sh
fivexx() { prom 'sum(increase(textstats_http_requests_total{route="/stats",status=~"5.."}[2m])) or vector(0)' | awk '{printf "%.0f\n", $NF}'; }
export -f fivexx

rec kubectl -n textstats get pods -l app=text-stats -o wide
rec 'echo "5xx responses in the 2 minutes before: $(fivexx)"'
rec 'victim=$(kubectl -n textstats get pods -l app=text-stats -o jsonpath="{.items[0].metadata.name}"); kubectl -n textstats delete pod $victim --grace-period=0 --force 2>/dev/null; date -u +"killed $victim at %H:%M:%S"
  until [ "$(kubectl -n textstats get pods -l app=text-stats --no-headers | grep -v $victim | grep -c " 1/1 ")" = "$(kubectl -n textstats get rollout text-stats -o jsonpath="{.spec.replicas}")" ]; do sleep 1; done
  date -u +"replacement pod ready at %H:%M:%S"'
rec kubectl -n textstats get pods -l app=text-stats
rec 'sleep 90; echo "5xx responses in the 2 minutes around the kill: $(fivexx)"'
