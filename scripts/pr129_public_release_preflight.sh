#!/usr/bin/env bash
# PR129: strictly read-only release preflight of the LIVE public Workspace.
# Run before preparing an image/route swap. No financial writes, no Caddy edits.
set -Eeuo pipefail

PUBLIC='sbi-source-reports-v1'
PREVIEW='sbi-bulk-report-pr129-https-preview'
CADDY='aws_lightsail-caddy-1'
REPO='/home/ubuntu/sbi-bulk-report-integration/repo'

echo '=== PR129 LIVE SOURCE RELEASE PREFLIGHT ==='
echo 'SCOPE=COMBINED_XLSX_ONLY'
echo 'FINANCIAL_WRITES=NOT_REQUESTED'
echo 'PUBLIC_CONFIG_CHANGE=NOT_REQUESTED'

if [ -d "$REPO/.git" ]; then
  echo "GIT_BRANCH=$(git -C "$REPO" branch --show-current)"
  echo "GIT_REVISION=$(git -C "$REPO" rev-parse --short HEAD)"
  git -C "$REPO" status --short | head -15
fi

for C in "$PUBLIC" "$PREVIEW"; do
  echo "=== CONTAINER=$C ==="
  if ! sudo docker container inspect "$C" >/dev/null 2>&1; then
    echo 'CONTAINER=MISSING'
    continue
  fi
  sudo docker inspect "$C" \
    --format 'STATE={{.State.Status}} IMAGE={{.Config.Image}} RESTARTS={{.RestartCount}} NETWORK_MODE={{.HostConfig.NetworkMode}}'
  echo 'NETWORK_NAMES:'
  sudo docker inspect "$C" \
    --format '{{range $name, $net := .NetworkSettings.Networks}}{{println $name}}{{end}}'
  echo 'APP_FILE_IDENTITIES:'
  for file in index.html app.py dashboard.js dashboard_sessions.py \
      bulk_reports.py bulk_report_excel.py invoice_source_schema.py \
      sbi_reporting_bundle.py; do
    sudo docker cp "$C:/app/$file" - 2>/dev/null \
      | tar -xOf - 2>/dev/null \
      | sha256sum \
      | awk -v f="$file" '{print f " SHA256=" $1}' \
      || echo "$file MISSING_OR_UNREADABLE"
  done
  if [ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ]; then
    sudo docker exec -i "$C" python - <<'PY'
from pathlib import Path
from importlib.util import find_spec
import sys
print("PYTHON_VERSION=", sys.version.split()[0])
print("OPENPYXL_INSTALLED=", find_spec("openpyxl") is not None)
p=Path("/app/index.html")
if p.is_file():
    html=p.read_text(encoding="utf-8", errors="replace")
    for name, marker in [
        ("MODERN_WORKSPACE", "SBI Reconciliation <span>Workspace</span>"),
        ("CONTROL_TOWER", 'id="dil-tower-panel"'),
        ("REPORTS_TAB", 'id="dil-reports"'),
        ("DATABASE_UPDATE", 'id="dil-imports"'),
        ("INVOICE_PREVIEW", 'id="dil-import-form"'),
        ("PAYMENT_EVIDENCE", 'id="dil-db-payments"'),
        ("COMBINED_EXCEL_UI", 'fetch("/api/bulk-report/generate-excel"')
    ]:
        print(name+"=", marker in html)
try:
    from app import app
    routes={str(r): set(r.methods) for r in app.url_map.iter_rules()}
    for name,route in [
        ("EXCEL_POST", "/api/bulk-report/generate-excel"),
        ("LEGACY_ZIP_POST", "/api/bulk-report/generate"),
        ("BULK_STATUS", "/api/bulk-report/status"),
        ("DATABASE_PREVIEW", "/api/invoices/preview")
    ]:
        print(name+"=", route in routes, 
              "METHODS=", ",".join(sorted(routes.get(route, set())-{"HEAD","OPTIONS"})))
except Exception as exc:
    print("ROUTE_INSPECTION_ERROR=", type(exc).__name__, str(exc)[:180])
PY
  else
    echo 'APP_ROUTE_INSPECTION=SKIPPED_CONTAINER_NOT_RUNNING'
  fi
done

echo '=== PUBLIC CADDY ROUTING — READ ONLY ==='
sudo docker exec "$CADDY" sh -c \
  'grep -nE "reverse_proxy|@login|@legacy|handle" /etc/caddy/Caddyfile' \
  || echo 'CADDY_ROUTING=UNAVAILABLE'

echo 'PUBLIC_RELEASE_PREFLIGHT=COMPLETE'
echo 'PUBLIC_CADDY=UNCHANGED'
echo 'FINANCIAL_WRITES=NONE'
