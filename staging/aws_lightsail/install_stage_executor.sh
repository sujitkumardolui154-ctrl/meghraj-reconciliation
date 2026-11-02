#!/usr/bin/env bash
# One-time installer for staging-only SSH deploy handler/executor.
# Run as: sudo bash staging/aws_lightsail/install_stage_executor.sh
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "ERROR: root required"; exit 2; }
BASE="$(cd "$(dirname "$0")" && pwd)"
HANDLER="$BASE/sbi_stage_request.sh"
EXECUTOR="$BASE/sbi_stage_deploy_root.sh"
KEYFILE="/home/sbi-deployer/.ssh/authorized_keys"
SUDOFILE="/etc/sudoers.d/90-sbi-stage-deploy"
[[ -f "$HANDLER" && -f "$EXECUTOR" ]] || { echo "ERROR: missing source files"; exit 2; }
[[ -r "$KEYFILE" ]] || { echo "ERROR: restricted key not configured"; exit 2; }
[[ "$(stat -c '%U:%a' "$KEYFILE")" == "sbi-deployer:600" ]] || { echo "ERROR: unsafe authorized_keys"; exit 2; }
[[ "$(wc -l < "$KEYFILE")" -eq 1 ]] || { echo "ERROR: multiple SSH keys must be reviewed"; exit 2; }
grep -Eq '^restrict,command="/usr/local/bin/sbi-stage-request" ssh-ed25519 [A-Za-z0-9+/=]+$' "$KEYFILE" || {
  echo "ERROR: authorized key is not forced-command restricted"; exit 2;
}
[[ "$(id -nG sbi-deployer)" != *docker* ]] || { echo "ERROR: deployer in docker group"; exit 2; }
[[ "$(getent passwd sbi-deployer | cut -d: -f7)" == "/bin/sh" ]] || {
  echo "ERROR: deployer shell not configured as expected"; exit 2;
}
bash -n "$HANDLER" "$EXECUTOR"
[[ ! -e "$SUDOFILE" ]] || { echo "ERROR: pre-existing sudoers entry requires manual review"; exit 2; }
[[ -f "/usr/local/bin/sbi-stage-request" ]] || { echo "ERROR: current SSH handler missing"; exit 2; }
[[ "$(stat -c '%U' /usr/local/bin/sbi-stage-request)" == "root" ]] || {
  echo "ERROR: current SSH handler not root-owned"; exit 2;
}
command -v visudo >/dev/null
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
printf '%s\n' 'sbi-deployer ALL=(root) NOPASSWD: /usr/local/sbin/sbi-stage-deploy ""' > "$TMP"
chmod 440 "$TMP"
visudo -cf "$TMP" >/dev/null
cp -p /usr/local/bin/sbi-stage-request "/usr/local/bin/sbi-stage-request.bak"
chmod 600 /usr/local/bin/sbi-stage-request.bak
install -o root -g root -m 0700 "$EXECUTOR" /usr/local/sbin/sbi-stage-deploy
install -o root -g root -m 0755 "$HANDLER" /usr/local/bin/sbi-stage-request
install -o root -g root -m 0440 "$TMP" "$SUDOFILE"
visudo -cf /etc/sudoers >/dev/null
echo "STAGING_EXECUTOR_INSTALLED=YES"
echo "RESTRICTED_SSH_HANDLER_INSTALLED=YES"
echo "FINANCIAL_DATABASE_WRITES=DISABLED"
echo "NO_DEPLOYMENT_PERFORMED=YES"
