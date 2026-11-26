# Shared helpers for the lab scripts: run from the repo root after sourcing lab/rec.sh.
SHOTS=evidence/screenshots
PROM=http://prometheus.k8s.orb.local
# instant PromQL query, one "labels value" line per series
prom() { curl -s --data-urlencode "query=$1" $PROM/api/v1/query | jq -r '.data.result[] | "\(.metric | del(.__name__) | to_entries | map("\(.key)=\(.value)") | join(",")) \(.value[1])"'; }
# screenshot a page in a real browser session (pages that stream data need a few seconds to render)
shot() { agent-browser set viewport 1500 950 >/dev/null 2>&1; agent-browser open "$2" >/dev/null 2>&1
  agent-browser wait "${3:-4000}" >/dev/null 2>&1; agent-browser screenshot "$SHOTS/$1.png" >/dev/null 2>&1 || true; }
rollout_state() { kubectl -n textstats get rollout text-stats -o jsonpath='step={.status.currentStepIndex} phase={.status.phase} pods={.status.replicas} new_version_pods={.status.updatedReplicas} canary_weight={.status.canary.weights.canary.weight} {.status.message}'; }
export -f prom rollout_state
export PROM
