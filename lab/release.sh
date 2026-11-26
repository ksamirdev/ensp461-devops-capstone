#!/usr/bin/env bash
# Follows one release from the commit on main to the end of its canary.
#   lab/release.sh <name>      name labels the log and screenshots (e.g. good, bad)
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=$1
source lab/rec.sh evidence/logs/release-$NAME.log
source lab/common.sh
git fetch -q origin
SHA=$(git rev-parse origin/main)
DASH=http://rollouts.k8s.orb.local/rollouts/rollout/textstats/text-stats

rec git log -3 --format="'%h %an %ad %s'" --date=format:%H:%M:%S origin/main
rec git show --format= origin/main -- deploy/k8s
rec "until [ \"\$(kubectl -n argocd get application textstats -o jsonpath='{.status.sync.revision}')\" = $SHA ]; do sleep 2; done; echo \"Argo CD synced ${SHA:0:7} at \$(date -u +%H:%M:%S) without a manual sync\""

( until rollout_state | grep -qE '^step=2 |phase=Degraded'; do sleep 2; done; shot "release-$NAME-canary-10" "$DASH" ) &
SNAP=$!
rec 'last=""; while :; do s=$(rollout_state); [ "$s" != "$last" ] && echo "$(date -u +%H:%M:%S) $s" && last=$s
  case "$s" in *"phase=Healthy"*|*"phase=Degraded"*) break;; esac; sleep 2; done'
wait $SNAP || true
shot "release-$NAME-rollout" "$DASH"
rec kubectl argo rollouts get rollout text-stats -n textstats --no-color
rec "kubectl -n textstats get analysisrun --sort-by=.metadata.creationTimestamp -o json | jq -r '.items[-3:][] | .metadata.name as \$n | .status.metricResults[] | \"\(\$n)  \(.name)  phase=\(.phase)  values=\([.measurements[].value] | join(\" \"))\"'"
rec kubectl -n textstats get traefikservice text-stats -o jsonpath="'{range .spec.weighted.services[*]}{.name}={.weight} {end}'"
rec 'echo "requests/s by pod-template hash:"; prom "sum by (rollouts_pod_template_hash) (rate(textstats_http_requests_total{route=\"/stats\"}[1m]))"'
rec 'echo "5xx share by pod-template hash (2m):"; prom "sum by (rollouts_pod_template_hash) (rate(textstats_http_requests_total{route=\"/stats\",status=~\"5..\"}[2m])) / sum by (rollouts_pod_template_hash) (rate(textstats_http_requests_total{route=\"/stats\"}[2m]))"'
rec curl -s -H "'Host: textstats.k8s.orb.local'" http://localhost/
rec kubectl -n argocd get application textstats
