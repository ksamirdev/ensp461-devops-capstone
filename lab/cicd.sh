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
rec gh run list --workflow ci-cd.yml --limit 20
for id in $(gh run list --workflow ci-cd.yml --limit 20 --json databaseId,conclusion -q '.[] | select(.conclusion=="failure") | .databaseId'); do
  rec "gh run view $id --json displayTitle,headSha -q '\"\\(.headSha[:7]) \\(.displayTitle)\"'; jobs_of $id"
  rec "gh run view $id --log-failed | sed -E 's/^[^\\t]*\\t[^\\t]*\\t[0-9TZ:.-]+ //' | grep -E '^(KSV|FAILED|E  |.*(Total|HIGH|CRITICAL).*│?)' | grep -vE 'Library|^│ *│' | head -12"
done
GOOD=$(gh run list --workflow ci-cd.yml --limit 20 --json databaseId,conclusion,displayTitle -q '[.[] | select(.conclusion=="success" and (.displayTitle | test("1.1.0|sentence")))][0].databaseId')
rec "gh run view $GOOD --json displayTitle,headSha -q '\"\\(.headSha[:7]) \\(.displayTitle)\"'; jobs_of $GOOD"
rec "gh run view $GOOD --log | grep -E 'Publish to GHCR.*(digest:|already published)|Release through GitOps.*(release: text-stats|main -> main)' | sed -E 's/^[^\\t]*\\t[^\\t]*\\t[0-9TZ:.-]+ //'"
rec git log --format="'%h %an  %s'" -12 origin/main
shot cicd-runs "https://github.com/$REPO/actions/workflows/ci-cd.yml" 5000
shot cicd-run-green "https://github.com/$REPO/actions/runs/$GOOD" 5000
FIRST_FAIL=$(gh run list --workflow ci-cd.yml --limit 20 --json databaseId,conclusion -q '[.[] | select(.conclusion=="failure")][-1].databaseId')
shot cicd-run-blocked "https://github.com/$REPO/actions/runs/$FIRST_FAIL" 5000
