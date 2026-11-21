#!/usr/bin/env bash
# Preview-only selected-invoice UI/API installation. Leave verified DB disconnected.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
BASE=/home/ubuntu/sbi-bulk-report-integration
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
HOST=pr129.13-232-241-221.sslip.io
FILES="index.html bulk_reports.py bulk_report_excel.py bulk_report_selection.py invoice_number_selection.py"
cd "$REPO"

echo '=== SELECTED INVOICE PREVIEW INSTALL ==='
[ "$(git branch --show-current)" = ui/bulk-report-reports-tab-20261121 ]
[ -z "$(git status --porcelain --untracked-files=no)" ]
[ "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET" ]
[ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ]
sudo docker exec "$C" python -c '
import os
if os.environ.get("INVOICE_LOOKUP_BACKEND"):
    raise SystemExit("STOP: VERIFIED LOOKUP CONFIG ALREADY SET")
print("VERIFIED_LOOKUP_BACKEND=DISCONNECTED")
'
for f in $FILES; do test -s "dashboard_source/$f"; done
python3 -m py_compile dashboard_source/bulk_reports.py dashboard_source/bulk_report_excel.py dashboard_source/bulk_report_selection.py dashboard_source/invoice_number_selection.py
python3 - <<'PY'
from pathlib import Path
ui=Path("dashboard_source/index.html").read_text()
api=Path("dashboard_source/bulk_reports.py").read_text()
required=['id="bulk-selected-form"', 'id="bulk-report-form"', 'id="dil-imports"', 'id="dil-tower-panel"']
if any(x not in ui for x in required) or '/api/bulk-report/select-invoices-excel' not in api:
    raise SystemExit("STOP: EXPECTED_SOURCE_MARKERS_MISSING")
print("SOURCE_PREFLIGHT=PASS")
PY
BACKUP="$(mktemp -d "$BASE/pr129-selected-backup.XXXXXXXX")"
STAGED="$(mktemp -d "$BASE/pr129-selected-staged.XXXXXXXX")"
chmod 0700 "$BACKUP" "$STAGED"
trap 'rm -rf "$STAGED"' EXIT
CHANGING=0
restore() {
 if [ "$CHANGING" = 1 ]; then
  echo SELECTED_PREVIEW_ROLLBACK=STARTED
  for f in $FILES; do
   if [ -f "$BACKUP/$f" ]; then sudo docker cp "$BACKUP/$f" "$C:/app/$f" || true; fi
  done
  if [ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ]; then
   sudo docker restart "$C" >/dev/null || true
  else
   sudo docker start "$C" >/dev/null || true
  fi
  echo SELECTED_PREVIEW_ROLLBACK=ATTEMPTED
 fi
}
trap restore ERR
for f in $FILES; do
 if sudo docker cp "$C:/app/$f" "$BACKUP/$f" 2>/dev/null; then
  sudo chown "$(id -u):$(id -g)" "$BACKUP/$f"
  chmod 0644 "$BACKUP/$f"
 else
  : > "$BACKUP/$f.absent"
 fi
done
CHANGING=1
for f in $FILES; do
 install -m 0644 "dashboard_source/$f" "$STAGED/$f"
 sudo docker cp "$STAGED/$f" "$C:/app/$f"
done
sudo docker restart "$C" >/dev/null

sudo docker exec -i "$C" python - <<'PY'
from app import app
from pathlib import Path
ui=Path("/app/index.html").read_text()
routes={str(r):set(r.methods) for r in app.url_map.iter_rules()}
checks={
 "INVOICE_SELECTION_UI":'id="bulk-selected-form"' in ui,
 "INVOICE_SELECTION_API":"POST" in routes.get("/api/bulk-report/select-invoices-excel",set()),
 "INVOICE_SELECTION_PARSER":Path("/app/invoice_number_selection.py").is_file(),
 "EXISTING_COMBINED_XLSX":"POST" in routes.get("/api/bulk-report/generate-excel",set()),
 "DATABASE_UPDATE":'id="dil-imports"' in ui,
 "CONTROL_TOWER":'id="dil-tower-panel"' in ui,
}
for name,ok in checks.items():
 print(name+"="+("PASS" if ok else "FAIL"))
if not all(checks.values()):
 raise SystemExit(1)
PY
HTTP=000
for i in 1 2 3 4 5 6 7 8; do
 HTTP="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" -sS --max-time 10 -o /dev/null -w '%{http_code}' "https://$HOST/login" 2>/dev/null || true)"
 [ "$HTTP" = 200 ] && break
 sleep 2
done
[ "$HTTP" = 200 ]
ANON="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" -sS --max-time 10 -o /dev/null -w '%{http_code}' "https://$HOST/api/bulk-report/select-invoices-excel" 2>/dev/null || true)"
case "$ANON" in 401|403) ;; *) echo "ANONYMOUS_SELECTED_ROUTE_HTTP=$ANON"; false ;; esac
CHANGING=0
trap - ERR
echo "PREVIEW_LOGIN_HTTP=$HTTP"
echo "ANONYMOUS_SELECTED_ROUTE_HTTP=$ANON"
echo SELECTED_INVOICE_PREVIEW=PASS
echo VERIFIED_LOOKUP_BACKEND=DISCONNECTED
echo "ROLLBACK_BACKUP=$BACKUP"
echo PUBLIC_APPLICATION=UNCHANGED
echo FINANCIAL_WRITES=NONE
