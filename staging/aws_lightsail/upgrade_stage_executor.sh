#!/usr/bin/env bash
# Independently reviewed, source-pinned upgrade of the AWS staging SSH handler
# and executor ONLY. No Docker, financial data, Caddy, dashboard or chatbot changes.
# Usage (after reviewed merge to main):
#   sudo bash staging/aws_lightsail/upgrade_stage_executor.sh <full-reviewed-main-sha>
set -Eeuo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ "$(id -u)" -eq 0 ]] || { echo "BLOCKED: root required"; exit 2; }
[[ $# -eq 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
  echo "BLOCKED: expected exactly one full reviewed SHA"; exit 2;
}
SHA="$1"
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
[[ "$(git -C "$ROOT" rev-parse --show-toplevel)" == "$ROOT" ]] || {
  echo "BLOCKED: source is not the repository root"; exit 2;
}
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || {
  echo "BLOCKED: checkout does not match reviewed SHA"; exit 2;
}
EXPECTED_ORIGIN="https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git"
[[ "$(git -C "$ROOT" remote get-url origin)" == "$EXPECTED_ORIGIN" ]] || {
  echo "BLOCKED: unexpected repository origin"; exit 2;
}
# Require the exact current reviewed main commit; never install a draft PR SHA.
REMOTE_MAIN="$(git -C "$ROOT" ls-remote origin refs/heads/main | awk '{print $1}')"
[[ "$REMOTE_MAIN" == "$SHA" ]] || {
  echo "BLOCKED: reviewed SHA is not current origin/main"; exit 2;
}
for rel in staging/aws_lightsail/upgrade_stage_executor.sh \
           staging/aws_lightsail/sbi_stage_deploy_root.sh \
           staging/aws_lightsail/sbi_stage_request.sh; do
  git -C "$ROOT" show "$SHA:$rel" | cmp -s - "$ROOT/$rel" || {
    echo "BLOCKED: reviewed source differs from checkout"; exit 2;
  }
done
EXEC="/usr/local/sbin/sbi-stage-deploy"
HANDLER="/usr/local/bin/sbi-stage-request"
SUDOFILE="/etc/sudoers.d/90-sbi-stage-deploy"
KEYFILE="/home/sbi-deployer/.ssh/authorized_keys"
[[ -f "$EXEC" && -f "$HANDLER" && -f "$SUDOFILE" && -f "$KEYFILE" ]] || {
  echo "BLOCKED: complete existing restricted installation required"; exit 2;
}
[[ "$(stat -c '%U:%a' "$EXEC")" == "root:700" ]] || {
  echo "BLOCKED: unexpected executor ownership or mode"; exit 2;
}
[[ "$(stat -c '%U:%a' "$HANDLER")" == "root:755" ]] || {
  echo "BLOCKED: unexpected handler ownership or mode"; exit 2;
}
[[ "$(stat -c '%U:%a' "$SUDOFILE")" == "root:440" ]] || {
  echo "BLOCKED: unexpected sudoers ownership or mode"; exit 2;
}
[[ "$(wc -l < "$SUDOFILE")" -eq 1 ]] &&
  grep -Fxq 'sbi-deployer ALL=(root) NOPASSWD: /usr/local/sbin/sbi-stage-deploy ""' "$SUDOFILE" || {
  echo "BLOCKED: sudoers rule differs from approved restriction"; exit 2;
}
[[ "$(stat -c '%U:%a' "$KEYFILE")" == "sbi-deployer:600" ]] &&
  [[ "$(wc -l < "$KEYFILE")" -eq 1 ]] &&
  grep -Eq '^restrict,command="/usr/local/bin/sbi-stage-request" ssh-ed25519 [A-Za-z0-9+/=]+$' "$KEYFILE" || {
  echo "BLOCKED: SSH forced-command restriction differs"; exit 2;
}
[[ " $(id -nG sbi-deployer) " != *" docker "* ]] || {
  echo "BLOCKED: deployer must not belong to docker group"; exit 2;
}
[[ "$(getent passwd sbi-deployer | cut -d: -f7)" == "/bin/sh" ]] || {
  echo "BLOCKED: unexpected deployer shell"; exit 2;
}
command -v visudo >/dev/null
command -v runuser >/dev/null
visudo -cf /etc/sudoers >/dev/null
bash -n "$ROOT/staging/aws_lightsail/sbi_stage_deploy_root.sh" \
  "$ROOT/staging/aws_lightsail/sbi_stage_request.sh"
# Refuse concurrent deployments or upgrades. This is the same lock as the executor.
exec 9>/run/lock/sbi-stage-release.lock
flock -n 9 || { echo "BLOCKED: staging release/upgrade already running"; exit 2; }
if cmp -s "$EXEC" "$ROOT/staging/aws_lightsail/sbi_stage_deploy_root.sh" &&
   cmp -s "$HANDLER" "$ROOT/staging/aws_lightsail/sbi_stage_request.sh"; then
  echo "UPGRADE_ALREADY_APPLIED=YES"
  echo "DEPLOYMENT_TRIGGERED=NO"
  exit 0
fi
BACKUP_PARENT="/var/lib/sbi-stage-release/upgrade-backups"
install -d -o root -g root -m 0700 "$BACKUP_PARENT"
BACKUP="$(mktemp -d "$BACKUP_PARENT/reviewed.XXXXXXXX")"
cp -p "$EXEC" "$BACKUP/executor"
cp -p "$HANDLER" "$BACKUP/handler"
chmod 0600 "$BACKUP/executor" "$BACKUP/handler"
TMP_EXEC="$(mktemp /usr/local/sbin/.sbi-stage-deploy.XXXXXXXX)"
TMP_HANDLER="$(mktemp /usr/local/bin/.sbi-stage-request.XXXXXXXX)"
CHANGED=0
finish() {
  code=$?
  trap - EXIT INT TERM
  rm -f -- "$TMP_EXEC" "$TMP_HANDLER"
  if (( code != 0 && CHANGED == 1 )); then
    # Restore both original binaries even if only one was replaced.
    install -o root -g root -m 0700 "$BACKUP/executor" "$EXEC" || true
    install -o root -g root -m 0755 "$BACKUP/handler" "$HANDLER" || true
    if cmp -s "$BACKUP/executor" "$EXEC" &&
       cmp -s "$BACKUP/handler" "$HANDLER"; then
      echo "UPGRADE_ROLLBACK=PASS"
    else
      echo "UPGRADE_ROLLBACK=FAIL"
    fi
  fi
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
install -o root -g root -m 0700 \
  "$ROOT/staging/aws_lightsail/sbi_stage_deploy_root.sh" "$TMP_EXEC"
install -o root -g root -m 0755 \
  "$ROOT/staging/aws_lightsail/sbi_stage_request.sh" "$TMP_HANDLER"
cmp -s "$TMP_EXEC" "$ROOT/staging/aws_lightsail/sbi_stage_deploy_root.sh"
cmp -s "$TMP_HANDLER" "$ROOT/staging/aws_lightsail/sbi_stage_request.sh"
CHANGED=1
mv -f "$TMP_EXEC" "$EXEC"
mv -f "$TMP_HANDLER" "$HANDLER"
# A read-only capability handshake as the restricted SSH account is mandatory.
STATUS="$(runuser -u sbi-deployer -- env SSH_ORIGINAL_COMMAND=status-auth-v1 "$HANDLER")"
grep -Fxq 'SBI_STAGE_EXECUTOR=PREVIEW_AUTH_V1' <<< "$STATUS" &&
  grep -Fxq 'FINANCIAL_WRITES=DISABLED' <<< "$STATUS" || {
  echo "BLOCKED: restricted staging handshake failed"; exit 2;
}
cmp -s "$EXEC" "$ROOT/staging/aws_lightsail/sbi_stage_deploy_root.sh"
cmp -s "$HANDLER" "$ROOT/staging/aws_lightsail/sbi_stage_request.sh"
CHANGED=0
trap - EXIT INT TERM
rm -f -- "$TMP_EXEC" "$TMP_HANDLER"
echo "STAGING_EXECUTOR_UPGRADE=PASS"
echo "SSH_HANDLER_UPGRADE=PASS"
echo "DEPLOYMENT_TRIGGERED=NO"
echo "FINANCIAL_WRITES=DISABLED"
echo "BACKUP_PRESERVED=YES"
