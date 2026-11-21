#!/usr/bin/env bash
# PR129: fix XLSX monetary types AND calendar dates in isolated AWS preview.
# No invoice-source, Firestore, auth, Caddy or production changes.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
BASE=/home/ubuntu/sbi-bulk-report-integration
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
HOST=pr129.13-232-241-221.sslip.io
FILES="bulk_report_excel.py test_bulk_report_combined_excel.py test_aws_verified_invoice_lookup.py"
cd "$REPO"

echo '=== PR129 NUMERIC MONEY + DATE XLSX EXPORT FIX — PREVIEW ONLY ==='
test "$(git branch --show-current)" = ui/bulk-report-reports-tab-20261121
test -z "$(git status --porcelain --untracked-files=no)"
test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true
test "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET"
sudo docker exec -i -w /app "$C" python -B - <<'PY'
from pathlib import Path
from app import app
marker=Path("/app/pr129_aws_invoice_lookup.enabled")
assert marker.is_file() and marker.read_text() == "AWS_FIRESTORE_READONLY_PR129\n"
routes={str(r):set(r.methods) for r in app.url_map.iter_rules()}
assert "POST" in routes.get("/api/bulk-report/select-invoices-excel",set())
assert "POST" in routes.get("/api/bulk-report/generate-excel",set())
print("EXISTING_AWS_LOOKUP=ENABLED")
print("PREVIEW_SELECTED_AND_COMBINED_ROUTES=PASS")
PY
for f in $FILES; do test -s "dashboard_source/$f"; done
python3 -m py_compile \
  dashboard_source/bulk_report_excel.py \
  dashboard_source/test_bulk_report_combined_excel.py \
  dashboard_source/test_aws_verified_invoice_lookup.py

BACKUP="$(mktemp -d "$BASE/pr129-money-format-backup.XXXXXXXX")"
STAGE="$(mktemp -d "$BASE/pr129-money-format-stage.XXXXXXXX")"
chmod 0700 "$BACKUP" "$STAGE"
trap 'rm -rf "$STAGE"' EXIT
CHANGING=0
rollback() {
 if [ "$CHANGING" -eq 1 ]; then
   echo 'MONEY_FORMAT_PREVIEW_ROLLBACK=STARTED'
   for f in $FILES; do
     if [ -f "$BACKUP/$f" ]; then
       sudo docker cp "$BACKUP/$f" "$C:/app/$f" || true
     elif [ -f "$BACKUP/$f.absent" ]; then
       sudo docker exec -u 0 "$C" rm -f "/app/$f" || true
     fi
   done
   sudo docker restart "$C" >/dev/null || true
   echo 'MONEY_FORMAT_PREVIEW_ROLLBACK=ATTEMPTED'
 fi
}
trap rollback ERR
for f in $FILES; do
  if sudo docker cp "$C:/app/$f" "$BACKUP/$f" >/dev/null 2>&1; then
    sudo chown "$(id -u):$(id -g)" "$BACKUP/$f"
    chmod 0644 "$BACKUP/$f"
  else
    : > "$BACKUP/$f.absent"
  fi
done
CHANGING=1
for f in $FILES; do
  install -m 0644 "dashboard_source/$f" "$STAGE/$f"
  sudo docker cp "$STAGE/$f" "$C:/app/$f"
  expected="$(sha256sum "$STAGE/$f" | awk '{print $1}')"
  actual="$(sudo docker exec "$C" sha256sum "/app/$f" | awk '{print $1}')"
  if [ "$expected" != "$actual" ]; then
    echo "FILE_HASH_MISMATCH=$f"
    false
  fi
  echo "INSTALLED_FILE_HASH_VERIFIED=$f"
done

# Offline synthetic QA checks XLSX money and date cells, source-only and selected
# invoice workflows, source-matched 53-column IDs, formula-injection safety,
# and previously working status/category sheets. NO live invoice rows queried.
sudo docker exec -i -w /app "$C" python -B -m unittest -v \
  test_bulk_report_combined_excel \
  test_aws_verified_invoice_lookup

sudo docker exec -i -w /app "$C" python -B - <<'PY'
from pathlib import Path
import bulk_report_excel as mod
from app import app
from datetime import datetime
assert 13 in mod.AMOUNT_COLUMN_INDEXES
assert 14 in mod.AMOUNT_COLUMN_INDEXES
assert 20 in mod.AMOUNT_COLUMN_INDEXES
assert 12 not in mod.AMOUNT_COLUMN_INDEXES
assert 6 not in mod.AMOUNT_COLUMN_INDEXES
assert mod._excel_money("2.4299999999999997") == 2.43
assert mod._excel_money("43.739999999999995") == 43.74
assert mod._excel_money("CANCLED") is None
assert mod._excel_money("CREDIT NOTE") is None
assert mod._excel_money("1.005") == 1.005
assert mod.DATE_COLUMN_FORMATS == {
    4: "mmmm yyyy", 5: "dd/mm/yyyy", 21: "dd/mm/yyyy",
    23: "dd/mm/yyyy", 36: "dd/mm/yyyy",
}
assert mod._excel_date("2023-10-17T00:00:00") == datetime(2023,10,17)
assert mod._excel_date("2023-09-01") == datetime(2023,9,1)
assert mod._excel_date("CANCLED") is None
assert mod._excel_date("Mar-May 2026") is None
assert Path("/app/pr129_aws_invoice_lookup.enabled").read_text() == "AWS_FIRESTORE_READONLY_PR129\n"
print("NUMERIC_AMOUNT_FORMAT=PASS")
print("DATE_AND_MONTH_FORMAT=PASS")
print("INVOICE_IDENTIFIERS_PRESERVED=PASS")
print("STATUS_TEXT_PRESERVED=PASS")
print("FIRESTORE_LOOKUP_GATE_PRESERVED=PASS")
PY

