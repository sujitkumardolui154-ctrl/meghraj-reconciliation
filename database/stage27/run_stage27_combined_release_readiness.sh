#!/usr/bin/env bash
# Stage 27 - combined READ ONLY PR129 candidate release-readiness checks.
# No production deployment, Caddy edits, restarts, database writes, or credential display.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
STAGE25=sbi-pr129-pg-stage25-firebase-adc
CANDIDATE=sbi-pr129-pg-modernui-stage26r2
NET=sbi_pr129_pg_staging_only
DB=sbi_reconciliation_main
BACKUP=/home/ubuntu/sbi-db-backups/sbi_main_initial.dump
finish() {
 rc=$?
 trap - EXIT
 if ((rc));then echo "STAGE27_COMBINED_RELEASE_QA=FAIL step=$STEP exit=$rc"
 else echo "STAGE27_COMBINED_RELEASE_QA=PASS";fi
 echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
 echo "FINANCIAL_WRITES_BY_QA=NONE"
 exit "$rc"
}
trap finish EXIT
sql() {
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"
}
counts() {
 sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}

echo "=== 1. BASELINE SECURITY ==="
STEP=BASELINE
sudo -n docker info >/dev/null
LIVE_BASE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE25_BASE="$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
CANDIDATE_BASE="$(sudo -n docker inspect "$CANDIDATE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$STAGE25" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$CANDIDATE" --format '{{.State.Running}}')" == true ]]
[[ -z "$(sudo -n docker port "$CANDIDATE")" ]]
[[ "$(sudo -n docker inspect "$CANDIDATE" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
DB_BASE="$(counts)"
echo "LIVE_AND_PRIVATE_STAGES_RUNNING=PASS"
echo "STAGE27_PUBLIC_PORTS=NONE"

echo "=== 2. SOURCE-LEVEL UI, ROUTE AND AUTH GATES ==="
STEP=FLASK_QA
sudo -n docker exec -i "$CANDIDATE" python3 -B - <<'PY'
from pathlib import Path
from app import app
import google.auth
from sbi_report_access import can_view_report
import inspect
html=Path("/app/index.html").read_text()
markers={
 "MODERN_UI":'SBI Reconciliation <span>Workspace</span>',
 "CONTROL_TOWER":'id="dil-tower-panel"',
 "REPORTS":'id="dil-reports"',
 "DATABASE_UPDATE":'id="dil-imports"',
 "PAYMENTS":'id="dil-db-payments"',
 "BULK_REPORT":'id="bulk-report-form"',
 "SELECTED_INVOICE_FORM":'id="bulk-selected-form"',
 "SELECTED_LOOKUP_DISABLED":'id="bulk-selected-button" disabled',
}
for name,term in markers.items():
 assert term in html,name
 print("UI_CHECK_"+name+"=PASS")
assert not Path("/app/pr129_aws_invoice_lookup.enabled").exists()
assert list(inspect.signature(can_view_report).parameters)==["user","identity","change_report"]
assert google.auth.default()[1]=="meghraj-reconciliation"
routes={r.rule:set(r.methods) for r in app.url_map.iter_rules()}
for path,method in {
 "/":"GET", "/login":"GET", "/auth/session":"POST",
 "/auth/csrf":"GET", "/api/reporting/v2":"GET",
 "/api/reporting/v2/postgresql-summary":"GET",
 "/api/bulk-report/status":"GET",
 "/api/bulk-report/generate-excel":"POST",
 "/api/bulk-report/select-invoices-excel":"POST",
 "/dashboard.js":"GET","/account.js":"GET",
 "/dashboard-theme.css":"GET",
}.items():
 assert method in routes.get(path,set()), path
print("STAGE27_UI_AND_BACKEND_ROUTE_CONTRACT=PASS")
client=app.test_client()
for path in ("/api/reporting/v2",
             "/api/reporting/v2/postgresql-summary",
             "/api/bulk-report/status"):
 response=client.get(path)
 assert response.status_code in (401,403),(path,response.status_code)
for path in ("/api/bulk-report/generate-excel",
             "/api/bulk-report/select-invoices-excel"):
 response=client.post(path)
 assert response.status_code in (401,403),(path,response.status_code)
print("STAGE27_ANONYMOUS_ACCESS=DENIED")
print("STAGE27_FIREBASE_ADC_PROJECT=PASS")
print("STAGE27_SELECTED_INVOICE_LOOKUP=DISABLED")
PY

echo "=== 3. SYNTHETIC COMBINED EXCEL REGRESSION ==="
STEP=EXCEL_QA
sudo -n docker exec -i "$CANDIDATE" python3 -B -m unittest -q \
 test_bulk_report_combined_excel \
 test_bulk_report_selection \
 test_invoice_number_selection
echo "STAGE27_SYNTHETIC_EXCEL_QA=PASS"

echo "=== 4. POSTGRESQL LIVE CONNECTION READ-ONLY GATE ==="
STEP=POSTGRES_QA
sudo -n docker exec -i "$CANDIDATE" python3 -B - <<'PY'
import psycopg
with psycopg.connect(connect_timeout=8) as conn:
 conn.execute("SET TRANSACTION READ ONLY")
 info=conn.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()
 assert info==("sbi_pr129_report_login","sbi_reconciliation_main","on")
 flags=conn.execute(
   "SELECT has_table_privilege(current_user,'sbi.invoices','INSERT'),"
   "has_table_privilege(current_user,'sbi.payments','INSERT'),"
   "has_table_privilege(current_user,'sbi.allocations','INSERT'),"
   "has_table_privilege(current_user,'sbi.credit_notes','INSERT')"
 ).fetchone()
 assert flags==(False,False,False,False)
 invoice_count=conn.execute("SELECT count(*) FROM sbi.invoice_financial_summary").fetchone()[0]
 payment_count=conn.execute("SELECT count(*) FROM sbi.payment_financial_summary").fetchone()[0]
 assert invoice_count>=0 and payment_count>=0
 print("STAGE27_INVOICE_REPORT_ROWS="+str(invoice_count))
 print("STAGE27_PAYMENT_REPORT_ROWS="+str(payment_count))
print("STAGE27_POSTGRES_READ_ONLY=PASS")
print("STAGE27_FINANCIAL_INSERT_PERMISSIONS=DENIED")
PY

echo "=== 5. BACKUP CATALOG / LIVE IMAGE ROLLBACK INVENTORY ==="
STEP=BACKUP
if [[ -s "$BACKUP" ]]; then
 if sudo -n pg_restore -l "$BACKUP" >/dev/null 2>&1;then
  echo "STAGE27_BACKUP_ARCHIVE_CATALOG=PASS"
 else
  echo "STAGE27_BACKUP_ARCHIVE_CATALOG=FAIL"
  exit 22
 fi
else
 echo "STAGE27_BACKUP_ARCHIVE_CATALOG=NOT_FOUND_REVIEW_REQUIRED"
fi
sudo -n docker image inspect "$(sudo -n docker inspect "$LIVE" --format '{{.Image}}')" >/dev/null
sudo -n docker image inspect "$(sudo -n docker inspect "$CANDIDATE" --format '{{.Image}}')" >/dev/null
echo "STAGE27_LIVE_AND_CANDIDATE_IMAGES=AVAILABLE"
echo "STAGE27_RESTORE_REHEARSAL=HISTORICAL_PASS_NOT_REPEATED"
echo "STAGE27_OFF_HOST_BACKUP=NOT_VERIFIED"
echo "STAGE27_ROLLBACK_EXECUTION=NOT_PERFORMED"

echo "=== 6. IMMUTABILITY AND FINANCIAL STABILITY ==="
STEP=IMMUTABILITY
[[ "$LIVE_BASE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE25_BASE" == "$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$CANDIDATE_BASE" == "$(sudo -n docker inspect "$CANDIDATE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$DB_BASE" == "$(counts)" ]]
[[ -z "$(sudo -n docker port "$CANDIDATE")" ]]
IP="$(sudo -n docker inspect "$CANDIDATE" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 30
echo "STAGE27_PRIVATE_IP=$IP"
echo "STAGE27_LIVE_PR129_UNCHANGED=PASS"
echo "STAGE27_STAGE25_UNCHANGED=PASS"
echo "STAGE27_STAGE26R2_UNCHANGED=PASS"
echo "STAGE27_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE27 RELEASE READINESS ==="
echo "STAGE27_UI_ROUTE_QA=PASS"
echo "STAGE27_FIREBASE_ADC_AND_ANONYMOUS_DENIAL=PASS"
echo "STAGE27_REPORT_AND_EXCEL_QA=PASS"
echo "STAGE27_POSTGRES_READ_ONLY_QA=PASS"
echo "STAGE27_REAL_USER_AUTHORIZED_REPORT=OBSERVED_BY_OWNER_NOT_AUTOMATED"
echo "STAGE27_INCOGNITO_DENIAL=OBSERVED_BY_OWNER_NOT_AUTOMATED"
echo "STAGE27_SELECTED_INVOICE_VERIFIED_LOOKUP=NOT_CONNECTED"
echo "STAGE27_LIVE_RELEASE=REVIEW_REQUIRED_LIMITED_SCOPE_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "NEXT=OWNER_REVIEW_RELEASE_SCOPE_OFFHOST_BACKUP_AND_ROLLBACK_PLAN"
