#!/usr/bin/env bash
# Load test: 20 concurrent clients for 4 minutes; the HPA adds pods while CPU is above 60% of requests
# and removes them after the 2-minute stabilisation window once the load stops.
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/scaling.log
source lab/common.sh
hpa() { kubectl -n textstats get hpa text-stats -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}% cpu, replicas {.status.currentReplicas} -> {.status.desiredReplicas}'; }
export -f hpa
rec kubectl -n textstats get hpa text-stats
rec kubectl top pods -n textstats -l app=text-stats
rec "kubectl -n textstats delete job load --ignore-not-found >/dev/null; kubectl -n textstats create job load --image=curlimages/curl:8.23.0 -- sh -c 'end=\$((\$(date +%s)+240)); for i in \$(seq 20); do (while [ \$(date +%s) -lt \$end ]; do curl -s -o /dev/null -X POST -H \"Host: textstats.k8s.orb.local\" -H \"Content-Type: application/json\" -d \"{\\\"text\\\":\\\"load test sentence number \$i with a few more words to count\\\"}\" http://traefik.traefik.svc/stats; done) & done; wait'"
rec 'start=$(date +%s); last=""; while [ $(( $(date +%s) - start )) -lt 540 ]; do s=$(hpa); [ "$s" != "$last" ] && echo "$(date -u +%H:%M:%S) $s" && last=$s; sleep 5; done'
shot scaling-grafana "http://grafana.k8s.orb.local/d/textstats/text-stats-service?orgId=1&from=now-12m&to=now" 8000
rec kubectl -n textstats describe hpa text-stats '|' sed -n "'/Events:/,\$p'"
rec 'echo "5xx during the load test:"; prom "sum(increase(textstats_http_requests_total{route=\"/stats\",status=~\"5..\"}[10m])) or vector(0)"; echo "requests during the load test:"; prom "sum(increase(textstats_http_requests_total{route=\"/stats\"}[10m]))"'
rec kubectl -n textstats delete job load
