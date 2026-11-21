#!/usr/bin/env bash
# SBI live AWS Bulk Report deployment inventory — read-only.
# Distinguishes isolated PR129 preview from MAIN live gateway.
# No copying files, no Caddy reload, no restart, no DB reads/writes.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
cd "$REPO"
echo '=== SBI MAIN LIVE VS PR129 PREVIEW — REPORT INVENTORY ==='
echo "GIT_BRANCH=$(git branch --show-current)"
echo "GIT_REVISION=$(git rev-parse --short HEAD)"
echo 'OPERATIONS=READ_ONLY'
echo 'FIRESTORE_QUERIES=NONE'

# Preview must remain clearly separate. Never infer live from preview.
PREVIEW=sbi-bulk-report-pr129-https-preview
if sudo docker inspect "$PREVIEW" >/dev/null 2>&1; then
  echo "PR129_PREVIEW_RUNNING=$(sudo docker inspect "$PREVIEW" --format '{{.State.Running}}')"
  echo "PR129_PREVIEW_NETWORK=$(sudo docker inspect "$PREVIEW" --format '{{.HostConfig.NetworkMode}}')"
fi

names="$(sudo docker ps --format '{{.Names}}')"
if [ -z "$names" ]; then echo 'STOP_NO_RUNNING_DOCKER_CONTAINERS'; exit 1; fi

echo '=== LIVE CONTAINERS WITH REPORT-RELATED CONTENT (NO FILE CONTENT) ==='
found_main=0
found_live=0
while IFS= read -r name; do
  [ -n "$name" ] || continue
  case "$name" in
    *pr129*|*stage*|*canary*|*readonly-stage*) continue ;;
  esac
  found_main=$((found_main+1))
  echo "CONTAINER=$name"
  image="$(sudo docker inspect "$name" --format '{{.Config.Image}}')"
  network="$(sudo docker inspect "$name" --format '{{.HostConfig.NetworkMode}}')"
  echo "CONTAINER_IMAGE_REFERENCE=$image"
  echo "CONTAINER_NETWORK=$network"
  for entry in /app/index.html /app/production_gateway.py /app/bulk_reports.py /app/bulk_report_excel.py /app/aws_verified_invoice_lookup.py /app/sbi_report_access.py /app/pr129_aws_invoice_lookup.enabled; do
    if sudo docker exec "$name" sh -c 'test -f "$1"' _ "$entry" >/dev/null 2>&1; then
      echo "INSTALLED_FILE=$entry"
      case "$entry" in /app/bulk_reports.py) found_live=$((found_live+1));; esac
    fi
  done
  # Only infer routes from source/compiled Flask if present, never use
  # anonymous HTTP 401 as proof of registered route.
  if sudo docker exec "$name" sh -c 'test -f /app/bulk_reports.py' >/dev/null 2>&1; then
    if sudo docker exec "$name" grep -q 'select-invoices-excel' /app/bulk_reports.py 2>/dev/null; then
      echo 'SOURCE_SELECTED_INVOICE_ROUTE=PRESENT'
    else
      echo 'SOURCE_SELECTED_INVOICE_ROUTE=MISSING'
    fi
    if sudo docker exec "$name" grep -q 'generate-excel' /app/bulk_reports.py 2>/dev/null; then
      echo 'SOURCE_COMBINED_BULK_ROUTE=PRESENT'
    else
      echo 'SOURCE_COMBINED_BULK_ROUTE=MISSING'
    fi
    if sudo docker exec "$name" sh -c 'test -f /app/bulk_report_excel.py' >/dev/null 2>&1; then
      if sudo docker exec "$name" grep -q 'DATE_COLUMN_FORMATS' /app/bulk_report_excel.py 2>/dev/null; then
        echo 'SOURCE_MONEY_AND_DATE_EXPORTER=NEW'
      else
        echo 'SOURCE_MONEY_AND_DATE_EXPORTER=OLD_OR_MISSING'
      fi
    fi
  fi
  # Only report Caddy routing cues, not the full config, hostnames or secrets.
  if sudo docker exec "$name" sh -c 'test -f /etc/caddy/Caddyfile' >/dev/null 2>&1; then
    echo 'CADDY_CONTAINER=YES'
    if sudo docker exec "$name" grep -q 'bulk-report' /etc/caddy/Caddyfile 2>/dev/null; then
      echo 'CADDY_BULK_REPORT_RULE=EXPLICITLY_PRESENT'
    else
      echo 'CADDY_BULK_REPORT_RULE=NO_EXPLICIT_MATCH'
    fi
    if sudo docker exec "$name" grep -q 'sbi-source-reports' /etc/caddy/Caddyfile 2>/dev/null; then
      echo 'CADDY_SOURCE_REPORTS_ROUTE=REFERENCED'
    fi
  fi
