"""Capstone report content. Every number quoted here comes from evidence/logs or a screenshot in evidence/screenshots."""
from build_report import REPO, ROOT, bullets, config, esc, shot, table, term

TITLE = "Capstone - End-to-End DevOps Automation Platform"

INTRO = (
    '<p class="question"><b>Project:</b> build a platform that takes an application from a commit to production '
    "automatically and safely, covering version control, CI/CD, containerization, Kubernetes orchestration, "
    "infrastructure automation, monitoring and alerting, centralized logging, security and secrets, an advanced "
    "deployment strategy, and recoverability.</p>"
    "<p>Everything below ran on the lab cluster between 07:20 and 09:15 UTC on 26 November 2026. Command output is "
    "copied verbatim from the logs in <code>evidence/logs/</code>, which <code>lab/rec.sh</code> recorded while the "
    f'commands ran. Repository: <a href="{REPO}">{REPO}</a>.</p>'
)


def svg(path, caption):
    return f'<figure>{(ROOT / path).read_text()}<figcaption>{esc(caption)}</figcaption></figure>'


def overview():
    return "".join([
        "<h2>1. What was built</h2>",
        "<p>The application is <b>text-stats</b>, the text-statistics API carried through Labs 1-4, now a Flask 3.1 service "
        "on PostgreSQL 18. <code>POST /stats</code> counts characters, words, unique words and (since 1.1.0) sentences and "
        "stores each analysis; <code>/healthz</code>, <code>/readyz</code> and <code>/metrics</code> serve the platform. "
        "Every request writes one JSON log line with a request id.</p>",
        table(
            ["Requirement", "How it is met", "Where"],
            [
                ["Version control", "Git on <code>main</code>, one commit per change; releases and rollbacks are commits too",
                 "GitHub repository"],
                ["CI/CD pipeline", "6 gated jobs: quality, security, integration, image build + scan, publish, GitOps release",
                 "<code>.github/workflows/ci-cd.yml</code>"],
                ["Containerization", "Multi-stage image, non-root user 10001, HEALTHCHECK, no pip in the runtime",
                 "<code>Dockerfile</code>"],
                ["Orchestration", "Rollout (3-8 pods, HPA), PDB, StatefulSet + PVC, CronJob, probes, resource limits",
                 "<code>deploy/k8s/</code>"],
                ["Infrastructure automation", "One idempotent Ansible playbook builds the whole platform from an empty cluster",
                 "<code>infra/ansible/</code>"],
                ["Monitoring and alerting", "Prometheus, SLO recording rules, 5 alert rules, Alertmanager routing, Grafana",
                 "<code>deploy/platform/</code>"],
                ["Centralized logging", "Grafana Alloy ships container logs to Loki; JSON fields queried with LogQL",
                 "<code>deploy/platform/alloy-values.yaml</code>"],
                ["Security", "Secret, SAST, dependency, IaC and image scans as gates; Vault; network policies; hardened pods",
                 "pipeline, <code>deploy/k8s/</code>"],
                ["Advanced deployment", "Canary 10/30/60/100% with Traefik weights and automated Prometheus analysis",
                 "<code>deploy/k8s/app.yaml</code>"],
                ["Recoverability", "Self-healing, GitOps drift correction, 10-minute backups with tested restore",
                 "<code>deploy/k8s/backup.yaml</code>, <code>lab/restore.sh</code>"],
            ],
        ),
        "<h2>2. Architecture</h2>",
        svg("lab/architecture.svg", "Figure 1 - Platform architecture. Solid arrows: requests and data; dashed: the GitOps pull."),
        "<p>GitHub never pushes into the cluster. The pipeline's last job only <i>commits</i> the new image tag to "
        "<code>deploy/k8s/kustomization.yaml</code>; Argo CD, running inside the cluster, polls that folder and applies it. "
        "So the cluster needs no inbound access and no cluster credentials are stored in GitHub, and Git holds the full "
        "history of what ran in production.</p>",
        shot("argocd-tree", "Figure 2 - Argo CD after the last change: Synced to main and Healthy; every object in the namespace comes from Git"),
        "<h3>Commit to production</h3>",
        table(
            ["#", "Stage", "Tooling", "Stops the release when"],
            [
                ["1", "Commit", "Git, GitHub", "-"],
                ["2", "Quality gate", "ruff, pytest (22 unit tests, coverage &ge; 75%)", "lint error, failing test, low coverage"],
                ["3", "Security gate", "gitleaks, bandit, pip-audit, trivy config", "secret in history, SAST issue, known CVE, HIGH misconfiguration"],
                ["4", "Integration gate", "pytest against PostgreSQL 18 (5 tests)", "the API and the database disagree"],
                ["5", "Image gate", "docker build, trivy image, smoke test", "fixable HIGH/CRITICAL CVE, container not healthy"],
                ["6", "Publish", "GHCR, tags <code>1.2.0</code> and <code>sha-&lt;commit&gt;</code>", "release tag already exists (immutable)"],
                ["7", "Release", "bot commit to <code>deploy/k8s</code>", "-"],
                ["8", "Canary", "Argo CD + Argo Rollouts + Traefik + Prometheus", "5xx ratio &gt; 2% or p95 &ge; 250 ms on the canary"],
                ["9", "Operate", "HPA, alerts, Loki, backups", "alerts page the on-call receiver"],
            ],
        ),
    ])


