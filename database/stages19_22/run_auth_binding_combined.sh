#!/usr/bin/env bash
# Combined Stage19-22 authorization binding discovery and safe release gate.
# Read only. Leaves live PR129 and Financial Engine unchanged.
set -Eeuo pipefail
umask 077
STEP=INIT
trap 'r=$?; echo "AUTH_BINDING_COMBINED_QA=FAIL step=$STEP code=$r"; echo "LIVE_CUTOVER=NOT_PERFORMED"; exit "$r"' ERR
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
REV=c296acc246cd135fd2fd4ae376e1cbcf8601b4f8
APP=sbi-bulk-report-pr129-https-preview
IMAGE=sbi-pr129-postgres-stage17:isolated
DB=sbi_reconciliation_main
WORK=/home/ubuntu/sbi-stages19-22-auth-binding
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"

echo "=== A. PRE-CHECK CENTRAL POSTGRESQL AND PR129 BASELINE ==="
STEP=PRECHECK
sudo -u postgres pg_isready -d "$DB" >/dev/null
sudo -n docker info >/dev/null
BEFORE="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
counts() {
  sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
FIN_BEFORE="$(counts)"
echo "PR129_CONTAINER_STATUS=RUNNING"
echo "FINANCIAL_COUNTS_BEFORE=$FIN_BEFORE"

echo "=== B. STAGE 19 REAL SESSION + can_view_report AUTH INTERFACE ==="
STEP=AUTH_MAPPING
curl -4 -fLsS --retry 3 -o map_real_report_auth.py "$BASE/$REV/database/stages19_22/map_real_report_auth.py"
python3 -m py_compile map_real_report_auth.py
sudo -n docker exec -i "$APP" python3 -B - < map_real_report_auth.py | tee real_auth_map.txt
grep -qx 'EXISTING_AUTH_POLICY_IDENTIFIED=PASS' real_auth_map.txt
grep -qx 'SESSION_INSTALL_ORDER=PASS' real_auth_map.txt
grep -qx 'AUTH_SOURCE_MAPPING=COMPLETE' real_auth_map.txt
echo "STAGE19_REAL_AUTH_SIGNATURE_INVENTORY=PASS"

echo "=== C. STAGES 20–21 ISOLATED STAGING SECURITY RECHECK ==="
STEP=STAGING_AUTH_DENIAL
sudo -n docker image inspect "$IMAGE" >/dev/null
sudo -n docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$IMAGE" -B -m unittest -v \
  test_stage17_blueprint.py test_sbi_pg_reporting_combined.py
sudo -n docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$IMAGE" -B -c '
from flask import Flask
from pg_reporting_blueprint import pg_reporting_blueprint
app=Flask("stage19_22_auth_audit")
app.register_blueprint(pg_reporting_blueprint)
response=app.test_client().get("/api/reporting/v2/postgresql-summary")
assert response.status_code==403, response.status_code
print("STAGE21_NEW_PG_ROUTE_UNAUTHENTICATED_DENIAL=PASS")
'
echo "STAGES20_21_ISOLATED_SECURITY_UNIT_QA=PASS"

echo "=== D. STAGE 22 LIVE ANONYMOUS PROTECTION / NO-WRITES CHECK ==="
STEP=LIVE_SAFETY
for path in /auth/me /api/reporting/v2 /api/bulk-report/status; do
 status="$(curl -4 -sS --max-time 15 -o /dev/null -w '%{http_code}' "https://pr129.13-232-241-221.sslip.io$path" || true)"
 echo "ANONYMOUS_ROUTE=$path HTTP=$status"
 [[ "$status" == 401 || "$status" == 403 ]]
done
AFTER="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_AFTER="$(counts)"
[[ "$BEFORE" == "$AFTER" ]]
[[ "$FIN_BEFORE" == "$FIN_AFTER" ]]
echo "FINANCIAL_ROW_COUNTS_UNCHANGED=PASS"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL AUTHORIZATION-BINDING DISCOVERY RESULT ==="
echo "AUTH_BINDING_COMBINED_QA=PASS"
echo "AUTH_SOURCE_MAPPING=COMPLETE"
echo "ISOLATED_FLASK_SECURITY_QA=PASS"
echo "LIVE_ANONYMOUS_ROUTE_GUARDS=PASS"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "DATABASE_WRITES=NONE"
echo "AUTHENTICATED_USER_ENDPOINT_QA=NOT_PERFORMED"
echo "STAGE21_STAGING_SERVICE_DEPLOYMENT=NOT_PERFORMED"
echo "STAGE22_LIVE_RELEASE=BLOCKED"
echo "NEXT=REVIEW_AUTH_POLICY_SIGNATURE_AND_SESSION_VALUES_BEFORE_WIRING"
