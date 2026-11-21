#!/usr/bin/env bash
# AWS staging ONLY. Separate Docker Compose project; existing UI and Caddy intact.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE="$SCRIPT_DIR/compose.synthetic.yaml"

if [ "$(git -C "$REPO_ROOT" rev-parse --show-toplevel)" != "$REPO_ROOT" ]; then
  echo "STAGING_ERROR=RUN_FROM_REPOSITORY_WORKTREE" >&2; exit 2
fi
SBI_REVIEWED_SOURCE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if ! [[ "$SBI_REVIEWED_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STAGING_ERROR=FULL_SHA_REQUIRED" >&2; exit 2
fi
if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]; then
  echo "STAGING_ERROR=CHECKOUT_HAS_UNCOMMITTED_MODIFICATIONS" >&2; exit 2
fi
export SBI_REVIEWED_SOURCE_SHA

if docker info >/dev/null 2>&1; then
  DC=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  # Docker Compose must receive the pinned SHA even under sudo env_reset.
  DC=(sudo env "SBI_REVIEWED_SOURCE_SHA=$SBI_REVIEWED_SOURCE_SHA" docker)
else
  echo "STAGING_ERROR=DOCKER_ACCESS_REQUIRED" >&2; exit 2
fi
if ! "${DC[@]}" compose version >/dev/null 2>&1; then
  echo "STAGING_ERROR=DOCKER_COMPOSE_PLUGIN_REQUIRED" >&2; exit 2
fi

"${DC[@]}" compose -f "$COMPOSE" config --quiet
"${DC[@]}" compose -f "$COMPOSE" build
"${DC[@]}" compose -f "$COMPOSE" up -d --no-deps --wait

BASE="http://127.0.0.1:18087"
curl --fail --silent --show-error "$BASE/healthz" | python3 -c '
import json,sys
j=json.load(sys.stdin)
assert j["mode"]=="SYNTHETIC_ONLY"
assert j["financial_writes"] is False
assert j["apply_enabled"] is False
assert j["historical_records_accessed"] is False
assert j["production_approved"] is False
print("SBI_SYNTHETIC_HEALTH=PASS")'
curl --fail --silent --show-error "$BASE/api/synthetic-demo" | python3 -c '
import json,sys
j=json.load(sys.stdin)
assert j["synthetic_probe"]=="PASS"
assert j["proposal_count"]==1
assert j["actual_financial_status"]=="NOT_ASSIGNED"
assert j["financial_writes"] is False
print("SBI_SYNTHETIC_DEMO=PASS")'
curl --fail --silent --show-error "$BASE/api/stage3/synthetic-bridge" | python3 -c '
import json,sys
j=json.load(sys.stdin)
assert j["stage3_probe"]=="PASS"
assert j["mock_receipt_registered"] is True
assert j["mock_review_completed"] is True
assert j["mock_candidate_ledger_edges"]==1
assert j["mock_ledger_persistent"] is False
assert j["financial_writes"] is False
print("SBI_STAGE3_MOCK_BRIDGE=PASS")'
code="$(curl --silent --output /dev/null --write-out '%{http_code}' -X POST "$BASE/api/payment-reconciliation/apply")"
if [ "$code" != "403" ]; then
  echo "STAGING_ERROR=FINANCIAL_APPLY_NOT_LOCKED" >&2
  "${DC[@]}" compose -f "$COMPOSE" down || true
  exit 3
fi

echo "SBI_NEW_ENGINE_SOURCE_SHA=$SBI_REVIEWED_SOURCE_SHA"
echo "SBI_NEW_ENGINE_STAGE=RUNNING_LOOPBACK_ONLY"
echo "SBI_NEW_ENGINE_APPLY=LOCKED"
echo "SBI_FINANCIAL_POSTING=NOT_ENABLED"
echo "EXISTING_AWS_DASHBOARD=UNCHANGED_BY_THIS_SCRIPT"