done <<< "$names"

echo '=== KNOWN MAIN SBI LIVE UPSTREAM — REGISTERED FLASK ROUTES ==='
PUBLIC=sbi-source-reports-v1
if sudo docker inspect "$PUBLIC" >/dev/null 2>&1; then
  if [ "$(sudo docker inspect "$PUBLIC" --format '{{.State.Running}}')" = true ]; then
    sudo docker exec -i -w /app "$PUBLIC" python -B - <<'PY' || echo 'LIVE_APP_ROUTE_INSPECTION=UNAVAILABLE'
from pathlib import Path
from importlib.util import find_spec
from app import app

routes={str(r):set(r.methods) for r in app.url_map.iter_rules()}
for label, path in (
    ("LIVE_SELECTED_INVOICE_POST","/api/bulk-report/select-invoices-excel"),
    ("LIVE_COMBINED_EXCEL_POST","/api/bulk-report/generate-excel"),
    ("LIVE_BULK_STATUS_GET","/api/bulk-report/status"),
):
    allowed="GET" if label.endswith("_GET") else "POST"
    print(label+"="+("REGISTERED" if allowed in routes.get(path,set()) else "MISSING"))

p=Path("/app/index.html")
if p.is_file():
    html=p.read_text(encoding="utf-8", errors="replace")
    print("LIVE_SELECTED_INVOICE_UI="+("PRESENT" if 'id="bulk-selected-form"' in html else "MISSING"))
    print("LIVE_BULK_REPORT_UI="+("PRESENT" if 'id="bulk-report-form"' in html else "MISSING"))

excel=Path("/app/bulk_report_excel.py")
print("LIVE_EXCEL_EXPORTER="+("PRESENT" if excel.is_file() else "MISSING"))
if excel.is_file():
    txt=excel.read_text(encoding="utf-8",errors="replace")
    print("LIVE_EXCEL_DATE_FORMAT_FIX="+("PRESENT" if "DATE_COLUMN_FORMATS" in txt else "MISSING"))
    print("LIVE_EXCEL_MONEY_FORMAT_FIX="+("PRESENT" if "AMOUNT_COLUMN_INDEXES" in txt else "MISSING"))
PY
  else
    echo 'LIVE_PUBLIC_UPSTREAM=NOT_RUNNING'
  fi
else
  echo 'LIVE_PUBLIC_UPSTREAM=NOT_FOUND'
fi

echo "NONPREVIEW_NONSTAGING_CONTAINERS_CHECKED=$found_main"
echo "NONPREVIEW_CONTAINERS_WITH_BULK_REPORT_SOURCE=$found_live"
echo 'AUTHENTICATED_LIVE_BROWSER_WORKFLOW=NOT_TESTED'
echo 'SOURCE_IMAGE_PROVENANCE=NOT_VERIFIED'
echo 'MAIN_LIVE_DEPLOYMENT=REQUIRES_ROUTE_AND_IMAGE_CONFIRMATION'
echo 'PUBLIC_GATEWAY_CHANGED=NO'
echo 'PRODUCTION_DEPLOYMENT=NOT_PERFORMED'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
echo 'SBI_LIVE_BULK_REPORT_INVENTORY=COMPLETE'
