#!/usr/bin/env bash
# Run ONLY as OpenSSH authorized_keys forced-command, account sbi-deployer.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
original="${SSH_ORIGINAL_COMMAND:-}"
if [[ "$original" == "status" ]]; then
  echo "SBI_STAGE_SSH=RESTRICTED"
  echo "FINANCIAL_WRITES=DISABLED"
elif [[ "$original" =~ ^deploy[[:space:]]([0-9a-f]{40})$ ]]; then
  printf '%s\n' "${BASH_REMATCH[1]}" | sudo -n /usr/local/sbin/sbi-stage-deploy
else
  echo "REQUEST_DENIED" >&2
  exit 126
fi
