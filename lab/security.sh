#!/usr/bin/env bash
# Security controls on the running platform: secrets only in Vault, least-privilege Vault access,
# network isolation of the database, and hardened pods.
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/security.log
source lab/common.sh

# Secrets: none in Git, all copied from Vault
rec gitleaks git . --redact --no-banner
rec git check-ignore -v .vault-init.json
rec 'grep -rniE "password|secret_key|token" deploy/k8s | grep -vE "secretKeyRef|remoteRef|key: password|secretKey: password|ExternalSecret|SecretStore|textstats-secrets|serviceAccountRef|automountServiceAccountToken" || echo "no credential values in deploy/k8s"'
rec kubectl -n textstats get secretstore,externalsecret
rec "kubectl -n textstats get secret postgres-credentials -o json | jq -c '{name: .metadata.name, owner: .metadata.ownerReferences[0].kind, keys: (.data | keys)}'"
rec "curl -s -H \"X-Vault-Token: \$(jq -r .root_token .vault-init.json)\" http://vault.k8s.orb.local/v1/auth/kubernetes/role/textstats | jq -c '.data | {bound_service_account_names, bound_service_account_namespaces, policies, token_ttl}'"
# Least privilege: log in exactly like External Secrets does, then try a path outside the policy
rec 'tok=$(kubectl -n textstats create token textstats-secrets --audience vault --duration 10m)
vt=$(curl -s -X POST -d "{\"role\":\"textstats\",\"jwt\":\"$tok\"}" http://vault.k8s.orb.local/v1/auth/kubernetes/login | jq -r .auth.client_token)
echo "read secret/textstats/db       -> HTTP $(curl -s -o /dev/null -w %{http_code} -H "X-Vault-Token: $vt" http://vault.k8s.orb.local/v1/secret/data/textstats/db)"
echo "read secret/monitoring/grafana -> HTTP $(curl -s -o /dev/null -w %{http_code} -H "X-Vault-Token: $vt" http://vault.k8s.orb.local/v1/secret/data/monitoring/grafana)"
echo "write secret/textstats/db      -> HTTP $(curl -s -o /dev/null -w %{http_code} -X POST -d "{\"data\":{\"x\":\"y\"}}" -H "X-Vault-Token: $vt" http://vault.k8s.orb.local/v1/secret/data/textstats/db)"'

# Network policies: only the app and backup pods reach the database; only Traefik and Prometheus reach the app
rec kubectl -n textstats get networkpolicy
rec 'kubectl -n textstats exec deploy/traffic -- sh -c "curl -s -m 3 telnet://postgres:5432 </dev/null; echo traffic pod to postgres:5432 exit=\$? (28 = timed out, blocked)"'
rec 'kubectl -n textstats exec deploy/traffic -- sh -c "curl -s -m 3 -o /dev/null -w \"traffic pod to app pod directly: HTTP %{http_code}\" http://text-stats-stable/healthz; echo \" exit=\$?\""'
rec 'kubectl -n textstats exec deploy/traffic -- sh -c "curl -s -m 3 -o /dev/null -w \"traffic pod through Traefik: HTTP %{http_code}\n\" -H \"Host: textstats.k8s.orb.local\" http://traefik.traefik.svc/healthz"'
rec 'pod=$(kubectl -n textstats get pod -l app=text-stats -o jsonpath="{.items[0].metadata.name}"); kubectl -n textstats exec $pod -- python -c "import socket; socket.create_connection((\"postgres\", 5432), 3); print(\"app pod to postgres:5432 connected\")"'

# Hardened containers
rec "kubectl -n textstats get pods -o json | jq -r '.items[] | .metadata.name as \$p | .spec.containers[] | \"\(\$p)  user=\(.securityContext.runAsUser // \"image:\" + \"nonroot\")  readOnlyRoot=\(.securityContext.readOnlyRootFilesystem)  privEsc=\(.securityContext.allowPrivilegeEscalation)  drop=\(.securityContext.capabilities.drop // [] | join(\",\"))\"'"
rec 'pod=$(kubectl -n textstats get pod -l app=text-stats -o jsonpath="{.items[0].metadata.name}"); kubectl -n textstats exec $pod -- sh -c "id; touch /srv/text-stats/x 2>&1 || true"'
