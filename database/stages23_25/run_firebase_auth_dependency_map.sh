#!/usr/bin/env bash
# Combined read-only Firebase dependency and error-path mapping.
# Does not copy service-account files or touch credentials.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-origin-stage-v2
DB=sbi_reconciliation_main
WORK=/home/ubuntu/sbi-auth-dependency-map
REPO=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
REV=ee85a38bea2a51e0697f87b9c307760485ed229f
MAP_SHA=71a7cef3a3ba5c03563420ae4aa996368a43c3c3
trap 'rc=$?; if ((rc));then echo "FIREBASE_AUTH_DEPENDENCY_QA=FAIL step=$STEP exit=$rc";fi;echo "LIVE_PR129_CUTOVER=NOT_PERFORMED";exit "$rc"' EXIT
counts() {
  sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c \
    "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
echo "=== A. PR129 AND PRIVATE STAGING SAFETY BASELINE ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ -z "$(sudo -n docker port "$STAGE")" ]]
FIN_BEFORE="$(counts)"
mkdir -p "$WORK";chmod 700 "$WORK";cd "$WORK"
echo "STAGING_PUBLIC_PORTS=NONE"

echo "=== B. IMMUTABLE CREDENTIAL-SAFE SOURCE INSPECTOR ==="
STEP=FETCH
curl -4 -fLsS --retry 3 -o map_firebase_login_dependency_safe.py \
  "$REPO/$REV/database/stages23_25/map_firebase_login_dependency_safe.py"
[[ "$(git hash-object map_firebase_login_dependency_safe.py)" == "$MAP_SHA" ]]
python3 -m py_compile map_firebase_login_dependency_safe.py
echo "AUTH_MAP_SIGNATURE_VERIFIED=PASS"

echo "=== C. SOURCE-LEVEL AUTH LOGIN DEPENDENCIES IN LIVE PR129 ==="
STEP=LIVE_SOURCE
sudo -n docker exec -i "$LIVE" python3 -B - < map_firebase_login_dependency_safe.py | tee live_auth_map.txt
grep -qx 'AUTH_DEPENDENCY_MAPPING=COMPLETE' live_auth_map.txt

echo "=== D. SOURCE-LEVEL AUTH LOGIN DEPENDENCIES IN PRIVATE STAGING ==="
STEP=STAGE_SOURCE
sudo -n docker exec -i "$STAGE" python3 -B - < map_firebase_login_dependency_safe.py | tee staging_auth_map.txt
grep -qx 'AUTH_DEPENDENCY_MAPPING=COMPLETE' staging_auth_map.txt

echo "=== E. VERIFY CENTRAL DATA AND CONTAINERS UNCHANGED ==="
STEP=SAFETY
[[ "$FIN_BEFORE" == "$(counts)" ]]
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
echo "CENTRAL_FINANCIAL_COUNTS_STABLE=PASS"
echo "LIVE_AND_STAGING_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL FIREBASE AUTH DEPENDENCY MAPPING ==="
echo "FIREBASE_AUTH_DEPENDENCY_QA=PASS"
echo "SERVICE_ACCOUNT_CREDENTIALS_COPIED=NO"
echo "AUTHENTICATED_FIREBASE_USER_E2E=NOT_PERFORMED"
echo "AUTHORIZED_POSTGRES_REPORT=NOT_TESTED"
echo "FINAL_DEPLOYMENT=BLOCKED_PENDING_REAL_USER_AUTH_QA_AND_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=REVIEW_AUTH_UNAVAILABLE_TEXT_SOURCE_AND_CREDENTIAL_DEPENDENCY_BEFORE_STAGING_CREDENTIAL_PROVISIONING"