def cicd():
    log = "cicd.log"
    return "".join([
        "<h2>3. CI/CD pipeline</h2>",
        "<p>Jobs are chained with <code>needs:</code>, so a job runs only when the jobs before it passed. Quality and security "
        "run in parallel; the image is built only after both, and published only from <code>main</code>.</p>",
        config(".github/workflows/ci-cd.yml", start="  security:", end="  integration:",
               label=".github/workflows/ci-cd.yml (security job; full file in the repository)"),
        config(".github/workflows/ci-cd.yml", start="  deliver:", label=".github/workflows/ci-cd.yml (deliver job)"),
        "<h3>Every run on main</h3>",
        term(log, "gh run list", label="UTC start time, commit, result, commit message"),
        "<p>The gates stopped two real problems before anything was published:</p>",
        term(log, "45775381064 --log-failed", label="Run 1 (commit a5d6cfe): the IaC scan found 4 HIGH misconfigurations in the manifests"),
        term(log, "45775846683 --log-failed", label="Run 2 (commit b49fb47): manifests fixed, but the image scan found 5 HIGH CVEs"),
        "<p>The CVEs were not in the application's dependencies but in pip's own vendored copies of urllib3 and msgpack, "
        "left in the virtualenv. The fix was to uninstall pip from the virtualenv in the build stage "
        "(commit 55991a3); the next run published 1.0.0. A third push, a31e2a8, contained a failing unit test; it was "
        "superseded 13 s later by the fix 8f8a337; its run was still queued behind the previous one and the workflow's "
        "concurrency group cancelled it in favour of the newer commit, so it never reached the unit-test gate.</p>",
        term(log, "45778488727 --json", "45778488727 --log", label="A green run: all six jobs, then the bot's release commit"),
        term(log, "git log --format"),
        shot("cicd-runs", "Figure 3 - GitHub Actions: every run of the ci-cd workflow on main"),
        shot("cicd-run-green", "Figure 4 - A green run: quality and security in parallel, then integration, build, publish and release"),
        shot("cicd-run-blocked", "Figure 5 - The first run: the security job failed, so build, publish and release were skipped"),
    ])


def container():
    return "".join([
        "<h2>4. Containerization</h2>",
        config("Dockerfile"),
        bullets(
            "<b>Two stages:</b> dependencies are installed in a build stage; the runtime stage copies only the virtualenv and "
            "the code. pip, setuptools and wheel are removed from both the system Python and the virtualenv.",
            "<b>Non-root:</b> runs as uid 10001; Kubernetes additionally enforces <code>runAsNonRoot</code>, a read-only root "
            "filesystem, no privilege escalation, all capabilities dropped and the RuntimeDefault seccomp profile.",
            "<b>Health:</b> the image HEALTHCHECK calls <code>/healthz</code>; the pipeline's smoke test waits for "
            "<code>healthy</code> before testing a real request.",
            "<b>Size:</b> 175 MB for the arm64 image, of which the Python 3.13 slim base is most.",
        ),
    ])


