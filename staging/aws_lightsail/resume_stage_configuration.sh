#!/usr/bin/env bash
# Resume AWS staging credential configuration without repinning branch HEAD.
# Refuse ambiguous or partially installed privileged components.
set -Eeuo pipefail
umask 077
HOST="${1:-}"
[[ "$HOST" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{2,252}$ ]] || { echo "BLOCKED: supply the approved AWS staging public hostname/IP"; exit 2; }
SOURCE_BASE="f93a94ae33b223ab29147e8c4c40996076ec8db0"
BRANCH="feature/consolidated-requirements-g-n-20261102"
ROOT="$HOME/sbi-agent-workspace/sbi-agent-source"
cd "$ROOT"
git fetch origin "$BRANCH"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "BLOCKED: wrong branch"; exit 2; }
git pull --ff-only origin "$BRANCH"
git merge-base --is-ancestor "$SOURCE_BASE" HEAD || { echo "BLOCKED: unapproved history"; exit 2; }
git diff --quiet "$SOURCE_BASE" HEAD -- \
  staging/aws_lightsail/install_stage_executor.sh \
  staging/aws_lightsail/sbi_stage_deploy_root.sh \
  staging/aws_lightsail/sbi_stage_request.sh \
  staging/aws_lightsail/configure_gh_stage_secrets.sh \
  .github/workflows/sbi-aws-staging-release-request.yml ||
  { echo "BLOCKED: privileged deployment source changed since reviewed base"; exit 2; }
echo "SOURCE_ANCESTRY=PASS"

EXEC=/usr/local/sbin/sbi-stage-deploy
HANDLER=/usr/local/bin/sbi-stage-request
SUDOFILE=/etc/sudoers.d/90-sbi-stage-deploy
EXPECTED_SUDO='sbi-deployer ALL=(root) NOPASSWD: /usr/local/sbin/sbi-stage-deploy ""'
if sudo test -e "$EXEC" || sudo test -e "$SUDOFILE"; then
  sudo test -x "$EXEC" && sudo test -f "$SUDOFILE" || {
    echo "BLOCKED: partial privileged installation, manual review required"; exit 2;
  }
  sudo cmp -s staging/aws_lightsail/sbi_stage_deploy_root.sh "$EXEC" || {
    echo "BLOCKED: installed executor differs from reviewed source"; exit 2;
  }
  sudo cmp -s staging/aws_lightsail/sbi_stage_request.sh "$HANDLER" || {
    echo "BLOCKED: installed SSH handler differs from reviewed source"; exit 2;
  }
  sudo grep -Fxq "$EXPECTED_SUDO" "$SUDOFILE" || {
    echo "BLOCKED: sudoers permission differs from approved rule"; exit 2;
  }
  sudo visudo -cf /etc/sudoers >/dev/null
  echo "EXECUTOR=EXISTING_VERIFIED"
else
  sudo bash staging/aws_lightsail/install_stage_executor.sh
  echo "EXECUTOR=INSTALLED"
fi
# At this point the executor exists but has not been permitted to deploy anything.
bash staging/aws_lightsail/configure_gh_stage_secrets.sh "$HOST"
echo "SBI_CONFIGURATION=COMPLETE"
echo "DEPLOYMENT_TRIGGERED=NO"
echo "FINAL_CONSOLIDATED_DEPLOYMENT_TEST=PENDING"
