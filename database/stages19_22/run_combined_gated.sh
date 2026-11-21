#!/usr/bin/env bash
# SBI PR129 Central PostgreSQL — Stage 19–22 combined gated QA
# READ ONLY: no live deployment, DB writes, uploads, route exposure or Financial Engine changes.
set -Eeuo pipefail
umask 077
export PAGER=cat
STEP=START
trap 'rc=$?; echo "STAGES19_22_SAFE_QA=FAIL step=$STEP exit=$rc"; echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"; exit "$rc"' ERR

DB=sbi_reconciliation_main
APP=sbi-bulk-report-pr129-https-preview
IMAGE=sbi-pr129-postgres-stage17:isolated
WORK=/home/ubuntu/sbi-stages19-22-gated
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
AUTH_REF=160069d9c06360e8dc23e361776eb9b82500fc63
mkdir -p "$WORK" && chmod 700 "$WORK" && cd "$WORK"

STEP=PRECHECK
echo '=== PRECHECK: CURRENT DEPLOYMENT BASELINE ==='
sudo -n docker info >/dev/null
sudo -u postgres pg_isready -d "$DB" >/dev/null
sudo -n docker image inspect "$IMAGE" >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
sql() { sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() { sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
reports() { sql "SELECT (SELECT count(*) FROM sbi.invoice_financial_summary),(SELECT count(*) FROM sbi.payment_financial_summary);"; }
FIN_BEFORE="$(counts)"
REPORT_BEFORE="$(reports)"
[[ "$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema='sbi' AND table_type='BASE TABLE';")" == 14 ]]
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo 'CENTRAL_POSTGRESQL_FOUNDATION=PASS'
echo "FINANCIAL_COUNTS_BEFORE=$FIN_BEFORE"
echo "REPORT_COUNTS_BEFORE=$REPORT_BEFORE"

STEP=STAGE19
echo '=== STAGE 19: AUTHORIZATION POLICY INVENTORY ==='
curl -4 -fLsS --retry 3 -o inspect_auth_policy_masked.py "$BASE/$AUTH_REF/database/stage19/inspect_auth_policy_masked.py"
python3 -m py_compile inspect_auth_policy_masked.py
sudo -n docker exec -i "$APP" python3 -B - < inspect_auth_policy_masked.py | tee stage19_auth_inventory.txt
grep -qx 'AUTH_POLICY_AST_REVIEW=COMPLETE' stage19_auth_inventory.txt
grep -qx 'SESSION_INSTALL_CALLS= 1' stage19_auth_inventory.txt
grep -qx 'GLOBAL_PROTECT_HOOK= True' stage19_auth_inventory.txt
grep -qx 'REPORT_HANDLERS_PRESENT= True' stage19_auth_inventory.txt
echo 'STAGE19_SOURCE_INVENTORY=PASS'
echo 'STAGE19_REAL_AUTH_CALLBACK=REQUIRES_REVIEW'

STEP=STAGE20
echo '=== STAGE 20: FLASK + POSTGRESQL ADAPTER COMBINED QA ==='
sudo -n docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
 --entrypoint python3 "$IMAGE" -B -m unittest -v test_stage17_blueprint.py test_sbi_pg_reporting_combined.py

echo 'Enter only the currently valid PostgreSQL REPORT login password when requested.'
IFS= read -r -s -p 'PostgreSQL report password (hidden): ' REPORT_PASSWORD </dev/tty
printf '\n'
[[ -n "$REPORT_PASSWORD" ]]
printf '%s\n' "$REPORT_PASSWORD" | sudo -n docker run --rm -i --network none --read-only \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
 --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
 -e PGHOST=/var/run/postgresql -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
 --entrypoint python3 "$IMAGE" -B test_live_readonly_stdin_v2.py | tee stage20_adapter.txt
unset REPORT_PASSWORD
grep -qx 'ISOLATED_POSTGRES_ADAPTER_READ_ONLY=PASS' stage20_adapter.txt
inv="$(awk -F'= *' '/^invoice_report_rows=/{gsub(/\r/,"",$2); print $2}' stage20_adapter.txt | tail -1)"
pay="$(awk -F'= *' '/^payment_report_rows=/{gsub(/\r/,"",$2); print $2}' stage20_adapter.txt | tail -1)"
[[ -n "$inv" && -n "$pay" && "$(reports)" == "$inv|$pay" ]]
echo 'STAGE20_ADAPTER_AND_REPORT_PARITY=PASS'

STEP=STAGE21
echo '=== STAGE 21: ISOLATED STAGING IMAGE ROUTE VALIDATION ==='
# Run synthetic Flask route checks inside the candidate, not the live service.
sudo -n docker run --rm --network none --read-only --cap-drop ALL \
 --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" \
 -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python3 "$IMAGE" -B -c '
import ast
from pathlib import Path
from flask import Flask
from pg_reporting_blueprint import pg_reporting_blueprint
source = ast.parse(Path("/app/app.py").read_text())
functions = [n for n in ast.walk(source) if isinstance(n, ast.Call)]
registered = [n for n in functions if isinstance(n.func, ast.Attribute) and n.func.attr == "register_blueprint"]
assert any(n.args and isinstance(n.args[0],ast.Name) and n.args[0].id=="pg_reporting_blueprint" for n in registered)
app = Flask("isolated_stage21")
app.register_blueprint(pg_reporting_blueprint)
resp = app.test_client().get("/api/reporting/v2/postgresql-summary")
assert resp.status_code == 403, resp.status_code
print("STAGE21_CANDIDATE_BLUEPRINT_WIRED=PASS")
print("STAGE21_UNAUTHENTICATED_ROUTE_DENIED=PASS")
print("STAGE21_STAGING_SERVICE_DEPLOYMENT=NOT_PERFORMED")'

STEP=STAGE22
echo '=== STAGE 22: LIVE RELEASE READINESS AND SAFETY GATE ==='
for route in /auth/me /api/reporting/v2 /api/bulk-report/status; do
 status="$(curl -4 -sS --max-time 12 -o /dev/null -w '%{http_code}' "https://pr129.13-232-241-221.sslip.io$route" || true)"
 echo "LIVE_ANONYMOUS_HTTP=$route:$status"
 [[ "$status" == 401 || "$status" == 403 ]]
done
[[ "$(counts)" == "$FIN_BEFORE" ]]
[[ "$(reports)" == "$REPORT_BEFORE" ]]
[[ "$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" == "$LIVE_BEFORE" ]]
echo 'STAGE22_LIVE_ANONYMOUS_GUARDS=PASS'
echo 'FINANCIAL_ROW_COUNTS_STABLE=PASS'
echo 'LIVE_PR129_CONTAINER_UNCHANGED=PASS'

echo '=== COMBINED STAGE 19-22 SUMMARY ==='
echo 'STAGES19_22_SAFE_QA=PASS'
echo 'STAGE19_SOURCE_POLICY_AUDIT=PASS'
echo 'STAGE19_REAL_AUTH_CALLBACK=NOT_YET_VERIFIED'
echo 'STAGE20_COMBINED_ADAPTER_QA=PASS'
echo 'STAGE21_ISOLATED_CANDIDATE_QA=PASS'
echo 'STAGE21_STAGING_SERVICE_DEPLOYMENT=NOT_PERFORMED'
echo 'STAGE22_RELEASE_READINESS=BLOCKED_PENDING_AUTHENTICATED_USER_QA'
echo 'STAGE22_LIVE_ACTIVATION=NOT_PERFORMED'
echo 'FINANCIAL_ENGINE=UNCHANGED'
echo 'DATABASE_FINANCIAL_WRITES_BY_TEST=NONE'
echo 'NEXT_GATE=REVIEW_AUTH_CALLBACK_AND_TEST_AUTHENTICATED_STAGING_ENDPOINT'