def ansible():
    log = "platform.log"
    return "".join([
        "<h2>5. Infrastructure automation (Ansible)</h2>",
        "<p>One playbook builds everything around the application: ten Helm releases at pinned chart versions, Vault "
        "initialisation, unsealing and configuration, the observability stack, and finally the Argo CD Application that "
        "hands the app over to GitOps. It talks to the Kubernetes API and Helm from the control node, so the inventory is "
        "<code>localhost</code>. Each role reads current state first and changes only what differs, so a second run "
        "changes nothing.</p>",
        config("infra/ansible/site.yml"),
        config("infra/ansible/group_vars/all.yml", start="charts:", end="helm_repos:", label="infra/ansible/group_vars/all.yml (pinned versions)"),
        term(log, "--tags platform,vault,observability", head=4, tail=27,
             label="First run on the cluster (vault, observability); the platform releases were already installed by an earlier attempt"),
        term(log, "--tags gitops", tail=9),
        term(log, "ansible-playbook site.yml\n", "ANSIBLE_FORCE_COLOR=0 ansible-playbook site.yml", pick=slice(2, 3), tail=17,
             label="Second full run: ok=16, changed=0 - the cluster already matches the playbook"),
        "<p>The playbook was also what recovered the platform after the OrbStack VM was restarted with more memory: Vault "
        "comes back sealed after every restart, and the <code>vault</code> role unsealed it with three of the five key shares.</p>",
    ])


def k8s():
    return "".join([
        "<h2>6. Kubernetes orchestration</h2>",
        table(
            ["Object", "Purpose"],
            [
                ["Rollout <code>text-stats</code>", "the app; canary strategy, probes, limits, hardened security context"],
                ["HorizontalPodAutoscaler", "3 to 8 pods at 60% of the CPU request; 2-minute scale-down window"],
                ["PodDisruptionBudget", "voluntary disruptions take at most one app pod at a time"],
                ["StatefulSet <code>postgres</code> + PVC", "PostgreSQL 18 data on a persistent volume"],
                ["CronJob <code>postgres-backup</code> + PVC", "pg_dump every 10 minutes, verified, 24 kept"],
                ["Services, TraefikService, IngressRoute", "stable and canary Services, weighted between by Traefik"],
                ["NetworkPolicies", "default deny; only the paths in section 8 are open"],
                ["ExternalSecrets, SecretStore", "database credentials from Vault"],
            ],
        ),
        config("deploy/k8s/app.yaml", start="  template:", end="  strategy:", label="deploy/k8s/app.yaml (pod template)"),
        "<p>Readiness uses <code>/healthz</code>, not <code>/readyz</code>: if the database fails, every pod keeps answering "
        "(503 on writes) instead of all leaving the Service at once. The errors then stay visible in the application's own "
        "metrics, which is what the alert in section 9 relies on.</p>",
    ])


def secrets():
    log = "security.log"
    return "".join([
        "<h2>7. Secret management</h2>",
        "<p>No credential exists in Git or in a manifest. Ansible generates each password (40 random characters) straight "
        "into Vault without printing it. External Secrets logs in to Vault with a 15-minute token bound to one service "
        "account in one namespace and copies the values into Kubernetes Secrets every minute. Vault's unseal keys and root "
        "token exist only in <code>.vault-init.json</code> on the control node (mode 600, gitignored).</p>",
        config("infra/ansible/roles/vault/defaults/main.yml"),
        config("deploy/k8s/secrets.yaml", start="kind: ExternalSecret", end="---", label="deploy/k8s/secrets.yaml (one of two ExternalSecrets)"),
        term(log, "gitleaks", "check-ignore", "get secretstore", "get secret postgres-credentials"),
        "<p>Least privilege, checked the way External Secrets itself logs in: the <code>textstats</code> role can read its "
        "own path and nothing else, and cannot write.</p>",
        term(log, "tok=$(kubectl"),
    ])


def network():
    log = "security.log"
    return "".join([
        "<h2>8. Network policies and hardened pods</h2>",
        config("deploy/k8s/network-policies.yaml", start="# The database", label="deploy/k8s/network-policies.yaml (database policy)"),
        term(log, "get networkpolicy", "telnet://postgres", "text-stats-stable/healthz", "through Traefik", "create_connection"),
        "<p>Only the app and the backup job reach the database; the traffic generator, which sits in the same namespace, "
        "cannot. Users and Prometheus reach the app only through their own paths.</p>",
        term(log, "securityContext.runAsUser", "id; touch"),
    ])


