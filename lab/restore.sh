#!/usr/bin/env bash
# Restores the newest (or the given) dump from the postgres-backups volume into the live database.
#   lab/restore.sh [textstats-YYYYMMDDTHHMMSSZ.dump]
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
              echo "restoring \$f"
              pg_restore --clean --if-exists --no-owner --single-transaction --dbname=textstats "\$f"
              echo "restore ok"
          securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
          volumeMounts: [{name: backups, mountPath: /backups, readOnly: true}]
      volumes:
        - {name: backups, persistentVolumeClaim: {claimName: postgres-backups}}
YAML
kubectl -n textstats wait --for=condition=complete job/restore --timeout=180s >/dev/null
kubectl -n textstats logs job/restore
echo "restore took $(( $(date +%s) - started )) s"
