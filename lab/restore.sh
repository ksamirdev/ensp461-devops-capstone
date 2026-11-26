#!/usr/bin/env bash
# Restores a dump from the postgres-backups volume into the live database.
#   lab/restore.sh [textstats-YYYYMMDDTHHMMSSZ.dump | latest]
# After data loss, name the last dump taken BEFORE the incident: a scheduled backup that ran after it holds the loss too.
set -euo pipefail
DUMP=${1:-latest}
started=$(date +%s)
kubectl -n textstats delete job restore --ignore-not-found >/dev/null
kubectl -n textstats apply -f - >/dev/null <<YAML
apiVersion: batch/v1
kind: Job
metadata: {name: restore}
spec:
  backoffLimit: 0
  template:
    metadata:
      labels: {app: postgres-backup}   # the network policy lets backup pods reach the database
    spec:
      restartPolicy: Never
      securityContext: {runAsNonRoot: true, runAsUser: 999, fsGroup: 999, seccompProfile: {type: RuntimeDefault}}
      containers:
        - name: restore
          image: mirror.gcr.io/library/postgres:18
          env:
            - {name: PGUSER, valueFrom: {secretKeyRef: {name: postgres-credentials, key: username}}}
            - {name: PGPASSWORD, valueFrom: {secretKeyRef: {name: postgres-credentials, key: password}}}
            - {name: PGHOST, value: postgres}
            - {name: PGDATABASE, value: textstats}
          command: [sh, -ec]
          args:
            - |
              f=\$( [ "$DUMP" = latest ] && ls -1t /backups/*.dump | head -1 || echo /backups/$DUMP )
              # the network policy admits a new pod's IP a few seconds after it starts
              until pg_isready -q -t 2; do sleep 1; done
              echo "restoring \$f"
              pg_restore --clean --if-exists --no-owner --single-transaction --dbname=textstats "\$f"
              echo "restore ok"
          securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
          volumeMounts: [{name: backups, mountPath: /backups, readOnly: true}]
      volumes:
        - {name: backups, persistentVolumeClaim: {claimName: postgres-backups}}
YAML
until [ "$(kubectl -n textstats get job restore -o jsonpath='{.status.succeeded}{.status.failed}')" != "" ]; do sleep 1; done
[ "$(kubectl -n textstats get job restore -o jsonpath='{.status.succeeded}')" = 1 ] \
  || { kubectl -n textstats logs job/restore; echo "restore FAILED"; exit 1; }
kubectl -n textstats logs job/restore
echo "restore took $(( $(date +%s) - started )) s"
