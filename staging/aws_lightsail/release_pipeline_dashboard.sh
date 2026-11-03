#!/usr/bin/env bash
# Single operator command: reviewed GitHub->AWS isolated staging gate,
# then read-only public dashboard promotion. No financial deployment.
set -Eeuo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
REPO="sujitkumardolui154-ctrl/meghraj-reconciliation"
WORKFLOW="sbi-aws-staging-release-request.yml"
AWS_BRANCH="aws/lightsail-preview-20261102"
PUBLIC="$(cd "$(dirname "$0")/../.." && pwd -P)"
MAIN="$HOME/sbi-agent-workspace/sbi-release-main"
[[ -e "$MAIN/.git" ]] || { echo "BLOCKED: previously approved main release worktree missing"; exit 2; }
command -v gh >/dev/null
command -v timeout >/dev/null
gh auth status >/dev/null 2>&1 || { echo "BLOCKED: GitHub CLI authentication missing"; exit 2; }
[[ "$(git -C "$PUBLIC" branch --show-current)" == "$AWS_BRANCH" ]] || {
  echo "BLOCKED: public source is not on the reviewed AWS preview branch"; exit 2;
}
[[ -z "$(git -C "$PUBLIC" status --porcelain --untracked-files=no)" ]] || {
  echo "BLOCKED: public source has tracked local modifications"; exit 2;
}
REMOTE_PUBLIC="$(git -C "$PUBLIC" ls-remote origin "refs/heads/$AWS_BRANCH" | awk '{print $1}')"
PUBLIC_SHA="$(git -C "$PUBLIC" rev-parse HEAD)"
[[ "$PUBLIC_SHA" == "$REMOTE_PUBLIC" ]] || {
  echo "BLOCKED: public source must match reviewed GitHub AWS preview branch"; exit 2;
}
git -C "$MAIN" fetch origin main
git -C "$MAIN" checkout --detach origin/main
MAIN_SHA="$(git -C "$MAIN" rev-parse HEAD)"
REMOTE_MAIN="$(git -C "$MAIN" ls-remote origin refs/heads/main | awk '{print $1}')"
[[ "$MAIN_SHA" == "$REMOTE_MAIN" ]] || {
  echo "BLOCKED: staging SHA differs from reviewed main"; exit 2;
}
[[ "$(git -C "$MAIN" show "$MAIN_SHA:staging/railway_public/pipeline.html" | sha256sum | cut -d' ' -f1)" ==
   "$(sha256sum "$PUBLIC/staging/railway_public/pipeline.html" | cut -d' ' -f1)" ]] || {
  echo "BLOCKED: staging/public dashboard HTML are not identical"; exit 2;
}
echo "SOURCE_DASHBOARD_CONTRACT=PASS"
echo "STAGING_RELEASE_SHA=$MAIN_SHA"
echo "PUBLIC_PREVIEW_SOURCE_SHA=$PUBLIC_SHA"

# Stage release must finish successfully before public compose is touched.
START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gh workflow run "$WORKFLOW" -R "$REPO" --ref main -f "release_sha=$MAIN_SHA"
echo "STAGING_DEPLOYMENT_REQUESTED=YES"
RUN=""
for i in $(seq 1 25); do
  RUN="$(gh run list -R "$REPO" --workflow "$WORKFLOW" --event workflow_dispatch --branch main --limit 10 --json databaseId,createdAt,headSha --jq ".[] | select(.headSha==\"$MAIN_SHA\" and .createdAt>=\"$START\") | .databaseId" | head -1)"
  if [[ -n "$RUN" ]]; then break; fi
  sleep 3
done
[[ -n "$RUN" ]] || {
  echo "BLOCKED: cannot confirm newly dispatched staging run; public preview untouched"; exit 2;
}
echo "STAGING_GITHUB_RUN_ID=$RUN"
timeout 600 gh run watch "$RUN" -R "$REPO" --interval 8 --exit-status || {
  echo "BLOCKED: staging deployment did not pass; public preview untouched"; exit 2;
}
echo "STAGING_GITHUB_WORKFLOW=PASS"
sudo bash "$PUBLIC/staging/aws_lightsail/publish_pipeline_dashboard.sh" "$PUBLIC_SHA"
echo "SBI_PUBLIC_PIPELINE_RELEASE=PASS"
echo "FINANCIAL_WRITES=DISABLED"
echo "URL=https://sbi-preview.13-232-241-221.sslip.io/"