sudo docker restart "$C" >/dev/null

# Verify the exact LIVE container bytes AFTER restart and generate one
# synthetic XLSX via its freshly loaded modules. No real invoice is queried.
expected="$(sha256sum dashboard_source/bulk_report_excel.py | awk '{print $1}')"
actual="$(sudo docker exec "$C" sha256sum /app/bulk_report_excel.py | awk '{print $1}')"
test "$expected" = "$actual"
echo 'LIVE_CONTAINER_EXPORTER_SHA_MATCH=PASS'

sudo docker exec -i -w /app "$C" python -B - <<'PY'
import hashlib
import io
from openpyxl import load_workbook
from invoice_number_selection import Selection
from bulk_report_selection import build_selection_zip
from bulk_report_excel import combined_excel_from_report_zip
columns=[""]*53
columns[4]="2023-09-01T00:00:00"
columns[5]="2023-10-10T00:00:00"
columns[12]="SYNTHETIC-ONLY"
columns[14]="2.4299999999999997"
columns[15]="43.739999999999995"
columns[20]="31.86"
columns[21]="2023-10-17T00:00:00"
result={
    "version":"invoice-selection-v1",
    "dataset":"SYNTHETIC_ONLY",
    "source_kind":"VERIFIED_READ_ONLY_REPORT_SOURCE",
    "financial_writes":False,
    "reconciliation_executed":False,
    "database_updated":False,
    "matches":[{"invoice_no":"SYNTHETIC-ONLY", "values":columns,
                "payment_kind":"ok", "balance_review":False}],
    "review":[],
    "requested_count":1,"matched_count":1,"review_count":0,
}
bundle,_=build_selection_zip(
    Selection(("SYNTHETIC-ONLY",), ()), result,
    hashlib.sha256(b"synthetic only").hexdigest(),
)
workbook=load_workbook(
    io.BytesIO(combined_excel_from_report_zip(bundle)),
    read_only=True,data_only=False,
)
try:
    row=workbook["All Invoices"]
    assert row["M2"].data_type=="s"
    assert row["O2"].data_type=="n" and row["O2"].value==2.43
    assert row["P2"].data_type=="n" and row["P2"].value==43.74
    assert row["U2"].data_type=="n" and row["U2"].value==31.86
    assert row["E2"].data_type=="d"
    assert row["E2"].number_format=="mmmm yyyy"
    assert row["F2"].data_type=="d" and row["F2"].number_format=="dd/mm/yyyy"
    assert row["V2"].data_type=="d"
    assert row["V2"].value.strftime("%d/%m/%Y")=="17/10/2023"
    assert len(workbook.sheetnames)==7
    print("LIVE_CONTAINER_SYNTHETIC_XLSX_MONEY_AND_DATES=PASS")
finally:
    workbook.close()
PY

HTTP=000
for i in 1 2 3 4 5 6 7 8; do
  HTTP="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    "https://$HOST/login" 2>/dev/null || true)"
  [ "$HTTP" = 200 ] && break
  sleep 2
done
[ "$HTTP" = 200 ]
ANON="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    "https://$HOST/api/bulk-report/select-invoices-excel" 2>/dev/null || true)"
case "$ANON" in 401|403) ;; *) echo "STOP: ANONYMOUS_HTTP=$ANON"; false ;; esac

CHANGING=0
trap - ERR
echo 'PR129_NUMERIC_DATE_EXPORT_QA=PASS'
echo 'AWS_PREVIEW_MONEY_DATE_FORMAT_FIX=DEPLOYED'
echo "PREVIEW_LOGIN_HTTP=$HTTP"
echo "ANONYMOUS_SELECTED_ROUTE_HTTP=$ANON"
echo "ROLLBACK_BACKUP=$BACKUP"
echo 'FIRESTORE_SOURCE_RECORDS_CHANGED=NONE'
echo 'FINANCIAL_WRITES=NONE'
echo 'PRODUCTION_DEPLOYMENT=NOT_PERFORMED'
echo 'NEW_CLOUD_RUN_DEPLOYMENT=NOT_PERFORMED'
