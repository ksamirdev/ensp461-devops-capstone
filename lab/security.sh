#!/usr/bin/env bash
# Security controls on the running platform: secrets only in Vault, least-privilege Vault access,
# network isolation of the database, and hardened pods.
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/security.log
source lab/common.sh

# Secrets: none in Git, all copied from Vault
rec gitleaks git . --redact --no-banner --no-color
rec git check-ignore -v .vault-init.json
rec kubectl -n textstats get secretstore,externalsecret
rec "kubectl -n textstats get secret postgres-credentials -o json | jq -c '{name: .metadata.name, owner: .metadata.ownerReferences[0].kind, keys: (.data | keys)}'"
# Least privilege: log in exactly like External Secrets does, then try a path outside the policy
rec 'tok=$(kubectl -n textstats create token textstats-secrets --audience vault --duration 10m)
vt=$(curl -s -X POST -d "{\"role\":\"textstats\",\"jwt\":\"$tok\"}" http://vault.k8s.orb.local/v1/auth/kubernetes/login | jq -r .auth.client_token)
echo "read secret/textstats/db       -> HTTP $(curl -s -o /dev/null -w %{http_code} -H "X-Vault-Token: $vt" http://vault.k8s.orb.local/v1/secret/data/textstats/db)"
echo "read secret/monitoring/grafana -> HTTP $(curl -s -o /dev/null -w %{http_code} -H "X-Vault-Token: $vt" http://vault.k8s.orb.local/v1/secret/data/monitoring/grafana)"
echo "write secret/textstats/db      -> HTTP $(curl -s -o /dev/null -w %{http_code} -X POST -d "{\"data\":{\"x\":\"y\"}}" -H "X-Vault-Token: $vt" http://vault.k8s.orb.local/v1/secret/data/textstats/db)"'

# Network policies: only the app and backup pods reach the database; only Traefik and Prometheus reach the app
rec kubectl -n textstats get networkpolicy
rec 'kubectl -n textstats exec deploy/traffic -- sh -c "curl -s -m 3 telnet://postgres:5432 </dev/null; echo \"traffic pod to postgres:5432 curl exit=\$? (7 = refused, 28 = timed out)\""'
rec 'kubectl -n textstats exec deploy/traffic -- sh -c "curl -s -m 3 -o /dev/null -w \"traffic pod to app pod directly: HTTP %{http_code}\" http://text-stats-stable/healthz; echo \" exit=\$?\""'
rec 'kubectl -n textstats exec deploy/traffic -- sh -c "curl -s -m 3 -o /dev/null -w \"traffic pod through Traefik: HTTP %{http_code}\n\" -H \"Host: textstats.k8s.orb.local\" http://traefik.traefik.svc/healthz"'
rec 'pod=$(kubectl -n textstats get pod -l app=text-stats -o jsonpath="{.items[0].metadata.name}"); kubectl -n textstats exec $pod -- python -c "import socket; socket.create_connection((\"postgres\", 5432), 3); print(\"app pod to postgres:5432 connected\")"'

# Hardened containers
rec "kubectl -n textstats get pods -o json | jq -r '.items[] | .metadata.name as \$p | .spec.securityContext.runAsNonRoot as \$nr | .spec.containers[] | \"\\(\$p)  runAsNonRoot=\\(.securityContext.runAsNonRoot // \$nr)  readOnlyRoot=\\(.securityContext.readOnlyRootFilesystem)  privEsc=\\(.securityContext.allowPrivilegeEscalation)  drop=\\(.securityContext.capabilities.drop // [] | join(\",\"))\"'"
rec 'pod=$(kubectl -n textstats get pod -l app=text-stats -o jsonpath="{.items[0].metadata.name}"); kubectl -n textstats exec $pod -- sh -c "id; touch /srv/text-stats/x 2>&1 || true"'
