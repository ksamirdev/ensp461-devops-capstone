# Shared helpers for the lab scripts: run from the repo root after sourcing lab/rec.sh.
SHOTS=evidence/screenshots
PROM=http://prometheus.k8s.orb.local
# instant PromQL query, one "labels value" line per series
prom() { curl -s --data-urlencode "query=$1" $PROM/api/v1/query | jq -r '.data.result[] | "\(.metric | del(.__name__) | to_entries | map("\(.key)=\(.value)") | join(",")) \(.value[1])"'; }
# screenshot a page in a real browser session of its own; the browser's resolver does not see OrbStack's
# *.k8s.orb.local names, so they are mapped to Traefik on 127.0.0.1 (the Host header still picks the route)
export AGENT_BROWSER_SESSION=capstone AGENT_BROWSER_ARGS="--host-resolver-rules=MAP *.k8s.orb.local 127.0.0.1"
shot() { { agent-browser set viewport 1500 950 && agent-browser open "$2" && agent-browser wait "${3:-9000}" \
  && agent-browser screenshot "$SHOTS/$1.png"; } >/dev/null 2>&1 || echo "screenshot $1 failed" >&2; }
rollout_state() { kubectl -n textstats get rollout text-stats -o jsonpath='step={.status.currentStepIndex} phase={.status.phase} pods={.status.replicas} new_version_pods={.status.updatedReplicas} canary_weight={.status.canary.weights.canary.weight} {.status.message}'; }
export -f prom rollout_state
export PROM
