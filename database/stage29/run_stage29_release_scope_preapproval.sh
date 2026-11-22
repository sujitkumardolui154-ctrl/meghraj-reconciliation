#!/usr/bin/env bash
# Stage29 limited-scope review only. Never cut over, reload Caddy or write source financial rows.
set -Eeuo pipefail
umask 077
STEP=INIT
DB=sbi_reconciliation_main
LIVE=sbi-bulk-report-pr129-https-preview
STAGE25=sbi-pr129-pg-stage25-firebase-adc
STAGE26=sbi-pr129-pg-modernui-stage26r2
CADDY=aws_lightsail-caddy-1
NET=sbi_pr129_pg_staging_only
BACKUPS=/home/ubuntu/sbi-db-backups
EVIDENCE=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVIDENCE";chmod 700 "$EVIDENCE"
REPORT="$EVIDENCE/stage29_preapproval_$(date -u +%Y%m%dT%H%M%SZ).txt"
exec > >(tee "$REPORT") 2>&1
finish(){
 local rc=$?
 trap - EXIT
 if ((rc));then echo "STAGE29_COMBINED_PREAPPROVAL_QA=FAIL step=$STEP exit=$rc"
 else echo "STAGE29_COMBINED_PREAPPROVAL_QA=PASS";fi
 echo "STAGE29_OWNER_APPROVAL=NOT_GIVEN"
 echo "STAGE30_LIVE_PR129_CUTOVER=NOT_PERFORMED"
 echo "FINANCIAL_SOURCE_WRITES_BY_QA=NONE"
 echo "STAGE29_EVIDENCE_FILE=$REPORT"
 exit "$rc"
}
trap finish EXIT
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== A. LIVE / PRIVATE CANDIDATE BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$STAGE25" "$STAGE26" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "REQUIRED_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
LIVE_BASE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
S25_BASE="$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
S26_BASE="$(sudo -n docker inspect "$STAGE26" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
CADDY_BASE="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ -z "$(sudo -n docker port "$STAGE26")" ]]
[[ "$(sudo -n docker inspect "$STAGE26" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
FIN_BASE="$(counts)"
echo "STAGE29_PRIVATE_CANDIDATE_NETWORK=PASS"
echo "STAGE29_NO_PUBLISHED_STAGING_PORTS=PASS"

echo "=== B. MODERN WORKSPACE, FIREBASE AUTH AND REPORT ROUTES ==="
STEP=APP
sudo -n docker exec -i "$STAGE26" python3 -B - <<'PY'
from pathlib import Path
from app import app
from sbi_report_access import can_view_report
import google.auth,inspect,os
h=Path("/app/index.html").read_text()
for name,value in {
 "WORKSPACE":'SBI Reconciliation <span>Workspace</span>',
 "DASHBOARD":'id="dil-tower-panel"',
 "REPORTS":'id="dil-reports"',
 "DATABASE_UPDATE":'id="dil-imports"',
 "BULK_REPORT":'id="bulk-report-form"',
 "SELECTED_INVOICE_DISABLED":'id="bulk-selected-button" disabled',
}.items():
 assert value in h,name
 print("STAGE29_UI_"+name+"=PASS")
assert google.auth.default()[1]=="meghraj-reconciliation"
assert list(inspect.signature(can_view_report).parameters)==["user","identity","change_report"]
assert not Path("/app/pr129_aws_invoice_lookup.enabled").exists()
assert not os.getenv("INVOICE_LOOKUP_BACKEND")
routes={r.rule:set(r.methods) for r in app.url_map.iter_rules()}
for path,method in {
 "/auth/session":"POST",
 "/api/reporting/v2/postgresql-summary":"GET",
 "/api/bulk-report/generate-excel":"POST",
 "/api/bulk-report/select-invoices-excel":"POST",
}.items():
 assert method in routes.get(path,set()),path
client=app.test_client()
for path in ("/api/reporting/v2/postgresql-summary","/api/bulk-report/status"):
 assert client.get(path).status_code in (401,403)
for path in ("/api/bulk-report/generate-excel","/api/bulk-report/select-invoices-excel"):
 assert client.post(path).status_code in (401,403)
print("STAGE29_FIREBASE_ADC_AND_ANONYMOUS_DENIAL=PASS")
print("STAGE29_SELECTED_INVOICE_LOOKUP=NOT_CONNECTED_DISABLED")
print("STAGE29_BULK_EXCEL_REAL_DATA_PARITY=NOT_TESTED")
PY

echo "=== C. POSTGRESQL ROLE ACCESS AND READ-ONLY SOURCE ==="
STEP=POSTGRES
sudo -n docker exec -i "$STAGE26" python3 -B - <<'PY'
import psycopg
with psycopg.connect(connect_timeout=8) as c:
 c.execute("SET TRANSACTION READ ONLY")
 assert c.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()==(
 "sbi_pr129_report_login","sbi_reconciliation_main","on")
 perms=c.execute(
 "SELECT has_table_privilege(current_user,'sbi.invoices','INSERT'),"
 "has_table_privilege(current_user,'sbi.payments','INSERT'),"
 "has_table_privilege(current_user,'sbi.allocations','INSERT'),"
 "has_table_privilege(current_user,'sbi.credit_notes','INSERT')"
 ).fetchone()
 assert perms==(False,False,False,False)
 c.execute("SELECT count(*) FROM sbi.invoice_financial_summary").fetchone()
 c.execute("SELECT count(*) FROM sbi.payment_financial_summary").fetchone()
print("STAGE29_AUTHORIZED_POSTGRES_READER=PASS")
print("STAGE29_FINANCIAL_INSERT_PRIVILEGES=DENIED")
PY

echo "=== D. ENCRYPTED BACKUP PRESENCE AND SOURCE CHECKSUM ==="
STEP=BACKUP
[[ -d "$BACKUPS" ]]
BACKUP_FILE="$(find "$BACKUPS" -maxdepth 2 -type f -name 'sbi_reconciliation_main.dump.enc' -printf '%T@ %p\n' | sort -nr | sed -n '1s/^[^ ]* //p')"
[[ -n "$BACKUP_FILE" && -s "$BACKUP_FILE" && ! -L "$BACKUP_FILE" ]] || {
 echo "STAGE29_ENCRYPTED_BACKUP=NOT_FOUND";exit 21; }
[[ "$(stat -c '%a' "$BACKUP_FILE")" == 600 ]] ||
 { echo "STAGE29_ENCRYPTED_BACKUP_FILE_PERMISSIONS=REVIEW_REQUIRED";exit 22; }
[[ "$(stat -c '%a' "$(dirname "$BACKUP_FILE")")" == 700 ]] ||
 { echo "STAGE29_ENCRYPTED_BACKUP_DIR_PERMISSIONS=REVIEW_REQUIRED";exit 23; }
echo "STAGE29_ENCRYPTED_BACKUP_FILE=PASS"
echo "STAGE29_BACKUP_DIRECTORY=$(basename "$(dirname "$BACKUP_FILE")")"
echo "STAGE29_ENCRYPTED_BACKUP_SHA256=$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
echo "STAGE29_OFFHOST_HASH=OWNER_WINDOWS_SCREENSHOT_PASS_NOT_RETESTED_BY_AWS"
echo "STAGE29_SOURCE_RECOVERY_REHEARSAL=STAGE28_PASS_NOT_RERUN"

echo "=== E. PREVIOUS IMAGE, CADDY NETWORK AND ROLLBACK PREPARATION ==="
STEP=ROLLBACK
LIVE_IMAGE="$(sudo -n docker inspect "$LIVE" --format '{{.Image}}')"
NEW_IMAGE="$(sudo -n docker inspect "$STAGE26" --format '{{.Image}}')"
sudo -n docker image inspect "$LIVE_IMAGE" "$NEW_IMAGE" >/dev/null
echo "STAGE29_PREVIOUS_LIVE_IMAGE_AVAILABLE=PASS"
echo "STAGE29_APPROVED_CANDIDATE_IMAGE_AVAILABLE=PASS"
echo "STAGE29_OLD_IMAGE_DIGEST=$LIVE_IMAGE"
echo "STAGE29_CANDIDATE_IMAGE_DIGEST=$NEW_IMAGE"
CADDY_NETS="$(sudo -n docker inspect "$CADDY" --format '{{range $name,$v := .NetworkSettings.Networks}}{{$name}} {{end}}')"
STAGE_NETS="$(sudo -n docker inspect "$STAGE26" --format '{{range $name,$v := .NetworkSettings.Networks}}{{$name}} {{end}}')"
SHARED=NO
for a in $CADDY_NETS;do
 for b in $STAGE_NETS;do
  [[ "$a" == "$b" ]] && SHARED=YES
 done
done
echo "STAGE29_CADDY_PRIVATE_STAGE_SHARED_NETWORK=$SHARED"
if sudo -n docker exec "$CADDY" sh -c 'test -r /etc/caddy/Caddyfile';then
 echo "STAGE29_CADDY_SHA256=$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')"
else
 echo "STAGE29_CADDY_SHA256=NOT_AVAILABLE_REVIEW_REQUIRED"
fi
echo "STAGE30_ROUTABLE_PRODUCTION_DEPLOYMENT_PLAN=REQUIRED"
echo "STAGE30_ROLLBACK_COMMANDS=NOT_YET_VERIFIED"
echo "STAGE29_CADDY_ROUTE_CHANGE=NONE"

echo "=== F. NO PRODUCTION OR FINANCIAL CHANGES ==="
STEP=STABILITY
[[ "$LIVE_BASE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$S25_BASE" == "$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$S26_BASE" == "$(sudo -n docker inspect "$STAGE26" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$CADDY_BASE" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BASE" == "$(counts)" ]]
[[ -z "$(sudo -n docker port "$STAGE26")" ]]
echo "STAGE29_LIVE_PR129_UNCHANGED=PASS"
echo "STAGE29_STAGE25_UNCHANGED=PASS"
echo "STAGE29_STAGE26R2_UNCHANGED=PASS"
echo "STAGE29_CADDY_UNCHANGED=PASS"
echo "STAGE29_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE29 LIMITED RELEASE PREAPPROVAL ==="
echo "STAGE29_UI_AUTH_AND_REPORT_ROUTES=PASS"
echo "STAGE29_POSTGRES_READ_ONLY=PASS"
echo "STAGE29_ENCRYPTED_BACKUP_INVENTORY=PASS"
echo "STAGE29_ROLLBACK_IMAGE_INVENTORY=PASS"
echo "STAGE29_PROPOSED_SCOPE=MODERN_UI_FIREBASE_READONLY_REPORTS_SYNTHETIC_TESTED_EXCEL"
echo "STAGE29_DISABLED=FINANCIAL_ENGINE_FINANCIAL_WRITES_SELECTED_INVOICE_LOOKUP"
echo "STAGE29_RELEASE=REVIEW_REQUIRED_STAGE30_CUTOVER_PLAN_AND_OWNER_APPROVAL"
echo "NEXT=OWNER_REVIEW_LIMITED_SCOPE_AND_PREPARE_REVERSIBLE_STAGE30_PLAN"
echo "FINANCIAL_ENGINE=UNCHANGED"
