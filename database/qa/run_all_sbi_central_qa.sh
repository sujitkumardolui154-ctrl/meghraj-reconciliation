#!/usr/bin/env bash
# ONE combined SBI central PostgreSQL + PR129 + isolated adapter QA.
# DOES NOT deploy, restart running PR129, import data or run Financial Engine.
set -Eeuo pipefail
umask 077
export PAGER=cat
STAGE=INIT
trap 'code=$?; echo "COMBINED_SBI_QA=FAIL stage=$STAGE code=$code"; echo "PR129_DEPLOYMENT=NOT_PERFORMED"; exit "$code"' ERR

WORK=/home/ubuntu/sbi-central-combined-qa
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
FOUND=c3422bdee2d9a2efea6412b28d9120cf5615ea12
ADAPTER=c8075f13efe8db86e57410f2f995d96522a2a76a
TEST=300066d41c623797d8059d9d7a6a1909af668571
DB=sbi_reconciliation_main

STAGE=FETCH
echo "=== A. FETCH PINNED CODE AND VERIFY SYNTAX ==="
curl -4 -fLsS --retry 3 -o foundation.sh "$BASE/$FOUND/database/qa/sbi_pr129_flask_postgres_combined_readonly.sh"
for f in sbi_pg_reporting.py test_live_readonly.py Dockerfile.qa; do
  curl -4 -fLsS --retry 3 -o "$f" "$BASE/$ADAPTER/database/adapter/$f"
done
curl -4 -fLsS --retry 3 -o test_sbi_pg_reporting_combined.py "$BASE/$TEST/database/adapter/test_sbi_pg_reporting_combined.py"
bash -n foundation.sh
python3 -m py_compile sbi_pg_reporting.py test_live_readonly.py test_sbi_pg_reporting_combined.py
echo "SOURCE_SYNTAX=PASS"

financial_counts() {
  sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
report_counts() {
  sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoice_financial_summary),(SELECT count(*) FROM sbi.payment_financial_summary);"
}
STAGE=DATABASE_SNAPSHOT
BEFORE=$(financial_counts)
REPORT_BEFORE=$(report_counts)
echo "FINANCIAL_COUNTS_BEFORE=$BEFORE"
echo "REPORT_COUNTS_BEFORE=$REPORT_BEFORE"

STAGE=FOUNDATION
echo "=== B. COMBINED POSTGRES / ROLE / DOCKER / HTTPS CHECKS ==="
bash foundation.sh | tee foundation.log
grep -qx 'COMBINED_READ_ONLY_QA=PASS' foundation.log
echo "DATABASE_INFRASTRUCTURE_QA=PASS"

STAGE=PR129_ROUTING
echo "=== C. ACTUAL PR129 REPORTING BLUEPRINT AND SESSION CHECKS ==="
sudo docker exec -i sbi-bulk-report-pr129-https-preview python3 - <<'PY'
import ast
from pathlib import Path
p=Path("/app")
app=ast.parse((p/"app.py").read_text())
report=ast.parse((p/"readonly_reports_gateway.py").read_text())
session=ast.parse((p/"dashboard_sessions.py").read_text())
calls=[n.func.id for n in ast.walk(app) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
bps={ast.unparse(n.args[0]) for n in ast.walk(app) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="register_blueprint" and n.args}
expected={"tower","workspace","payment_evidence","reconciliation_readiness","readonly_reports","bulk_report"}
handlers={n.name for n in ast.walk(report) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
guard={n.name for n in ast.walk(session) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
assert "install_sessions" in calls
assert expected.issubset(bps)
assert {"report_catalog","source_report_csv"}.issubset(handlers)
assert "protect_dashboard" in guard
print("PR129_FLASK_REGISTRATION=PASS")
print("NOTE=Structural checks alone do not prove authorization.")
PY
for path in /api/reporting/v2 /api/bulk-report/status; do
  status=$(curl -4 -sS --max-time 15 -o /dev/null -w '%{http_code}' "https://pr129.13-232-241-221.sslip.io$path" || true)
  echo "ANONYMOUS_ROUTE=$path HTTP=$status"
  [[ "$status" == 401 || "$status" == 403 ]] || { echo "ROUTE_AUTH=REVIEW_REQUIRED"; exit 3; }
done
echo "ANONYMOUS_REPORTING_AUTH_QA=PASS"

STAGE=BUILD
echo "=== D. BUILD ISOLATED DRIVER IMAGE (NOT LIVE PR129) ==="
sudo docker build -f Dockerfile.qa -t sbi-pr129-pg-report-qa:combined .
echo "ISOLATED_DRIVER_BUILD=PASS"

STAGE=UNIT
echo "=== E. COMBINED ADAPTER UNIT TESTS ==="
sudo docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,source=$WORK,target=/opt/sbi-adapter,readonly" \
  sbi-pr129-pg-report-qa:combined \
  python3 -m unittest -v test_sbi_pg_reporting_combined.py
echo "ADAPTER_UNIT_TESTS=PASS"

STAGE=LIVE_ADAPTER
echo "=== F. LIVE AUTHENTICATED READ-ONLY ADAPTER QUERY ==="
echo "Type the restricted reporting password at the hidden prompt; never share it."
sudo docker run --rm -it --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,source=$WORK,target=/opt/sbi-adapter,readonly" \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  -e PGHOST=/var/run/postgresql -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
  sbi-pr129-pg-report-qa:combined python3 test_live_readonly.py | tee adapter.log
grep -q 'ISOLATED_POSTGRES_ADAPTER_READ_ONLY=PASS' adapter.log
inv=$(awk -F'= *' '/^invoice_report_rows=/{gsub(/\r/,"",$2); print $2}' adapter.log | tail -1)
pay=$(awk -F'= *' '/^payment_report_rows=/{gsub(/\r/,"",$2); print $2}' adapter.log | tail -1)

STAGE=PARITY
echo "=== G. REPORT PARITY AND FINANCIAL COUNT STABILITY ==="
AFTER=$(financial_counts)
REPORT_AFTER=$(report_counts)
echo "FINANCIAL_COUNTS_AFTER=$AFTER"
echo "REPORT_COUNTS_AFTER=$REPORT_AFTER"
[[ "$BEFORE" == "$AFTER" ]] || { echo "FINANCIAL_COUNT_STABILITY=FAIL"; exit 4; }
[[ "$REPORT_BEFORE" == "$REPORT_AFTER" ]] || { echo "REPORT_COUNT_STABILITY=FAIL"; exit 5; }
[[ "$REPORT_AFTER" == "$inv|$pay" ]] || { echo "REPORT_ADAPTER_PARITY=FAIL"; exit 6; }

STAGE=COMPLETE
echo "=== FINAL COMBINED RESULT ==="
echo "COMBINED_SBI_QA=PASS"
echo "DATABASE_INFRASTRUCTURE_QA=PASS"
echo "PR129_REPORT_AUTH_GUARD=PASS"
echo "ADAPTER_UNIT_TESTS=PASS"
echo "ISOLATED_POSTGRES_ADAPTER_READ_ONLY=PASS"
echo "REPORT_ADAPTER_PARITY=PASS"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "LIVE_PR129_APP=UNCHANGED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "PR129_POSTGRESQL_APP_INTEGRATION=NOT_YET_DEPLOYED"
