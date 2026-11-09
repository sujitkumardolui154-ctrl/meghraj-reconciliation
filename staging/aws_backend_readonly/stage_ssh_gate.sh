#!/usr/bin/env bash
# Install root-owned 0755 as /usr/local/sbin/sbi_backend_readonly_ssh_gate.sh.
# Make it the *forced* authorized_keys command for a separate non-admin
# sbi-backend-deployer account. Never reuse the dashboard stage SSH identity.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
COMMAND="${SSH_ORIGINAL_COMMAND:-}"
RUNNER=/usr/local/sbin/sbi_backend_readonly_stage_release.sh
if [[ "$COMMAND" == 'status-backend-v1' ]]; then
  printf '%s\n' status | sudo -n "$RUNNER"
elif [[ "$COMMAND" =~ ^deploy-backend[[:space:]]([0-9a-f]{40})$ ]]; then
  printf '%s\n' "${BASH_REMATCH[1]}" | sudo -n "$RUNNER"
else
  echo 'BLOCKED: backend staging command not allowlisted' >&2
  exit 2
fi
