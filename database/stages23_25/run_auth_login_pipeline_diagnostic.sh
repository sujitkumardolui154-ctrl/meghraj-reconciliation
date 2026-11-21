#!/usr/bin/env bash
# Targeted Firebase login failure diagnosis in live PR129 and repaired private
# staging. Metadata only; no credentials/tokens/code bodies, no login attempt,
# no DB modification, no Docker restart, no public route change.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-auth-parity-stage
DB=sbi_reconciliation_main
WORK=/home/ubuntu/sbi-auth-pipeline-investigation
SOURCE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/571bad316a2b2a135dbd2e64947c6aa126fa77fc/database/stages23_25/inspect_real_login_pipeline_safe.py
SOURCE_HASH=2bd83f17252f5c081cb48113fecad129df68ff7b
on_exit(){
 rc=$?
 trap - EXIT
 if ((rc));then echo "AUTH_LOGIN_PIPELINE_QA=FAIL step=$STEP exit=$rc";else echo "AUTH_LOGIN_PIPELINE_QA=PASS";fi
 echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
 exit "$rc"
}
trap on_exit EXIT
counts(){
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
echo "=== A. PRECHECK LIVE, PRIVATE STAGING, AND DATABASE SAFETY ==="
STEP=BASELINE
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
[[ -z "$(sudo -n docker port "$STAGE")" ]]
echo "LIVE_PR129_AND_STAGING_BASELINE=PASS"
echo "PRIVATE_STAGING_PUBLIC_PORTS=NONE"

echo "=== B. PINNED AUTH PATH INSPECTION SOURCE ==="
STEP=FETCH
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"
curl -4 -fLsS --retry 3 -o inspect_real_login_pipeline_safe.py "$SOURCE"
[[ "$(git hash-object inspect_real_login_pipeline_safe.py)" == "$SOURCE_HASH" ]]
python3 -m py_compile inspect_real_login_pipeline_safe.py
echo "SOURCE_INTEGRITY_AND_SYNTAX=PASS"

echo "=== C. LIVE PR129 AUTHENTICATION PIPELINE ==="
STEP=LIVE_INSPECT
sudo -n docker exec -i "$LIVE" python3 -B - < inspect_real_login_pipeline_safe.py | tee live_auth_pipeline.txt
grep -qx "AUTH_LOGIN_PIPELINE_INSPECTION=COMPLETE" live_auth_pipeline.txt

echo "=== D. PRIVATE STAGING AUTHENTICATION PIPELINE ==="
STEP=STAGE_INSPECT
sudo -n docker exec -i "$STAGE" python3 -B - < inspect_real_login_pipeline_safe.py | tee stage_auth_pipeline.txt
grep -qx "AUTH_LOGIN_PIPELINE_INSPECTION=COMPLETE" stage_auth_pipeline.txt

echo "=== E. COMPARE MODULE HASHES AND AUTH ROUTE HANDLERS ==="
STEP=COMPARE
for name in app.py dashboard_sessions.py cloud_auth.py sbi_report_access.py;do
 live="$(grep "^SOURCE=$name STATUS=PRESENT SHA256=" live_auth_pipeline.txt | sed 's/^.*SHA256=//' | head -1)"
 stage="$(grep "^SOURCE=$name STATUS=PRESENT SHA256=" stage_auth_pipeline.txt | sed 's/^.*SHA256=//' | head -1)"
 if [[ -n "$live" && "$live" == "$stage" ]];then
   echo "AUTH_SOURCE_PARITY=$name STATUS=MATCH"
 else
   echo "AUTH_SOURCE_PARITY=$name STATUS=DIFF_OR_MISSING"
 fi
done
if grep -q "^AUTH_ROUTE=/auth/session " stage_auth_pipeline.txt;then
 echo "STAGING_AUTH_SESSION_ROUTE=PRESENT"
else
 echo "STAGING_AUTH_SESSION_ROUTE=MISSING"
fi

echo "=== F. PROTECT LIVE AND CENTRAL DATA ==="
STEP=STABILITY
[[ "$FIN_BEFORE" == "$(counts)" ]]
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
echo "LIVE_AND_STAGING_CONTAINERS_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL AUTH LOGIN FAILURE DIAGNOSIS ==="
echo "AUTH_PIPELINE_SOURCE_DIAGNOSTIC=PASS"
echo "REAL_FIREBASE_USER_SIGNIN=NOT_TESTED"
echo "AUTHORIZED_POSTGRES_REPORT_ENDPOINT=NOT_TESTED"
echo "PRODUCTION_RELEASE=BLOCKED_PENDING_AUTHENTICATED_USER_QA_AND_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=REVIEW_ACTUAL_AUTH_ERROR_FUNCTION_AND_CREDENTIAL_REQUIREMENTS"
