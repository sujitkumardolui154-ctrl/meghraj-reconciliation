#!/usr/bin/env bash
# PR129: preview-only modern UI replacement. Does not touch public routes.
set -Eeuo pipefail
REPO='/home/ubuntu/sbi-bulk-report-integration/repo'
PREVIEW='sbi-bulk-report-pr129-https-preview'
NETWORK='sbi_pr129_preview_net'
BACKUP='/home/ubuntu/sbi-bulk-report-integration/pr129-preview-ui-backup'
cd "$REPO"

echo '=== APPLY MODERN WORKSPACE TO TEMPORARY PREVIEW ==='
[ "$(git branch --show-current)" = 'ui/bulk-report-reports-tab-20261121' ] || { echo 'STOP: Wrong Git branch'; exit 1; }
[ -z "$(git diff --name-only)" ] || { echo 'STOP: Uncommitted tracked changes'; exit 1; }
sudo docker container inspect "$PREVIEW" >/dev/null
[ "$(sudo docker inspect "$PREVIEW" --format '{{.State.Running}}')" = true ] || { echo 'STOP: Preview not running'; exit 1; }
[ "$(sudo docker inspect "$PREVIEW" --format '{{.HostConfig.NetworkMode}}')" = "$NETWORK" ] || { echo 'STOP: Not the isolated preview network'; exit 1; }
test ! -e "$BACKUP" || { echo "STOP: Previous backup exists at $BACKUP"; exit 1; }

# Read-only preflight before modifying any container.
python3 - <<'PY'
from pathlib import Path
p=Path("dashboard_source/index.html")
s=p.read_text(encoding="utf-8")
required=[
'SBI Reconciliation <span>Workspace</span>',
'id="dil-tower-panel"', 'id="dil-reports"',
'id="dil-imports"', 'id="dil-db-payments"',
'id="dil-import-form"', 'id="dil-report-refresh"',
'id="bulk-report"', 'id="bulk-report-form"',
'fetch("/api/bulk-report/generate"',
'"X-DIL-CSRF": csrfData.csrf_token'
]
missing=[x for x in required if x not in s]
if missing or "Excel Upload — Dashboard v1.3.0" in s:
    raise SystemExit("STOP: Modern UI invariants failed: "+str(missing))
if s.count('id="bulk-report"')!=1:
    raise SystemExit("STOP: Duplicate Bulk Report widget")
if not Path("dashboard_source/dashboard.js").is_file():
    raise SystemExit("STOP: Missing dashboard.js")
print("MODERN_UI_PREFLIGHT=PASS")
PY
sudo docker exec "$PREVIEW" test -f /app/index.html
sudo docker exec "$PREVIEW" test -f /app/dashboard.js
sudo docker exec "$PREVIEW" python - <<'PY'
PY
# Preserve the active preview files for rollback; do not touch public containers.
mkdir -m 700 "$BACKUP"
sudo docker cp "$PREVIEW:/app/index.html" "$BACKUP/index.html"
sudo docker cp "$PREVIEW:/app/dashboard.js" "$BACKUP/dashboard.js"
sudo chown "$(id -u):$(id -g)" "$BACKUP/index.html" "$BACKUP/dashboard.js"
chmod 600 "$BACKUP/index.html" "$BACKUP/dashboard.js"

rollback() {
  echo 'PREVIEW_UPDATE=FAILED; RESTORING PREVIOUS PREVIEW HTML/JS'
  sudo docker cp "$BACKUP/index.html" "$PREVIEW:/app/index.html" || true
  sudo docker cp "$BACKUP/dashboard.js" "$PREVIEW:/app/dashboard.js" || true
  echo 'PREVIEW_ROLLBACK=ATTEMPTED'
}
trap rollback ERR

sudo docker cp dashboard_source/index.html "$PREVIEW:/app/index.html"
sudo docker cp dashboard_source/dashboard.js "$PREVIEW:/app/dashboard.js"

for file in index.html dashboard.js; do
  LOCAL=$(sha256sum "dashboard_source/$file" | awk '{print $1}')
  REMOTE=$(sudo docker exec "$PREVIEW" sha256sum "/app/$file" | awk '{print $1}')
  [ "$LOCAL" = "$REMOTE" ] || { echo "SHA256_MISMATCH=$file"; false; }
done

# Ensure existing Flask routes still exist; no requests with financial payloads.
sudo docker exec "$PREVIEW" python -c '
from app import app
paths={str(r) for r in app.url_map.iter_rules()}
required={"/login","/dashboard.js","/api/bulk-report/status","/api/bulk-report/generate"}
missing=required-paths
if missing: raise SystemExit("Missing routes: "+str(sorted(missing)))
print("PREVIEW_ROUTE_CHECK=PASS")
'

trap - ERR
echo 'MODERN_WORKSPACE_PREVIEW=APPLIED'
echo 'EXISTING_PUBLIC_UI=UNCHANGED'
echo "ROLLBACK_BACKUP=$BACKUP"
echo 'FINANCIAL_WRITES=NONE'