def monitoring():
    log = "incident.log"
    return "".join([
        "<h2>9. Monitoring and alerting</h2>",
        "<p>Prometheus scrapes every annotated pod every 10 s; pod labels become series labels, so canary and stable pods are "
        "told apart by <code>rollouts_pod_template_hash</code>. Recording rules compute the SLIs once; alerts and the "
        "dashboard reuse them. The availability SLO is 99.5% of <code>/stats</code> requests over 30 days.</p>",
        config("deploy/platform/prometheus-values.yaml", start="  alerting_rules.yml:", end="          - alert: TextstatsPodRestarting",
               label="deploy/platform/prometheus-values.yaml (first three of five alert rules)"),
        table(
            ["Alert", "Condition", "Severity", "Routed to"],
            [
                ["TextstatsHighErrorRate", "5xx ratio &gt; 5% for 2 min", "critical", "pager"],
                ["TextstatsDown", "no app pod answers scrapes for 1 min", "critical", "pager"],
                ["TextstatsHighLatency", "p95 &gt; 250 ms for 5 min", "warning", "chat"],
                ["TextstatsPodRestarting", "&gt; 2 restarts in 15 min", "warning", "chat"],
                ["PostgresBackupStale", "no successful backup for 30 min", "warning", "chat"],
            ],
        ),
        "<p>Alert fatigue is limited by grouping per alert and namespace, a 4-hour repeat for warnings, and an inhibit rule: "
        "while <code>TextstatsDown</code> fires, the warnings it causes are suppressed. Both receivers are webhooks into "
        "<code>alert-sink</code>, a stand-in for PagerDuty and Slack that logs every notification it gets.</p>",
        "<h3>Incident drill: the database goes down under live traffic</h3>",
        "<p>Argo CD's self-heal is switched off for the drill (otherwise it would restore the database within seconds), "
        "then PostgreSQL is scaled to zero while the traffic generator keeps writing.</p>",
        term(log, "error ratio before", "selfHeal\":false", "scale statefulset", "firing at", "api/v1/alerts"),
        term(log, "alert-sink | grep -q", tail=2, label="alert-sink log: the critical alert reached the pager receiver 9 s after it started firing"),
        shot("incident-grafana", "Figure 6 - Grafana during the drill: 503s replace 200s, latency rises to the 2.5 s connect timeout, one alert firing"),
        shot("incident-alertmanager", "Figure 7 - Alertmanager: the critical alert, grouped and routed to oncall-pager"),
        "<p>Recovery is a GitOps action: turning self-heal back on makes Argo CD compare the cluster with Git (1 database "
        "replica) and restore it. The alert resolves by itself once the 5-minute error ratio falls under 5%.</p>",
        term(log, "selfHeal\":true", "database ready again", "resolution", "sed -n", "5xx/s now"),
    ])


def logging():
    log = "incident.log"
    return "".join([
        "<h2>10. Centralized logging</h2>",
        "<p>Grafana Alloy discovers pods through the Kubernetes API, reads their logs, promotes only the JSON "
        "<code>level</code> field to a label (labels stay low-cardinality: namespace, app, pod, container, level) and pushes "
        "to Loki, which keeps 7 days. Request fields such as <code>request_id</code> and <code>route</code> stay in the line "
        "and are filtered at query time with <code>| json</code>.</p>",
        config("deploy/platform/alloy-values.yaml", start="      // Promote", end="      loki.write",
               label="deploy/platform/alloy-values.yaml (processing stage)"),
        "<p>During the incident the logs answered the question the alert raises: which requests failed and why.</p>",
        term(log, "LogQL: {namespace"),
        term(log, "LogQL: sum by (level)"),
    ])


