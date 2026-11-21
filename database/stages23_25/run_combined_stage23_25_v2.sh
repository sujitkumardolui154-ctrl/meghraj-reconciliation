#!/usr/bin/env bash
# SBI PR129 Stage 23/24/25 combined targeted fix for verified session-name mismatch.
# Does not expose credentials, connect the Financial Engine, write to database,
# start a public service or replace/restart live PR129.
set -Eeuo pipefail
umask 077
export PAGER=cat
STEP=INIT
trap 'rc=$?; echo "STAGE23_CONTEXT_FIX_QA=FAIL step=$STEP exit=$rc"; echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"; exit "$rc"' ERR

REPO=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
PIN=b786758db72e37c7abf2ef39d04741582cf29472
STAGE=/home/ubuntu/sbi-stage23-auth-context-v2
APP=sbi-bulk-report-pr129-https-preview
BASE=sbi-pr129-postgres-stage17:isolated
CANDIDATE=sbi-pr129-pg-stage23-v2:isolated
DB=sbi_reconciliation_main
mkdir -p "$STAGE"
chmod 700 "$STAGE"
cd "$STAGE"

sql() { sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() { sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

STEP=BASELINE
echo "=== A. BASELINE SAFETY AND POSTGRESQL ==="
sudo -n docker info >/dev/null
sudo -u postgres pg_isready -d "$DB" >/dev/null
sudo -n docker image inspect "$BASE" >/dev/null
PR129_BEFORE="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
echo "FINANCIAL_COUNTS_BEFORE=$FIN_BEFORE"
echo "PR129_BASELINE=PASS"

STEP=FETCH
echo "=== B. FETCH PINNED SESSION-CONTEXT FIX ==="
for file in stage23_auth_bridge_v2.py test_stage23_auth_bridge_v2.py Dockerfile.stage23.v2; do
  curl -4 -fLsS --retry 3 -o "$file" "$REPO/$PIN/database/stages23_25/$file"
done
for file in patch_stage23_candidate.py inspect_actual_auth_contract.py; do
  curl -4 -fLsS --retry 3 -o "$file" "$REPO/$PIN/database/stages23_25/$file"
done
python3 -m py_compile stage23_auth_bridge_v2.py test_stage23_auth_bridge_v2.py patch_stage23_candidate.py inspect_actual_auth_contract.py
echo "SOURCE_SYNTAX=PASS"

STEP=SESSION
echo "=== C. VERIFY ACTUAL PR129 SESSION AND POLICY CONTRACT ==="
sudo -n docker exec -i "$APP" python3 -B - < inspect_actual_auth_contract.py | tee auth_contract.txt
grep -qx 'ACTUAL_POLICY_PARAMETERS=user,identity,change_report' auth_contract.txt
grep -qx 'STAGE23_KNOWN_POLICY_SIGNATURE=PASS' auth_contract.txt
grep -qx 'GLOBAL_BEFORE_REQUEST=True' auth_contract.txt
grep -qx 'SESSION_G_USER_DIRECT_ASSIGN=False' auth_contract.txt
grep -qx 'SESSION_G_IDENTITY_DIRECT_ASSIGN=False' auth_contract.txt
grep -qx 'SESSION_G_ATTRIBUTES_FOUND=dil_identity,dil_user' auth_contract.txt
echo "SESSION_CONTEXT_EXPECTED=g.dil_user,g.dil_identity"
echo "SESSION_CONTEXT_MAPPING=PASS"

STEP=BUILD
echo "=== D. BUILD ISOLATED STAGE23 V2 IMAGE ==="
sudo -n docker build --pull=false \
  --build-arg STAGE17_IMAGE="$BASE" \
  -f Dockerfile.stage23.v2 \
  -t "$CANDIDATE" .
echo "STAGE23_AUTH_CONTEXT_CANDIDATE_BUILD=PASS"

STEP=TESTS
echo "=== E. COMBINED AUTHORIZATION, FLASK AND REPORTING UNIT TESTS ==="
sudo -n docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$CANDIDATE" -B -m unittest -v \
  test_stage23_auth_bridge_v2.py \
  test_stage17_blueprint.py \
  test_sbi_pg_reporting_combined.py
echo "COMBINED_ISOLATED_UNIT_TESTS=PASS"

STEP=APP_ANONYMOUS
echo "=== F. ACTUAL ISOLATED PR129 FLASK APP MUST DENY ANONYMOUS REQUEST ==="
sudo -n docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$CANDIDATE" -B -c '
from app import app
assert callable(app.config.get("SBI_PG_REPORT_AUTH_CHECK"))
resp=app.test_client().get("/api/reporting/v2/postgresql-summary")
assert resp.status_code in (401,403), resp.status_code
print("STAGE24_CANDIDATE_ROUTE_ANONYMOUS_HTTP=",resp.status_code)
print("STAGE24_REAL_APP_DEFAULT_DENY=PASS")
'

STEP=RELEASE_GATE
echo "=== G. STAGE25 SAFETY GATES AND BACKUP LISTING ==="
for path in /auth/me /api/reporting/v2 /api/bulk-report/status; do
  status="$(curl -4 -sS --max-time 15 -o /dev/null -w '%{http_code}' "https://pr129.13-232-241-221.sslip.io$path" || true)"
  echo "LIVE_ANONYMOUS_ROUTE=$path HTTP=$status"
  [[ "$status" == 401 || "$status" == 403 ]]
done
[[ "$(counts)" == "$FIN_BEFORE" ]]
[[ "$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" == "$PR129_BEFORE" ]]
echo "FINANCIAL_COUNTS_STABLE=PASS"
echo "LIVE_PR129_CONTAINER_STABLE=PASS"
if test -r /home/ubuntu/sbi-db-backups/sbi_main_initial.dump && pg_restore -l /home/ubuntu/sbi-db-backups/sbi_main_initial.dump >/dev/null 2>&1; then
  echo "BACKUP_ARCHIVE_LISTING=PASS"
else
  echo "BACKUP_ARCHIVE_LISTING=REVIEW_REQUIRED"
fi

STEP=COMPLETE
echo "=== FINAL STAGE23–25 TARGETED COMBINED QA ==="
echo "STAGE23_CONTEXT_FIX_QA=PASS"
echo "EXISTING_POLICY_SIGNATURE=PASS"
echo "CORRECT_SESSION_ATTRIBUTES=g.dil_user,g.dil_identity"
echo "STAGE23_BRIDGE_WIRED_IN_CANDIDATE=PASS"
echo "STAGE24_COMBINED_SYNTHETIC_TESTS=PASS"
echo "STAGE24_ISOLATED_FLASK_ANONYMOUS_DENIAL=PASS"
echo "STAGE24_PRIVATE_STAGING_SERVICE=NOT_DEPLOYED"
echo "STAGE25_AUTHENTICATED_FIREBASE_USER_E2E=NOT_PERFORMED"
echo "STAGE25_BACKUP_RESTORE=NOT_TESTED"
echo "STAGE25_LIVE_RELEASE=BLOCKED_PENDING_AUTHENTICATED_STAGING_QA_AND_APPROVAL"
echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=PRIVATE_AUTHENTICATED_USER_STAGING_TEST_AND_RESTORE_REHEARSAL"
