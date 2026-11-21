#!/usr/bin/env bash
# SBI PR129 Firebase server credential QA, source-only/metadata-only.
# Does not print Google credential paths, private keys, tokens, login details,
# secret values, environment dumps, or cloud identities.
set -Eeuo pipefail
umask 077
STEP=INIT
trap 'rc=$?; if [[ "$rc" -ne 0 ]]; then echo "FIREBASE_CREDENTIAL_READONLY_QA=FAIL step=$STEP code=$rc"; fi; echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"; exit "$rc"' EXIT
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-origin-stage-v2
DB=sbi_reconciliation_main
WORK=/home/ubuntu/sbi-firebase-credential-review
REPO=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
REV=1f264a8b04febaa789f3b432689a74447acb17ed
SOURCE_SHA=52bd3af5e87d39178aad0b18d0a7d2fad8342385
counts() {
  sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
echo "=== A. CHECK LIVE AND STAGING IDENTITY ==="
STEP=BASELINE
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
[[ -z "$(sudo -n docker port "$STAGE")" ]]
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"

echo "=== B. FETCH IMMUTABLE SAFE CREDENTIAL AUDITOR ==="
STEP=FETCH
curl -4 -fLsS --retry 3 -o inspect_firebase_credential_dependency.py "$REPO/$REV/database/stages23_25/inspect_firebase_credential_dependency.py"
[[ "$(git hash-object inspect_firebase_credential_dependency.py)" == "$SOURCE_SHA" ]]
python3 -m py_compile inspect_firebase_credential_dependency.py
echo "CREDENTIAL_AUDITOR_HASH_AND_SYNTAX=PASS"

echo "=== C. LIVE PR129 GOOGLE APPLICATION CREDENTIAL READINESS ==="
STEP=LIVE
sudo -n docker exec -i "$LIVE" python3 -B - < inspect_firebase_credential_dependency.py | tee live_credential_audit.txt
grep -qx 'CREDENTIAL_DEPENDENCY_AUDIT=COMPLETE' live_credential_audit.txt

echo "=== D. PRIVATE STAGING GOOGLE APPLICATION CREDENTIAL READINESS ==="
STEP=STAGE
sudo -n docker exec -i "$STAGE" python3 -B - < inspect_firebase_credential_dependency.py | tee stage_credential_audit.txt
grep -qx 'CREDENTIAL_DEPENDENCY_AUDIT=COMPLETE' stage_credential_audit.txt

echo "=== E. CREDENTIAL READINESS COMPARISON ==="
STEP=COMPARE
for key in GOOGLE_CREDENTIAL_ENV_PRESENT GOOGLE_CREDENTIAL_FILE_EXISTS GOOGLE_CREDENTIAL_FILE_READABLE; do
  live="$(grep "^$key=" live_credential_audit.txt | head -1 | cut -d= -f2- || true)"
  stage="$(grep "^$key=" stage_credential_audit.txt | head -1 | cut -d= -f2- || true)"
  echo "CREDENTIAL_COMPARE_KEY=$key LIVE=$live STAGING=$stage"
done

echo "=== F. SAFETY CHECK ==="
STEP=STABILITY
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
echo "LIVE_AND_PRIVATE_STAGING_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL FIREBASE CREDENTIAL DEPENDENCY QA ==="
echo "FIREBASE_CREDENTIAL_READONLY_QA=PASS"
echo "PRODUCTION_CREDENTIALS_COPIED=NO"
echo "REAL_FIREBASE_AUTHENTICATED_USER_E2E=NOT_PERFORMED"
echo "AUTHORIZED_POSTGRES_REPORT_ENDPOINT=NOT_TESTED"
echo "LIVE_RELEASE=BLOCKED_PENDING_AUTHENTICATED_STAGING_QA_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=VERIFY_CREDENTIAL_DEPENDENCY_BEFORE_CONFIGURING_SCOPED_STAGING_AUTH"
