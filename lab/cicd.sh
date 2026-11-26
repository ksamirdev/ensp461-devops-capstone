#!/usr/bin/env bash
# Pipeline evidence from GitHub Actions: every run on main, which gate stopped each blocked run and why,
# and the release commit the deliver job wrote.
set -euo pipefail
cd "$(dirname "$0")/.."
source lab/rec.sh evidence/logs/cicd.log
source lab/common.sh
REPO=ksamirdev/ensp461-devops-capstone
jobs_of() { gh run view "$1" --json jobs -q '.jobs[] | "  \(.name): \(.conclusion)"'; }
export -f jobs_of
rec "gh run list --workflow ci-cd.yml --limit 20 --json headSha,conclusion,displayTitle,createdAt -q '.[] | \"\\(.createdAt[11:19])  \\(.headSha[:7])  \\(.conclusion | .[:9] + (\" \" * (9 - length)))  \\(.displayTitle[:70])\"'"
for id in $(gh run list --workflow ci-cd.yml --limit 20 --json databaseId,conclusion -q '.[] | select(.conclusion=="failure") | .databaseId'); do
  rec "gh run view $id --json displayTitle,headSha -q '\"\\(.headSha[:7]) \\(.displayTitle)\"'; jobs_of $id"
  rec "gh run view $id --log-failed | cut -f3- | sed -E 's/^[^ ]+ //' | grep -E '^(KSV-|Total: )|│ +[1-9] +│|^│ (msgpack|urllib3|setuptools) ' | head -16"
done
GOOD=$(gh run list --workflow ci-cd.yml --limit 20 --json databaseId,conclusion,displayTitle -q '[.[] | select(.conclusion=="success" and (.displayTitle | test("1.1.0|sentence")))][0].databaseId')
rec "gh run view $GOOD --json displayTitle,headSha -q '\"\\(.headSha[:7]) \\(.displayTitle)\"'; jobs_of $GOOD"
rec "gh run view $GOOD --log | grep -E '^(Publish to GHCR|Release through GitOps)' | cut -f1,3- | sed -E 's/\\t[^ ]+ / /' | grep -vE '\\[36;1m|##\\[' | grep -E 'digest:|already published|release: text-stats|main -> main'"
rec git log --format="'%h %an  %s'" -12 origin/main
shot cicd-runs "https://github.com/$REPO/actions/workflows/ci-cd.yml" 5000
shot cicd-run-green "https://github.com/$REPO/actions/runs/$GOOD" 5000
FIRST_FAIL=$(gh run list --workflow ci-cd.yml --limit 20 --json databaseId,conclusion -q '[.[] | select(.conclusion=="failure")][-1].databaseId')
shot cicd-run-blocked "https://github.com/$REPO/actions/runs/$FIRST_FAIL" 5000
