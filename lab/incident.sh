#!/usr/bin/env bash
# Incident drill: the database goes down under live traffic. Shows the alert firing and being routed to
# the pager, the error lines in Loki, and Argo CD restoring the database from Git when self-heal is back on.
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/incident.log
source lab/common.sh
kubectl -n monitoring port-forward svc/loki 23100:3100 >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT
LOKI=http://127.0.0.1:23100
logq() { curl -s -G $LOKI/loki/api/v1/query_range --data-urlencode "query=$1" --data-urlencode "since=${2:-10m}" --data-urlencode limit=${3:-5} \
  | jq -r '.data.result[] | (.stream | "\(.pod // "") \(.level // "")") as $s | .values[] | "\($s)  \(.[1])"' | head -${3:-5}; }
export -f logq; export LOKI

rec 'echo "error ratio before:"; prom textstats:error_ratio:rate5m'
# A maintenance window: self-heal off, or Argo CD would put the database back within seconds
rec kubectl -n argocd patch application textstats --type merge -p "'{\"spec\":{\"syncPolicy\":{\"automated\":{\"selfHeal\":false}}}}'"
rec "kubectl -n textstats scale statefulset postgres --replicas=0 && date -u +'database stopped at %H:%M:%S'"
rec 'until [ "$(curl -s $PROM/api/v1/alerts | jq -r "[.data.alerts[] | select(.labels.alertname==\"TextstatsHighErrorRate\" and .state==\"firing\")] | length")" -gt 0 ]; do sleep 5; done; date -u +"TextstatsHighErrorRate firing at %H:%M:%S"'
rec "curl -s $PROM/api/v1/alerts | jq -r '.data.alerts[] | \"\(.labels.alertname)  severity=\(.labels.severity)  state=\(.state)  since=\(.activeAt[11:19])  \(.annotations.summary)\"'"
rec 'until kubectl -n monitoring logs deploy/alert-sink | grep -q "\"firing\", \"alertname\": \"TextstatsHighErrorRate\""; do sleep 3; done; kubectl -n monitoring logs deploy/alert-sink'
shot incident-alertmanager http://alertmanager.k8s.orb.local/#/alerts
shot incident-prometheus-alerts "http://prometheus.k8s.orb.local/alerts?search=textstats"
shot incident-grafana "http://grafana.k8s.orb.local/d/textstats/text-stats-service?orgId=1&from=now-15m&to=now&refresh=10s" 8000
rec 'echo "LogQL: {namespace=\"textstats\", app=\"text-stats\", level=\"error\"} | json | msg=\"database write failed\""; logq "{namespace=\"textstats\", app=\"text-stats\", level=\"error\"} | json | msg=\"database write failed\"" 5m 4'
rec 'echo "LogQL: sum by (level) (count_over_time({namespace=\"textstats\", app=\"text-stats\"}[5m]))"; curl -s -G $LOKI/loki/api/v1/query --data-urlencode "query=sum by (level) (count_over_time({namespace=\"textstats\", app=\"text-stats\"}[5m]))" | jq -r ".data.result[] | \"\(.metric.level)  \(.value[1])\""'
# Turning self-heal back on is the whole fix: Argo CD sees replicas 0 != 1 in Git and restores it
rec "kubectl -n argocd patch application textstats --type merge -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"selfHeal\":true}}}}' && date -u +'self-heal on at %H:%M:%S'"
rec 'until [ "$(kubectl -n textstats get statefulset postgres -o jsonpath="{.status.readyReplicas}")" = 1 ]; do sleep 2; done; date -u +"database ready again at %H:%M:%S (restored by Argo CD)"'
# the resolved notification must come after the firing one from this drill, not from an earlier incident
rec 'until kubectl -n monitoring logs deploy/alert-sink | sed -n "/\"firing\", \"alertname\": \"TextstatsHighErrorRate\"/,\$p" | tail -n +2 | grep -q "\"resolved\", \"alertname\": \"TextstatsHighErrorRate\""; do sleep 5; done; kubectl -n monitoring logs deploy/alert-sink | tail -2'
rec 'echo "5xx/s now:"; prom "sum(rate(textstats_http_requests_total{route=\"/stats\",status=~\"5..\"}[1m])) or vector(0)"'
