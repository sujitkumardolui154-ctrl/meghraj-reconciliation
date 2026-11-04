#!/usr/bin/env bash
# Owner-controlled manual DIL staging source QA; NEVER deploys or reads finance.
# Usage: cd ~/sbi-aws-app && bash tools/dil_manual_stage_preflight.sh
set -Eeuo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "BLOCKED: run inside the GitHub checkout"; exit 2;
}
cd "$REPO"
command -v python3 >/dev/null || { echo "BLOCKED: python3 required"; exit 2; }
command -v git >/dev/null || { echo "BLOCKED: git required"; exit 2; }

# Require an existing origin pointing to the approved repository.
origin="$(git remote get-url origin)"
case "$origin" in
  git@github.com:sujitkumardolui154-ctrl/meghraj-reconciliation.git|https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git|https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation)
    ;;
  *) echo "BLOCKED: unexpected origin; review your remote before running"; exit 2;;
esac

echo "=== MANUAL DIL STAGING SOURCE QA (NO DEPLOY) ==="
echo "REPO=$REPO"
echo "ORIGIN=approved GitHub repository"
echo "Pulling the four PR HEAD refs into Git objects without switching the live checkout..."
git fetch --no-tags origin \
  refs/pull/49/head:refs/remotes/origin/dil-stage-pr49 \
  refs/pull/50/head:refs/remotes/origin/dil-stage-pr50 \
  refs/pull/51/head:refs/remotes/origin/dil-stage-pr51 \
  refs/pull/52/head:refs/remotes/origin/dil-stage-pr52

# Exact reviewed commits. If PR contents have changed, stop for a fresh review.
PR_NAMES=(49 50 51 52)
EXPECTED=(
  1c6fdca798f87183501f38b859cc47a69753eabf
  96a5bae41086b9394fdad307ba4793b90c640909
  5fc8c083aa13330eb61a988c89ab26f09818ac37
  77294ce0e4384c1136b21e23ffdd5bc4045f72e8
)
TESTS=(
  test_dil_evidence_boundary.py
  test_dil_chat_query_contract.py
  test_dil_chat_transport.py
  test_dil_invoice_intelligence_pipeline.py
)
for i in "${!PR_NAMES[@]}"; do
  sha="$(git rev-parse "refs/remotes/origin/dil-stage-pr${PR_NAMES[i]}")"
  if [[ "$sha" != "${EXPECTED[i]}" ]]; then
    echo "BLOCKED: PR #${PR_NAMES[i]} has a different HEAD: $sha"
    echo "Review the updated PR and regenerate an SHA-bound runbook."
    exit 3
  fi
done

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dil-stage-qa.XXXXXXXX")"
declare -a WORKTREES=()
cleanup() {
  local path
  for path in "${WORKTREES[@]}"; do
    git worktree remove --force "$path" >/dev/null 2>&1 || true
  done
  rmdir "$TEMP_DIR" 2>/dev/null || true
}
trap cleanup EXIT
for i in "${!PR_NAMES[@]}"; do
  pr="${PR_NAMES[i]}"
  path="$TEMP_DIR/pr-$pr"
  echo
  echo "=== PR #$pr — pinned commit ${EXPECTED[i]} ==="
  git worktree add --detach "$path" "${EXPECTED[i]}"
  WORKTREES+=("$path")
  (
    cd "$path"
    PYTHONPATH="$path:$path/dashboard_source" python3 "tests/${TESTS[i]}"
  )
  echo "PASS: PR #$pr synthetic source tests"
done
echo
echo "SOURCE_QA=PASS"
echo "HOST_DEPLOYMENT=NOT_PERFORMED"
echo "REAL_DATABASE_CONNECTED=NOT_VERIFIED"
echo "FINANCIAL_WRITE=NOT_PERFORMED"
echo "NEXT_GATE=Independent_review + private_authenticated_staging_tests + rollback"
