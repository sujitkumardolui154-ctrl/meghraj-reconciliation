#!/usr/bin/env bash
# PR129 install AWS-only read-only invoice lookup in ISOLATED preview.
# No public Caddy, supervisor/backend or database modifications.
# Offline synthetic QA runs BEFORE the explicit feature marker is installed.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
BASE=/home/ubuntu/sbi-bulk-report-integration
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
HOST=pr129.13-232-241-221.sslip.io
FILES="bulk_reports.py aws_verified_invoice_lookup.py test_aws_verified_invoice_lookup.py"
MARKER=/app/pr129_aws_invoice_lookup.enabled
cd "$REPO"

echo '=== PR129 AWS-ONLY VERIFIED INVOICE LOOKUP PREVIEW ==='
[ "$(git branch --show-current)" = ui/bulk-report-reports-tab-20261121 ]
[ -z "$(git status --porcelain --untracked-files=no)" ]
[ "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET" ]
[ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ]

sudo docker exec -i "$C" python -B - <<'PY'
from pathlib import Path
import os
if os.environ.get("INVOICE_LOOKUP_BACKEND",""):
    raise SystemExit("STOP: PREVIEW_REMOTE_LOOKUP_ALREADY_CONFIGURED")
if Path("/app/pr129_aws_invoice_lookup.enabled").exists():
    raise SystemExit("STOP: AWS_LOOKUP_MARKER_ALREADY_EXISTS")
print("EXISTING_REMOTE_LOOKUP=DISCONNECTED")
print("AWS_FIRESTORE_LOOKUP=DISABLED_BEFORE_QA")
PY

for f in $FILES; do test -s "dashboard_source/$f"; done
python3 -m py_compile \
  dashboard_source/aws_verified_invoice_lookup.py \
  dashboard_source/test_aws_verified_invoice_lookup.py \
  dashboard_source/bulk_reports.py

BACKUP="$(mktemp -d "$BASE/pr129-aws-lookup-backup.XXXXXXXX")"
STAGED="$(mktemp -d "$BASE/pr129-aws-lookup-staged.XXXXXXXX")"
chmod 0700 "$BACKUP" "$STAGED"
trap 'rm -rf "$STAGED"' EXIT
CHANGING=0
rollback() {
  if [ "$CHANGING" = 1 ]; then
    echo 'PR129_AWS_LOOKUP_ROLLBACK=STARTED'
    sudo docker exec -u 0 "$C" rm -f "$MARKER" || true
    for f in $FILES; do
      if [ -f "$BACKUP/$f" ]; then
        sudo docker cp "$BACKUP/$f" "$C:/app/$f" || true
      elif [ -f "$BACKUP/$f.absent" ]; then
        sudo docker exec -u 0 "$C" rm -f "/app/$f" || true
      fi
    done
    sudo docker restart "$C" >/dev/null || true
    echo 'PR129_AWS_LOOKUP_ROLLBACK=ATTEMPTED'
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
  install -m 0644 "dashboard_source/$f" "$STAGED/$f"
  sudo docker cp "$STAGED/$f" "$C:/app/$f"
done

# Synthetic only: no Firestore credentials are loaded for this test.
echo '=== SYNTHETIC READ-ONLY LOOKUP & XLSX QA ==='
sudo docker exec -w /app -e PYTHONPATH=/app "$C" \
  python -B -m unittest -v test_aws_verified_invoice_lookup

# Verify direct source access is currently confirmed via last standalone probe,
# but never invoke live invoice queries as part of this installer.
sudo docker exec -i -w /app "$C" python -B - <<'PY'
from pathlib import Path
from app import app
import inspect
from aws_verified_invoice_lookup import lookup_verified_invoices
from bulk_reports import selected_invoice_excel
routes={str(r):set(r.methods) for r in app.url_map.iter_rules()}
checks={
  "SELECTED_INVOICE_API":"POST" in routes.get("/api/bulk-report/select-invoices-excel",set()),
  "EXISTING_COMBINED_REPORT":"POST" in routes.get("/api/bulk-report/generate-excel",set()),
  "MODERN_DASHBOARD":'id="dil-imports"' in Path("/app/index.html").read_text(),
  "LOOKUP_MARKER_NOT_YET_ACTIVE":not Path("/app/pr129_aws_invoice_lookup.enabled").exists(),
  "AWS_LOOKUP_MODULE":callable(lookup_verified_invoices),
  "SELECTED_API_CALLABLE":callable(selected_invoice_excel),
}
for label,ok in checks.items():
    print(label+"="+("PASS" if ok else "FAIL"))
if not all(checks.values()):
    raise SystemExit("STOP: PR129_SOURCE_GATE_FAILED")
PY

# Enable ONLY the isolated authenticated PR129 preview. No docker recreate.
printf 'AWS_FIRESTORE_READONLY_PR129\n' > "$STAGED/pr129_aws_invoice_lookup.enabled"
chmod 0644 "$STAGED/pr129_aws_invoice_lookup.enabled"
sudo docker cp "$STAGED/pr129_aws_invoice_lookup.enabled" "$C:$MARKER"
sudo docker restart "$C" >/dev/null

# Gate availability and existing authentication; no invoice numbers transmitted.
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
case "$ANON" in 401|403) ;; *)
  echo "STOP: ANONYMOUS_LOOKUP_ACCESS_HTTP=$ANON"; false ;;
esac
sudo docker exec -i -w /app "$C" python -B - <<'PY'
from pathlib import Path
from aws_verified_invoice_lookup import DATASET
p=Path("/app/pr129_aws_invoice_lookup.enabled")
assert p.is_file() and p.read_text()=="AWS_FIRESTORE_READONLY_PR129\n"
assert DATASET.endswith("-report-v1")
print("AWS_FIRESTORE_LOOKUP_MARKER=ENABLED")
print("VERIFIED_LOOKUP_SCHEMA_MODULE=PASS")
PY

CHANGING=0
trap - ERR
echo 'PR129_AWS_LOOKUP_SYNTHETIC_QA=PASS'
echo 'AWS_FIRESTORE_LOOKUP_PREVIEW=ENABLED'
echo "PREVIEW_LOGIN_HTTP=$HTTP"
echo "ANONYMOUS_SELECTED_ROUTE_HTTP=$ANON"
echo "ROLLBACK_BACKUP=$BACKUP"
echo 'LIVE_INVOICE_LOOKUP=NOT_RUN_BY_INSTALLER'
echo 'PUBLIC_CADDY=UNCHANGED'
echo 'GOOGLE_CLOUD_DEPLOYMENT=NONE'
echo 'FIRESTORE_DOCUMENT_WRITES=NONE'
echo 'FINANCIAL_WRITES=NONE'
