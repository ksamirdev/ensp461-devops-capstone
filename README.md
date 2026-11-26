# ENSP461 Capstone - End-to-End DevOps Automation Platform

Author: Samir Kumar Gupta (Roll No. 2301730243)

The text-stats API from Labs 1-4 taken from a commit to production with no manual step.
GitHub Actions gates every change (tests, five security scans, image scan) and releases it by committing the new image tag.
Argo CD applies that commit, and Argo Rollouts ships it as a canary that Prometheus analysis can abort.
Ansible builds the whole platform; Vault holds every credential; Loki holds the logs; backups are verified and restorable.

Report: [reports/capstone-report.pdf](reports/capstone-report.pdf) (editable: [capstone-report.docx](reports/capstone-report.docx)).
Every command output in it is copied from [`evidence/logs/`](evidence/logs/), recorded by `lab/rec.sh` while the commands ran; screenshots are in [`evidence/screenshots/`](evidence/screenshots/).

## Results

- Pipeline: 2 of 12 runs blocked before publishing (4 manifest misconfigurations, 5 image CVEs); releases 1.0.0, 1.1.0, 1.2.0 published.
- Ansible: whole platform from one playbook; second run `ok=16 changed=0`.
- Canary: 1.2.0 promoted 10/30/60/100% about 4 minutes after its release commit; a faulty release (25% errors) aborted at 10% after 97 s, then reverted in Git.
- Incident: database stopped under traffic; critical alert paged 9 s after firing; Argo CD restored the database 8 s after self-heal was re-enabled.
- Recovery: killed pod replaced in 3 s with 0 failed requests; manual drift reverted in 2-18 s; table restored from backup in 9 s.
- Load: HPA 3 to 8 pods in 36 s; 0 errors in 57,108 requests.

## Layout

- `service/`, `tests/` - Flask API, unit, integration and smoke tests
- `Dockerfile` - multi-stage, non-root image with HEALTHCHECK
- `.github/workflows/ci-cd.yml` - the pipeline
- `infra/ansible/` - playbook and roles that build the platform
- `deploy/platform/` - Helm values, alert rules, Grafana dashboard
- `deploy/k8s/` - everything Argo CD keeps in sync in the `textstats` namespace
- `deploy/argocd/` - the Argo CD Application
- `lab/` - recorded drill scripts, restore script, report builder

## Running it

On a Kubernetes cluster (OrbStack here) with `helm`, `kubectl`, Ansible and the `kubernetes.core` collection:

```
cd infra/ansible && ansible-playbook site.yml   # platform, Vault, observability, then hand-over to Argo CD
bash lab/release.sh good                        # follow a release after a push to main
bash lab/incident.sh                            # database outage drill
bash lab/recovery.sh                            # drift and backup/restore drill
python3 lab/build_report.py                     # rebuild the report (Chrome, LibreOffice)
```

Vault's unseal keys and root token are written once to `.vault-init.json` (mode 600, gitignored).
