#!/usr/bin/env bash
# Builds the platform with Ansible, then runs the playbook a second time to prove it is idempotent.
#   lab/platform.sh [ansible tags]
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/platform.log
TAGS=${1:-all}
rec kubectl config current-context
rec kubectl get nodes -o wide
rec "cd infra/ansible && ANSIBLE_FORCE_COLOR=0 ansible-playbook site.yml --tags $TAGS"