def canary():
    good, bad = "release-good.log", "release-bad.log"
    return "".join([
        "<h2>11. Advanced deployment: automated canary</h2>",
        "<p>A release is a change to the pod template. Argo Rollouts then starts the new version beside the old one and moves "
        "Traefik's weights 10% &rarr; 30% &rarr; 60% &rarr; 100%. After each step an AnalysisRun queries Prometheus three "
        "times, 20 s apart, for the canary pods only; more than one failed measurement aborts the release and returns all "
        "traffic to the stable version.</p>",
        config("deploy/k8s/app.yaml", start="  strategy:", end="---", label="deploy/k8s/app.yaml (canary strategy)"),
        config("deploy/k8s/app.yaml", start="  metrics:", end="---", label="deploy/k8s/app.yaml (AnalysisTemplate metrics)"),
        "<h3>A good release: 1.2.0</h3>",
        "<p>Release 1.2.0 (reject bodies over 100 KB with 413) went through the full pipeline; the bot committed the new tag "
        "and Argo CD applied it with no manual step. The recording starts at the 10% step: Argo CD had already synced the "
        "commit by the time recording began, right after the OrbStack restart.</p>",
        term(good, "git log -3", "git show"),
        term(good, "while :"),
        term(good, "analysisrun", "traefikservice"),
        shot("release-good-canary-10", "Figure 8 - Argo Rollouts dashboard: 1.2.0 at the 10% step, its first analysis running"),
        "<h3>A faulty release: aborted at 10%, then reverted in Git</h3>",
        "<p>The drill commit sets <code>FAULT_RATE=0.25</code>, so a quarter of the canary's <code>/stats</code> requests fail. "
        "It shipped through the same path as any release.</p>",
        term(bad, "git show", "Argo CD synced aeca08a"),
        term(bad, "while :"),
        term(bad, "analysisrun", "traefikservice", "curl -s -H"),
        "<p>The first analysis measured a 33% and then a 30% error rate on the canary (and 0.70 s / 1.75 s p95), so the "
        "rollout was aborted 97 s after it began; only the 10% of requests routed to the canary were affected. The stable "
        "version kept serving 1.1.0. Because Git still described the faulty version, the rollback was completed in Git, "
        "so Git and the cluster agree again:</p>",
        term(bad, "git log -1", "Argo CD synced 58b57a1", "phase}\" | grep -q Healthy", "get application textstats", pick=slice(-4, None)),
        shot("release-bad-rollout", "Figure 9 - The aborted release: revision 3's analysis failed, the canary was scaled down"),
    ])


def recovery():
    log = "recovery.log"
    return "".join([
        "<h2>12. Recoverability</h2>",
        "<h3>Self-healing and drift correction</h3>",
        "<p>One of three pods is force-killed (no graceful shutdown) under the steady synthetic traffic:</p>",
        term("selfheal.log", "get pods -l app=text-stats -o wide", "before", "victim=", "around the kill"),
        "<p>The ReplicaSet had a replacement ready 3 s later and not one request failed: the Service only routes to ready pods.</p>",
        term(log, "delete service", "recreated by Argo CD", "patch cronjob", "reverted to", "get application"),
        "<p>A deleted Service came back in 2 s and a hand-edited backup schedule was reverted in 18 s: the cluster cannot "
        "drift from Git for longer than one Argo CD reconciliation.</p>",
        "<h3>Backup and restore after data loss</h3>",
        config("deploy/k8s/backup.yaml", start="              args:", end="              resources:", label="deploy/k8s/backup.yaml (backup command)"),
        term(log, "create job backup-now", "rows_before", "table dropped", "after the drop", "logs job/backup-now", "lab/restore.sh", "rows_after", "after the restore"),
        "<p>The dump was taken at 08:27:08 and the table dropped at 08:27:13, so the restore brought back everything except "
        "the writes of those 5 s (RPO); the 10-minute schedule bounds that loss in general. The restore itself took 9 s, and writes worked again without "
        "restarting the app.</p>",
        "<p>The first attempt at this drill (kept in <code>evidence/logs/recovery-first-attempt.log</code>) went wrong twice "
        "and changed the restore procedure: the restore pod was refused by the network policy for its first seconds, and the "
        "&quot;newest&quot; dump it then restored had been taken by the 10-minute schedule <i>after</i> the drop, so it held "
        "no table either. <code>lab/restore.sh</code> now waits for the database to accept it and must be given the last "
        "dump from before the incident.</p>",
        "<p>The same cause was behind two failed scheduled backups found afterwards (Argo CD reported the CronJob as "
        "Degraded): a new backup pod could be refused for its first second, and three quick retries were not enough. The "
        "CronJob now waits for <code>pg_isready</code> before dumping:</p>",
        term(log, "backup-check"),
    ])


