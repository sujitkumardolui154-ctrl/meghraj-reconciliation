#!/usr/bin/env bash
# SBI PR129 combined remaining Stage 23–25: candidate auth bridge, isolated
# Flask staging QA, release readiness. NEVER deploys to public PR129.
set -Eeuo pipefail
umask 077
export PAGER=cat
STEP=INIT
trap 'rc=$?; echo "STAGE23_25_COMBINED_SAFE_QA=FAIL step=$STEP exit=$rc"; echo "LIVE_PR129_DEPLOYMENT=NOT_PERFORMED"; exit "$rc"' ERR

REPO=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
REV=29e937297c1d82da58dabe82ee095e6519751c67
WORK=/home/ubuntu/sbi-stage23-25-combined
APP=sbi-bulk-report-pr129-https-preview
BASE_IMAGE=sbi-pr129-postgres-stage17:isolated
CANDIDATE=sbi-pr129-pg-stage23:isolated
DB=sbi_reconciliation_main
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"
ISSUES=0
review() { echo "REVIEW_REQUIRED: $*"; ISSUES=$((ISSUES+1)); }
sql() { sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() {
  sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
reports() {
  sql "SELECT (SELECT count(*) FROM sbi.invoice_financial_summary),(SELECT count(*) FROM sbi.payment_financial_summary);"
}

echo "=== 0. PRESERVE BASELINE ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
sudo -u postgres pg_isready -d "$DB" >/dev/null
sudo -n docker inspect "$APP" >/dev/null
sudo -n docker image inspect "$BASE_IMAGE" >/dev/null
BEFORE="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
REP_BEFORE="$(reports)"
[[ "$(sql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='sbi' AND table_type='BASE TABLE';")" == 14 ]]
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "DATABASE_AND_REPORT_ROLE_BASELINE=PASS"
echo "FINANCIAL_COUNTS_BEFORE=$FIN_BEFORE"
echo "REPORT_COUNTS_BEFORE=$REP_BEFORE"

echo "=== 1. GET PINNED STAGE23 SOURCE ==="
STEP=FETCH
for f in stage23_auth_bridge.py test_stage23_auth_bridge.py patch_stage23_candidate.py inspect_actual_auth_contract.py Dockerfile.stage23; do
  curl -4 -fLsS --retry 3 -o "$f" "$REPO/$REV/database/stages23_25/$f"
done
python3 -m py_compile stage23_auth_bridge.py test_stage23_auth_bridge.py patch_stage23_candidate.py inspect_actual_auth_contract.py
echo "STAGE23_SOURCE_SYNTAX=PASS"

echo "=== STAGE 23. EXISTING FIREBASE/REPORT POLICY CONTRACT ==="
STEP=STAGE23
sudo -n docker exec -i "$APP" python3 -B - < inspect_actual_auth_contract.py | tee stage23_contract.txt
grep -qx 'SOURCE_AUTH_CONTRACT_AUDIT=COMPLETE' stage23_contract.txt
if grep -qx 'STAGE23_KNOWN_POLICY_SIGNATURE=PASS' stage23_contract.txt; then
  echo "STAGE23_POLICY_SIGNATURE=PASS"
else
  review "Existing policy parameters differ from allowlisted Stage23 bridge signatures"
fi
if grep -qx 'STAGE23_AUTOWIRING_CONTEXT=STATIC_COMPATIBLE_NOT_E2E_VERIFIED' stage23_contract.txt; then
  echo "STAGE23_REQUEST_CONTEXT_STATIC_COMPATIBLE=PASS"
else
  review "Actual session guard does not prove assignment to g.user AND g.identity; bridge will deny until mapped"
fi

echo "=== STAGE 24. BUILD DERIVED AUTHENTICATED CANDIDATE, NEVER LIVE ==="
STEP=STAGE24_BUILD
sudo -n docker build --pull=false \
  --build-arg STAGE17_IMAGE="$BASE_IMAGE" \
  -f Dockerfile.stage23 \
  -t "$CANDIDATE" .
echo "STAGE24_ISOLATED_AUTH_BRIDGE_IMAGE=BUILT"

echo "=== STAGE 24. COMBINED FLASK AUTHORIZATION AND DB ADAPTER UNIT QA ==="
STEP=STAGE24_UNIT
sudo -n docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$CANDIDATE" -B -m unittest -v \
  test_stage23_auth_bridge.py test_stage17_blueprint.py test_sbi_pg_reporting_combined.py
echo "STAGE24_SYNTHETIC_UNIT_QA=PASS"

echo "=== STAGE 24. PRIVATE PR129 APP: ANONYMOUS ROUTE REJECTION ==="
STEP=STAGE24_ANONYMOUS
if sudo -n docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$CANDIDATE" -B -c '
import sys
try:
    from app import app
    test=app.test_client()
    response=test.get("/api/reporting/v2/postgresql-summary")
    status=response.status_code
    print("STAGE24_CANDIDATE_ANONYMOUS_HTTP=",status)
    if status not in (401,403):
        sys.exit(2)
    print("STAGE24_REAL_APP_ANONYMOUS_DENIAL=PASS")
except Exception as e:
    print("STAGE24_REAL_APP_IMPORT_OR_AUTH=REVIEW_REQUIRED",type(e).__name__)
    sys.exit(3)
'; then
  echo "STAGE24_APP_ROUTE_SECURITY=PASS"
else
  review "Isolated real app could not demonstrate HTTP 401/403; inspect PR129 runtime dependencies or authorization"
fi

echo "=== STAGE 25. LIVE DEPLOYMENT GATE & ROLLBACK EVIDENCE ==="
STEP=STAGE25
for endpoint in /auth/me /api/reporting/v2 /api/bulk-report/status; do
  status="$(curl -4 -sS --max-time 12 -o /dev/null -w '%{http_code}' "https://pr129.13-232-241-221.sslip.io$endpoint" || true)"
  echo "CURRENT_LIVE_ANONYMOUS=$endpoint HTTP=$status"
  [[ "$status" == 401 || "$status" == 403 ]] || review "Unexpected public anonymous response at $endpoint"
done

if [[ -r /home/ubuntu/sbi-db-backups/sbi_main_initial.dump ]] &&
   pg_restore -l /home/ubuntu/sbi-db-backups/sbi_main_initial.dump >/dev/null 2>&1; then
  echo "BACKUP_ARCHIVE_LISTING=PASS"
else
  review "Backup archive needs confirmation (restore was not tested)"
fi

[[ "$(counts)" == "$FIN_BEFORE" ]]
[[ "$(reports)" == "$REP_BEFORE" ]]
[[ "$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" == "$BEFORE" ]]
echo "FINANCIAL_DATA_COUNTS_STABLE=PASS"
echo "LIVE_PR129_CONTAINER_IDENTITY_STABLE=PASS"

echo "=== FINAL COMBINED STAGES 23-25 ==="
if [[ "$ISSUES" == 0 ]]; then
  echo "STAGE23_25_SAFE_CHECKS=PASS"
else
  echo "STAGE23_25_SAFE_CHECKS=REVIEW_REQUIRED"
fi
echo "REVIEW_COUNT=$ISSUES"
echo "STAGE23_AUTH_BRIDGE=BUILT_IN_ISOLATED_CANDIDATE"
echo "STAGE24_SYNTHETIC_SECURITY_QA=PASS"
echo "STAGE24_PRIVATE_STAGING_SERVICE_DEPLOYMENT=NOT_PERFORMED"
echo "STAGE25_AUTHENTICATED_FIREBASE_USER_E2E=NOT_PERFORMED"
echo "STAGE25_REAL_BACKUP_RESTORE_TEST=NOT_PERFORMED"
echo "STAGE25_LIVE_RELEASE=BLOCKED_PENDING_AUTHENTICATED_QA_AND_APPROVAL"
echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT_REQUIRED_ACTION=VERIFY_ACTUAL_SESSION_CONTEXT_AND_AUTHENTICATED_USER_IN_PRIVATE_STAGING"
