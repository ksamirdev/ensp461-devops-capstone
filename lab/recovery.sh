#!/usr/bin/env bash
# Recoverability: self-healing pods, GitOps drift correction, and database backup + restore.
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/recovery.log
source lab/common.sh
fivexx() { prom 'sum(increase(textstats_http_requests_total{route="/stats",status=~"5.."}[2m])) or vector(0)' | awk '{printf "%.0f\n", $NF}'; }
export -f fivexx

# 1. A pod dies: the ReplicaSet replaces it and readiness keeps users off it until it can serve
rec kubectl -n textstats get pods -l app=text-stats -o wide
rec 'victim=$(kubectl -n textstats get pods -l app=text-stats -o jsonpath="{.items[0].metadata.name}"); kubectl -n textstats delete pod $victim --wait=false; date -u +"deleted $victim at %H:%M:%S"'
rec 'until [ "$(kubectl -n textstats get rollout text-stats -o jsonpath="{.status.readyReplicas}")" = "$(kubectl -n textstats get rollout text-stats -o jsonpath="{.spec.replicas}")" ]; do sleep 1; done; date -u +"all replicas ready again at %H:%M:%S"'
rec kubectl -n textstats get pods -l app=text-stats
rec 'sleep 30; echo "5xx responses in the last 2 minutes: $(fivexx)"'

# 2. Someone edits the cluster by hand: Argo CD puts it back to what Git says
rec "kubectl -n textstats delete service text-stats-stable && date -u +'deleted Service text-stats-stable at %H:%M:%S'"
rec 'until kubectl -n textstats get service text-stats-stable >/dev/null 2>&1; do sleep 1; done; date -u +"Service recreated by Argo CD at %H:%M:%S"'
rec "kubectl -n textstats patch cronjob postgres-backup -p '{\"spec\":{\"schedule\":\"0 0 1 1 *\"}}' && date -u +'backup schedule changed by hand at %H:%M:%S'"
rec 'until [ "$(kubectl -n textstats get cronjob postgres-backup -o jsonpath="{.spec.schedule}")" = "*/10 * * * *" ]; do sleep 1; done; date -u +"schedule reverted to */10 by Argo CD at %H:%M:%S"'
rec kubectl -n argocd get application textstats

# 3. Data loss: back up, lose the table, restore from the newest dump
sql() { kubectl -n textstats exec postgres-0 -- sh -c "psql -U \$POSTGRES_USER -d textstats -c \"$1\""; }
export -f sql
rec "kubectl -n textstats create job backup-now --from=cronjob/postgres-backup && kubectl -n textstats wait --for=condition=complete job/backup-now --timeout=120s && kubectl -n textstats logs job/backup-now"
rec sql "'select count(*) as rows_before, max(id) as last_id, max(created_at) as newest_row from analyses'"
rec "date -u +'table dropped at %H:%M:%S'; sql 'drop table analyses'"
rec 'sleep 10; curl -s -o /dev/null -w "POST /stats after the drop: HTTP %{http_code}\n" -X POST -H "Host: textstats.k8s.orb.local" -H "Content-Type: application/json" -d "{\"text\":\"x\"}" http://localhost/stats'
rec bash lab/restore.sh
rec sql "'select count(*) as rows_after, max(id) as last_id, max(created_at) as newest_row from analyses'"
rec 'sleep 5; curl -s -w "\nPOST /stats after the restore: HTTP %{http_code}\n" -X POST -H "Host: textstats.k8s.orb.local" -H "Content-Type: application/json" -d "{\"text\":\"after restore\"}" http://localhost/stats'