def scaling():
    log = "scaling.log"
    return "".join([
        "<h2>13. Autoscaling under load</h2>",
        "<p>A Job runs 20 concurrent clients against <code>/stats</code> through Traefik for 4 minutes, on top of the "
        "steady synthetic traffic.</p>",
        term(log, "get hpa text-stats", "top pods", pick=slice(0, 2)),
        term(log, "while ["),
        term(log, "describe hpa", "5xx during"),
        "<p>The HPA went from 3 to 7 pods 20 s after the load began and to its maximum of 8 another 16 s later. At 8 pods "
        "the CPU was still above target, so 8 is the real ceiling here, set by the single node rather than by the "
        "application. When the load stopped, the 2-minute stabilisation window held the pods, then the HPA scaled down to 4 "
        "and finally back to the minimum of 3. None of the 57,108 requests in the 10-minute window failed.</p>",
        shot("scaling-grafana", "Figure 10 - Grafana after the load test: request rate, latency and replicas (HPA desired vs pods answering)"),
    ])


def results():
    return "".join([
        "<h2>14. Results</h2>",
        table(
            ["Check", "Result"],
            [
                ["Pipeline gates", "2 of 12 runs blocked before publishing (4 manifest misconfigurations, 5 image CVEs); 3 releases published"],
                ["Infrastructure as code", "whole platform from one playbook; second run ok=16, changed=0"],
                ["Commit to production", "1.2.0: release commit to fully promoted canary in about 4 minutes, no manual step"],
                ["Faulty release", "aborted automatically at 10% after 97 s; reverted in Git, Synced and Healthy again"],
                ["Database outage", "critical alert paged 9 s after firing; error lines found in Loki; restored by Argo CD 8 s after self-heal was re-enabled"],
                ["Drift", "deleted Service back in 2 s, hand-edited CronJob reverted in 18 s"],
                ["Load", "3 to 8 pods in 36 s, back to 3 after the load; 0 errors in 57,108 requests"],
                ["Data loss", "restore in 9 s; only the 5 s of writes after the last dump lost"],
                ["Secrets", "0 leaks in Git history; read of another namespace's path denied (403)"],
            ],
        ),
        "<h2>15. Problems met and what they taught</h2>",
        bullets(
            "<b>Gates catch real issues.</b> The first two runs failed on findings nobody planted: missing read-only root "
            "filesystems, and CVEs in pip's vendored libraries that would have shipped in every image.",
            "<b>A shared, undersized cluster distorts every measurement.</b> With 4 GB and another lab's workloads on the same "
            "node, the VM swapped 3.5 GB and reached a load average of 44; probes timed out and pods restarted. Raising "
            "OrbStack to 10 GB fixed it, and probe timeouts were raised so a slow node is not mistaken for a dead one.",
            "<b>Readiness must not depend on a shared dependency</b>, or one database outage empties the Service and the "
            "application's own error metrics go silent.",
            "<b>Backups need a restore procedure that knows about time.</b> &quot;Restore the latest&quot; is wrong after "
            "a data-loss incident if a scheduled backup ran after it.",
            "<b>Network policies are enforced a moment after a pod starts.</b> Short-lived jobs (backup, restore) must wait "
            "until the database accepts them instead of failing on their first connection.",
            "<b>Local name resolution differs per tool.</b> curl resolves OrbStack's <code>*.k8s.orb.local</code> names, but "
            "Python and the headless browser do not, so Ansible addresses Traefik on 127.0.0.1 with a Host header.",
        ),
        "<h2>16. Conclusion</h2>",
        "<p>The platform takes a change from a commit to production with no manual step, and every stage can stop it: tests, "
        "five kinds of security scan, an image scan, and finally the canary's live metrics. When something still goes "
        "wrong in production, it is detected (alerts within seconds of the threshold), explained (structured logs in "
        "Loki), and repaired from the same source of truth (Git through Argo CD, data from verified backups). The main "
        "limits are those of a single-node lab: one database instance without streaming replication (Lab 4 showed "
        "CloudNativePG failover), backups on the same node as the data, and receivers that log notifications instead of "
        "paging a person.</p>",
    ])


def body():
    sections = [overview, cicd, container, ansible, k8s, secrets, network, monitoring, logging, canary, recovery,
                scaling, results]
    return "".join(section() for section in sections)

