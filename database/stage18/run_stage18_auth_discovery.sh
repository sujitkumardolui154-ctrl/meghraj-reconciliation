#!/usr/bin/env bash
# SBI Stage 18: combined, read-only PR129 authorization discovery.
# Does NOT enable the PostgreSQL route, deploy any container, run financial
# matching or import data.
set -Eeuo pipefail
umask 077
export PAGER=cat
STEP=INIT
trap 'rc=$?; echo "STAGE18_DISCOVERY_QA=FAIL step=$STEP code=$rc"; echo "LIVE_PR129_DEPLOYMENT=NOT_PERFORMED"; exit "$rc"' ERR
WORK=/home/ubuntu/sbi-stage18-auth-audit
APP=sbi-bulk-report-pr129-https-preview
CANDIDATE=sbi-pr129-postgres-stage17:isolated
DB=sbi_reconciliation_main
URL=https://pr129.13-232-241-221.sslip.io
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/de265b81b226337880fdf34717fd10c5abac0489/database/stage18
mkdir -p "$WORK"
chmod 700 "$WORK"
cd "$WORK"

echo "=== A. DATABASE/DOCKER FOUNDATION ==="
STEP=FOUNDATION
sudo -n docker info >/dev/null
sudo -u postgres pg_isready -d "$DB" >/dev/null
tables=$(sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='sbi' AND table_type='BASE TABLE';")
[[ "$tables" == 14 ]]
echo "DATABASE_TABLES=14 PASS"
financial_counts() {
  sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
BEFORE=$(financial_counts)
LIVE_BEFORE=$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')
echo "PR129_LIVE_BACKEND=FOUND"

echo "=== B. AUTHORIZATION SOURCE INVENTORY ==="
STEP=SOURCE_INSPECTION
curl -4 -fLsS --retry 3 -o inspect_pr129_auth_ast.py "$BASE/inspect_pr129_auth_ast.py"
python3 -m py_compile inspect_pr129_auth_ast.py
sudo -n docker exec -i "$APP" python3 -B - < inspect_pr129_auth_ast.py | tee auth_inventory.log
grep -qx 'SESSION_INSTALL_CALLED= True' auth_inventory.log
grep -qx 'EXPECTED_SIX_BLUEPRINTS= True' auth_inventory.log
grep -qx 'STAGE18_AUTH_SOURCE_INSPECTION=COMPLETE' auth_inventory.log
echo "AUTH_SOURCE_INVENTORY=PASS"

echo "=== C. LIVE ANONYMOUS ACCESS DENIAL ==="
STEP=ROUTE_GUARDS
for path in /auth/me /api/reporting/v2 /api/bulk-report/status; do
  status=$(curl -4 -sS --max-time 15 -o /dev/null -w '%{http_code}' "$URL$path" || true)
  echo "ANONYMOUS_CHECK=$path HTTP=$status"
  [[ "$status" == 401 || "$status" == 403 ]]
done
echo "LIVE_PR129_ANONYMOUS_GUARDS=PASS"

echo "=== D. STAGE17 CANDIDATE DEFAULT DENIAL ==="
STEP=CANDIDATE
sudo -n docker image inspect "$CANDIDATE" >/dev/null
sudo -n docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$CANDIDATE" -B -c \
  'from flask import Flask; from pg_reporting_blueprint import pg_reporting_blueprint; a=Flask("audit"); a.register_blueprint(pg_reporting_blueprint); r=a.test_client().get("/api/reporting/v2/postgresql-summary"); assert r.status_code == 403, r.status_code; print("STAGE17_NEW_ROUTE_DEFAULT_DENY=PASS")'

echo "=== E. FINANCIAL AND LIVE CONTAINER STABILITY ==="
STEP=STABILITY
AFTER=$(financial_counts)
LIVE_AFTER=$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')
[[ "$BEFORE" == "$AFTER" ]]
[[ "$LIVE_BEFORE" == "$LIVE_AFTER" ]]
echo "FINANCIAL_COUNTS_STABLE=PASS"
echo "LIVE_PR129_CONTAINER_STABLE=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE18 RESULT ==="
echo "STAGE18_DISCOVERY_QA=PASS"
echo "AUTH_SOURCE_INVENTORY=PASS"
echo "LIVE_PR129_ANONYMOUS_GUARDS=PASS"
echo "STAGE17_NEW_ROUTE_DEFAULT_DENY=PASS"
echo "FINANCIAL_COUNTS_STABLE=PASS"
echo "LIVE_PR129_CONTAINER_STABLE=PASS"
echo "REAL_REPORT_AUTH_CALLBACK=REQUIRES_REVIEW"
echo "AUTHENTICATED_USER_ROUTE_QA=NOT_PERFORMED"
echo "STAGE18_DEPLOYMENT=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "NEXT=REVIEW_REPORT_AUTH_POLICY_AND_WIRE_STAGE18_CANDIDATE"
