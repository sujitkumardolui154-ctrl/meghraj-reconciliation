#!/usr/bin/env bash
# Operator-facing wrapper for the ONE reviewed, login-preserving staging executor.
# No separate Docker release logic: all checks, rollback and logs live in root executor.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
RELEASE="${1:-}"
[[ $# -eq 1 && "$RELEASE" =~ ^[0-9a-f]{40}$ ]] || {
  echo "BLOCKED: expected exactly one full reviewed Git SHA"; exit 2;
}
[[ "$(git rev-parse HEAD)" == "$RELEASE" ]] || {
  echo "BLOCKED: checkout SHA mismatch"; exit 2;
}
# Older installed root binaries did not preserve the preview login; never
# invoke their deploy path. Status mode performs no Docker or Git operations.
STATUS="$(printf 'status\n' | sudo -n /usr/local/sbin/sbi-stage-deploy)" || {
  echo "BLOCKED: installed executor capability check failed"; exit 2;
}
grep -Fxq 'SBI_STAGE_EXECUTOR=PREVIEW_AUTH_V1' <<< "$STATUS" || {
  echo "BLOCKED: login-preserving executor upgrade required"; exit 2;
}
echo "FINANCIAL_WRITES=DISABLED"
printf '%s\n' "$RELEASE" | sudo -n /usr/local/sbin/sbi-stage-deploy
