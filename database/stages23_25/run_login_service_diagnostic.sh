#!/usr/bin/env bash
# Read-only combined Firebase login-service diagnostic: live PR129 vs private stage.
# No Firebase login attempt, passwords, API-key values, production changes,
# docker restarts, database writes, or public port exposure.
set -Eeuo pipefail
umask 077
STEP=INIT
trap 'rc=$?; if [[ "$rc" -ne 0 ]]; then echo "LOGIN_SERVICE_DIAGNOSTIC=FAIL step=$STEP exit=$rc"; fi; echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"; exit "$rc"' EXIT
REPO=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
REV=649f98f902555779374b870789ffb80f43f65faf
SHA=256dbd5610933252620ae9e26b2936fdab354898
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-origin-stage-v2
DB=sbi_reconciliation_main
WORK=/home/ubuntu/sbi-auth-service-diagnostic
sql() { sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() { sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== 1. READ-ONLY LIVE + STAGING BASELINE ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ -z "$(sudo -n docker port "$STAGE")" ]]
FIN_BEFORE="$(counts)"
echo "LIVE_PR129_CONTAINER=RUNNING"
echo "PRIVATE_STAGE_PUBLIC_PORTS=NONE"
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"

echo "=== 2. PINNED AUTH-SERVICE DIAGNOSTIC ==="
STEP=FETCH
curl -4 -fLsS --retry 3 -o diagnose_login_service_safe.py \
  "$REPO/$REV/database/stages23_25/diagnose_login_service_safe.py"
[[ "$(git hash-object diagnose_login_service_safe.py)" == "$SHA" ]]
python3 -m py_compile diagnose_login_service_safe.py
echo "SOURCE_SIGNATURE_VERIFIED=PASS"

echo "=== 3. EXISTING LIVE PR129 LOGIN CONFIGURATION AND FIREBASE CONNECTIVITY ==="
STEP=LIVE
sudo -n docker exec -i "$LIVE" python3 -B - < diagnose_login_service_safe.py | tee live_login_diagnostic.txt
grep -qx 'AUTH_DIAGNOSTIC_IN_CONTAINER=COMPLETE' live_login_diagnostic.txt

echo "=== 4. ISOLATED STAGING LOGIN CONFIGURATION AND FIREBASE CONNECTIVITY ==="
STEP=STAGING
sudo -n docker exec -i "$STAGE" python3 -B - < diagnose_login_service_safe.py | tee private_login_diagnostic.txt
grep -qx 'AUTH_DIAGNOSTIC_IN_CONTAINER=COMPLETE' private_login_diagnostic.txt

echo "=== 5. AUTHENTICATION CONFIGURATION KEY GAPS ==="
STEP=COMPARE
sed -n 's/^AUTH_ENV_NAME=\([^ ]*\) PRESENT=YES$/\1/p' live_login_diagnostic.txt | sort -u > live_auth_names.txt
sed -n 's/^AUTH_ENV_NAME=\([^ ]*\) PRESENT=YES$/\1/p' private_login_diagnostic.txt | sort -u > private_auth_names.txt
if comm -23 live_auth_names.txt private_auth_names.txt | grep . >/dev/null; then
  echo "LIVE_AUTH_KEYS_ABSENT_FROM_STAGING=REVIEW_REQUIRED"
  comm -23 live_auth_names.txt private_auth_names.txt | sed 's/^/MISSING_STAGING_AUTH_CONFIG_NAME=/'
else
  echo "LIVE_AUTH_KEYS_ABSENT_FROM_STAGING=NONE_OF_INSPECTED_KEYS"
fi
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
echo "LIVE_AND_PRIVATE_STAGE_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_ROWS_UNCHANGED=PASS"
STEP=COMPLETE
echo "=== FINAL LOGIN AUTH SERVICE DIAGNOSTIC ==="
echo "LOGIN_SERVICE_DIAGNOSTIC_READ_ONLY=PASS"
echo "REAL_FIREBASE_AUTHENTICATED_USER_E2E=NOT_PERFORMED"
echo "AUTHORIZED_POSTGRES_REPORT_ENDPOINT=NOT_TESTED"
echo "FINAL_RELEASE=BLOCKED_PENDING_AUTHENTICATED_STAGING_QA_AND_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=REVIEW_FIREBASE_SERVICE_CONNECTIVITY_AND_AUTH_SOURCE_ERROR_PATH"
