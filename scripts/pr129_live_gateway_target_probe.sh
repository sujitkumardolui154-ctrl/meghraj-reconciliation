#!/usr/bin/env bash
# Identify the main public SBI live upstream and exact Caddy report routing.
# Zero changes: no Caddy reload/edit, no container restart, no invoice reads,
# no credentials printed, no Firestore writes, no source modifications.
set -Eeuo pipefail
CADDY=aws_lightsail-caddy-1
MAIN=aws_lightsail-sbi-preview-1
REPORT=sbi-source-reports-v1
PREVIEW=sbi-bulk-report-pr129-https-preview
echo '=== PR129 PUBLIC SBI LIVE GATEWAY TARGET VERIFICATION ==='

for C in "$CADDY" "$MAIN" "$REPORT" "$PREVIEW"; do
  if ! sudo docker inspect "$C" >/dev/null 2>&1; then
    echo "CONTAINER=$C EXISTS=NO"
    continue
  fi
  echo "CONTAINER=$C EXISTS=YES"
  sudo docker inspect "$C" --format '  RUNNING={{.State.Running}} IMAGE_ID={{.Image}}'
  sudo docker inspect "$C" --format '  NETWORKS={{range $n,$_ := .NetworkSettings.Networks}}{{$n}};{{end}}'
done

echo '=== PUBLIC CADDY ROUTE ORDER (NO AUTH SETTINGS) ==='
if ! sudo docker exec "$CADDY" test -r /etc/caddy/Caddyfile; then
  echo 'STOP_CADDY_CONFIGURATION_UNREADABLE'; exit 1
fi
sudo docker exec "$CADDY" awk '
{
  line=$0
  # Report only routing tokens, no header values, credentials or env vars.
  if (line ~ /(reverse_proxy|handle|handle_path|route|respond|redir|path|@bulk|@report)/) {
     if (line ~ /(Authorization|Bearer|token|secret|password|apikey|api_key)/) next
     gsub(/#.*$/, "", line)
     if (length(line)>200) line=substr(line,1,200)
     printf "CADDY_ROUTE_LINE_%d=%s\n", NR,line
  }
}
' /etc/caddy/Caddyfile

echo '=== ACTUAL MAIN LIVE APP ROUTE REGISTRATION ==='
if [ "$(sudo docker inspect "$MAIN" --format '{{.State.Running}}')" != true ]; then
  echo 'MAIN_LIVE_APP=STOPPED'; exit 1
fi
sudo docker exec -i -w /app "$MAIN" python -B - <<'PY'
from pathlib import Path
try:
    from app import app
except Exception as exc:
    print("MAIN_APP_IMPORT=UNAVAILABLE")
    print("ERROR_TYPE="+type(exc).__name__)
    raise SystemExit(1)
routes={str(r):set(r.methods) for r in app.url_map.iter_rules()}
for code,path,method in (
    ("BULK_STATUS","/api/bulk-report/status","GET"),
    ("BULK_ZIP","/api/bulk-report/generate","POST"),
    ("BULK_COMBINED_XLSX","/api/bulk-report/generate-excel","POST"),
    ("BULK_SELECTED_XLSX","/api/bulk-report/select-invoices-excel","POST"),
    ("INVOICE_IMPORT_PREVIEW","/api/invoices/preview","POST"),
    ("CREDIT_NOTE_REPORT","/api/reports/credit-note.csv","GET"),
):
    print("LIVE_ROUTE_"+code+"="+
          ("REGISTERED" if method in routes.get(path,set()) else "MISSING"))
ui=Path("/app/index.html")
if ui.is_file():
    s=ui.read_text(encoding="utf-8",errors="replace")
    for key,piece in (
        ("BULK_FORM",'id="bulk-report-form"'),
        ("SELECTED_INVOICE_FORM",'id="bulk-selected-form"'),
        ("DATABASE_UPDATE",'id="dil-imports"'),
        ("CONTROL_TOWER",'id="dil-tower-panel"'),
    ):
        print("LIVE_UI_"+key+"="+("PRESENT" if piece in s else "MISSING"))
print("LIVE_MAIN_APP_ROUTE_CHECK=COMPLETE")
PY

echo '=== REQUIRED DEPLOYMENT CONNECTIONS ==='
sudo docker inspect "$CADDY" --format 'CADDY_MOUNTS={{range .Mounts}}{{.Destination}};{{end}}'
sudo docker inspect "$MAIN" --format 'MAIN_MOUNTS={{range .Mounts}}{{.Destination}};{{end}}'
sudo docker inspect "$PREVIEW" --format 'PREVIEW_MOUNTS={{range .Mounts}}{{.Destination}};{{end}}'
echo 'PUBLIC_CADDY_CHANGED=NO'
echo 'DOCKER_CONTAINERS_CHANGED=NO'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
echo 'PR129_LIVE_GATEWAY_TARGET_PROBE=COMPLETE'
