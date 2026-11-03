#!/usr/bin/env bash
# Publish only AWS staging deployment credentials as GitHub environment secrets.
# Usage: bash .../configure_gh_stage_secrets.sh <public-SSH-hostname>
# Do not use GitHub deploy secrets to grant financial/database privileges.
set -Eeuo pipefail
umask 077
[[ $# -eq 1 ]] || { echo "Usage: $0 <public-SSH-hostname>"; exit 2; }
HOST="$1"
[[ "$HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]{2,252}$ ]] || { echo "BLOCKED: invalid SSH host"; exit 2; }
REPO="sujitkumardolui154-ctrl/meghraj-reconciliation"
KEY="$HOME/sbi-agent-workspace/credentials/sbi_github_stage"
[[ -s "$KEY" && -s "$KEY.pub" ]] || { echo "BLOCKED: deployment key missing"; exit 2; }
[[ "$(stat -c %a "$KEY")" == "600" ]] || { echo "BLOCKED: private key permissions"; exit 2; }
command -v gh >/dev/null
gh auth status >/dev/null 2>&1 || { echo "BLOCKED: gh auth missing"; exit 2; }
sudo test -x /usr/local/sbin/sbi-stage-deploy || { echo "BLOCKED: staged executor not installed"; exit 2; }
sudo test -x /usr/local/bin/sbi-stage-request || { echo "BLOCKED: restricted SSH handler missing"; exit 2; }
PUB="$(sudo cat /etc/ssh/ssh_host_ed25519_key.pub)"
[[ "$PUB" == ssh-ed25519\ * ]] || { echo "BLOCKED: expected ED25519 host key missing"; exit 2; }
# Only prepare secrets in a dedicated staging environment, not repository-wide.
gh api -X PUT "repos/$REPO/environments/sbi-staging" >/dev/null
printf '%s\n' "$HOST" | gh secret set SBI_STAGE_HOST --repo "$REPO" --env sbi-staging
gh secret set SBI_STAGE_DEPLOY_KEY --repo "$REPO" --env sbi-staging < "$KEY"
printf '%s %s\n' "$HOST" "$(printf '%s\n' "$PUB" | awk '{print $1" "$2}')" |
  gh secret set SBI_STAGE_HOST_KEY --repo "$REPO" --env sbi-staging
echo "GH_STAGE_SECRETS_CONFIGURED=YES"
echo "GH_ENVIRONMENT=sbi-staging"
echo "STAGING_RELEASE_NOT_TRIGGERED=YES"
echo "HOST_SSH_FINGERPRINT:"
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
echo "NOTE: restrict SSH ingress to trusted GitHub runner connectivity; do not open SSH globally solely for this workflow."
