#!/usr/bin/env bash
# SBI report-only main-live promotion: the proven PR129 dashboard is the source.
# This REPLACES the incorrect main-image-based release procedure.
# Source: already working PR129 preview, snapshotted to a local Docker image.
# Scope: main Caddy site login, default, and explicit /api/bulk-report routes.
# Preserve old main /api legacy upstream, other vhosts, and PR129 preview.
# No database migration, IAM mutation or financial database writes.
set -Eeuo pipefail
umask 077
BASE=/home/ubuntu/sbi-bulk-report-integration
REPO="$BASE/repo"
BRANCH=release/sbi-bulk-report-readonly-20261121
MAIN=aws_lightsail-sbi-preview-1
PREVIEW=sbi-bulk-report-pr129-https-preview
CADDY=aws_lightsail-caddy-1
NETWORK=sbi_pr129_preview_net
HOST=sbi-preview.13-232-241-221.sslip.io
cd "$REPO"
echo '=== SBI MAIN LIVE — VERIFIED REPORTING APP PROMOTION ==='
test "$(git branch --show-current)" = "$BRANCH" || {
  echo 'STOP_WRONG_RELEASE_BRANCH'; exit 1;
}
test -z "$(git status --porcelain --untracked-files=no)" || {
  echo 'STOP_TRACKED_SOURCE_CHANGES'; exit 1;
}
for c in "$MAIN" "$PREVIEW" "$CADDY"; do
  test "$(sudo docker inspect "$c" --format '{{.State.Running}}')" = true || {
    echo "STOP_CONTAINER_NOT_RUNNING=$c"; exit 1;
  }
done
for c in "$PREVIEW" "$CADDY"; do
  sudo docker inspect "$c" --format '{{range $name,$net := .NetworkSettings.Networks}}{{println $name}}{{end}}' |
    grep -Fxq "$NETWORK" || { echo "STOP_NETWORK_ACCESS_MISSING=$c"; exit 1; }
done

# Never make an unverified live route switch.
sudo docker exec -i -w /app "$PREVIEW" python -B - <<'PY'
from pathlib import Path
from app import app
from dashboard_sessions import ORIGINS
import bulk_report_excel as ex
expected="https://sbi-preview.13-232-241-221.sslip.io"
assert expected in ORIGINS, "main host not authorized for session/CSRF"
routes={str(rule):set(rule.methods) for rule in app.url_map.iter_rules()}
for route,method in (
    ("/login","GET"),
    ("/auth/csrf","GET"),
    ("/api/bulk-report/status","GET"),
    ("/api/bulk-report/generate-excel","POST"),
    ("/api/bulk-report/select-invoices-excel","POST"),
):
    assert method in routes.get(route,set()),"missing candidate route"
p=Path("/app/index.html")
assert p.is_file(), "candidate dashboard index unavailable"
html=p.read_text(encoding="utf-8")
for token in ('id="bulk-selected-form"','id="bulk-report-form"',
              'id="dil-imports"','id="dil-reports"'):
    assert token in html, "candidate dashboard section missing"
flag=Path("/app/pr129_aws_invoice_lookup.enabled")
assert flag.is_file() and flag.read_text()=="AWS_FIRESTORE_READONLY_PR129\n"
assert ex._excel_money("2.4299999999999997")==2.43
assert ex._excel_date("2023-10-17T00:00:00").strftime("%d/%m/%Y")=="17/10/2023"
print("PR129_COMPLETE_DASHBOARD_ROUTES=PASS")
print("PR129_MAIN_HOST_CSRF_ORIGIN=PASS")
print("PR129_MONEY_DATE_EXPORTER=PASS")
print("PR129_FIRESTORE_READ_ONLY_MARKER=PASS")
PY

REV="$(git rev-parse --short=12 HEAD)"
CANDIDATE="sbi-reports-main-$REV"
IMAGE="sbi-reporting-main:$REV"
if sudo docker inspect "$CANDIDATE" >/dev/null 2>&1; then
  echo 'STOP_CANDIDATE_NAME_ALREADY_EXISTS'; exit 1
fi
if sudo docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo 'STOP_RELEASE_IMAGE_TAG_ALREADY_EXISTS'; exit 1
fi
# Volumes/binds are not included by Docker commit. Mirror only approved
# destinations read-only so the source credentials are available without writes.
mount_count="$(sudo docker inspect "$PREVIEW" --format '{{len .Mounts}}')"
mount_args=()
if [ "$mount_count" -gt 0 ]; then
  while IFS='|' read -r kind dest mode; do
    [ -n "$dest" ] || continue
    case "$kind" in
      bind|volume) ;;
      *) echo "STOP_UNSUPPORTED_PREVIEW_MOUNT_TYPE=$kind"; exit 1 ;;
    esac
    case "$dest" in
      /app|/app/*|/tmp|/tmp/*|/var/run|/var/run/*|/run/docker.sock|/proc|/proc/*|/sys|/sys/*|/dev|/dev/*|/var/lib/postgresql|/var/lib/postgresql/*)
        echo "STOP_UNSAFE_MOUNT_DESTINATION=$dest"; exit 1 ;;
    esac
  done < <(sudo docker inspect "$PREVIEW" --format '{{range .Mounts}}{{printf "%s|%s|%t\n" .Type .Destination .RW}}{{end}}')
  mount_args=(--volumes-from "$PREVIEW:ro")
  echo "PR129_PREVIEW_MOUNTS_REPLICATED_READONLY=$mount_count"
else
  echo 'PR129_PREVIEW_MOUNTS=NONE'
fi

WORKROOT="$BASE/releases"
mkdir -p "$WORKROOT"
WORK="$(mktemp -d "$WORKROOT/pr129-main-promotion.XXXXXXXX")"
BACKUP="$WORKROOT/pr129-main-backup-$REV"
test ! -e "$BACKUP" || { echo 'STOP_BACKUP_ALREADY_EXISTS'; exit 1; }
mkdir -m 0700 "$BACKUP"
CUTOVER=0
DONE=0
CADDY_SOURCE=""
cleanup() {
  code=$?
  if [ "$DONE" != 1 ]; then
    if [ "$CUTOVER" = 1 ]; then
      echo 'CADDY_ROLLBACK=STARTED'
      sudo cp "$BACKUP/Caddyfile" "$CADDY_SOURCE" || true
      sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null || true
      echo 'CADDY_ROLLBACK=ATTEMPTED'
    fi
    sudo docker rm -f "$CANDIDATE" >/dev/null 2>&1 || true
    echo "PROMOTION_STOPPED_EXIT=$code"
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

CADDY_SOURCE="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')"
if [ -z "$CADDY_SOURCE" ]; then
  CADDY_DIR="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}')"
  [ -n "$CADDY_DIR" ] && CADDY_SOURCE="$CADDY_DIR/Caddyfile"
fi
test -f "$CADDY_SOURCE" || { echo 'STOP_CADDY_BIND_CONFIG_MISSING'; exit 1; }
sudo cp "$CADDY_SOURCE" "$BACKUP/Caddyfile"
sudo chmod 0600 "$BACKUP/Caddyfile"

# Snapshot the WHOLE tested preview including the hotfixed exporter, login,
# dashboard, and source modules; do not derive from /app/app.py legacy stub.
# Image is local to this private host; do not push/share it.
echo '=== SNAPSHOTTING VERIFIED REPORTS APP ==='
sudo docker commit --pause=true "$PREVIEW" "$IMAGE" >/dev/null
sudo docker inspect "$PREVIEW" --format '{{range .Config.Env}}{{println .}}{{end}}' > "$WORK/preview.env"
chmod 0600 "$WORK/preview.env"
sudo docker run -d --restart unless-stopped \
  --name "$CANDIDATE" --network "$NETWORK" \
  --cap-drop ALL --security-opt no-new-privileges \
  "${mount_args[@]}" \
  --env-file "$WORK/preview.env" "$IMAGE" >/dev/null
echo 'ISOLATED_MAIN_PROMOTION_CANDIDATE=STARTED'

candidate_mount_count="$(sudo docker inspect "$CANDIDATE" --format '{{len .Mounts}}')"
if [ "$candidate_mount_count" != "$mount_count" ]; then
  echo 'STOP_CANDIDATE_MOUNT_COUNT_MISMATCH'; exit 1
fi
if sudo docker inspect "$CANDIDATE" --format '{{range .Mounts}}{{printf "%s|%t\n" .Destination .RW}}{{end}}' | grep -q '|true$'; then
  echo 'STOP_CANDIDATE_HAS_WRITABLE_MOUNT'; exit 1
fi
preview_mount_targets="$(sudo docker inspect "$PREVIEW" --format '{{range .Mounts}}{{println .Destination}}{{end}}' | sort)"
candidate_mount_targets="$(sudo docker inspect "$CANDIDATE" --format '{{range .Mounts}}{{println .Destination}}{{end}}' | sort)"
if [ "$preview_mount_targets" != "$candidate_mount_targets" ]; then
  echo 'STOP_CANDIDATE_MOUNT_DESTINATION_MISMATCH'; exit 1
fi
echo 'CANDIDATE_MOUNT_DESTINATIONS_MATCH=PASS'
echo 'CANDIDATE_MOUNTS_READ_ONLY=PASS'

# Compare the candidate's route/format contract before public traffic cutover.
sudo docker exec -i -w /app "$CANDIDATE" python -B - <<'PY'
import requests
from app import app
from pathlib import Path
from aws_verified_invoice_lookup import _metadata, PROJECT
from google.auth.transport.requests import AuthorizedSession
import google.auth
routes={str(x):set(x.methods) for x in app.url_map.iter_rules()}
assert "POST" in routes.get("/api/bulk-report/select-invoices-excel",set())
assert "POST" in routes.get("/api/bulk-report/generate-excel",set())
assert Path("/app/pr129_aws_invoice_lookup.enabled").is_file()
cred,proj=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
assert proj in (None,PROJECT)
with AuthorizedSession(cred) as session:
    meta=_metadata(session)
assert meta.get("rows")==14374
import time
for attempt in range(12):
    try:
        resp=requests.get("http://127.0.0.1:8080/login",timeout=4,allow_redirects=False)
        if resp.status_code==200:
            break
    except requests.RequestException:
        pass
    time.sleep(2)
else:
    raise RuntimeError("Candidate login did not become ready")
resp=requests.get("http://127.0.0.1:8080/api/bulk-report/status",
                  timeout=15,allow_redirects=False)
assert resp.status_code in (401,403),resp.status_code
print("PROMOTION_CANDIDATE_FIRESTORE_METADATA=PASS")
print("PROMOTION_CANDIDATE_LOGIN_HTTP=200")
print("PROMOTION_CANDIDATE_ANON_REPORT_DENIED=PASS")
print("INVOICE_ROWS_QUERIED=NONE")
PY

# Parse and edit ONLY the main Caddy site. Fail closed if the observed
# Caddy matcher layout has changed. Keep @legacy's old sbi-preview upstream.
sudo cp "$BACKUP/Caddyfile" "$WORK/proposed.Caddyfile"
sudo chown "$(id -u):$(id -g)" "$WORK/proposed.Caddyfile"
echo '=== MAIN CADDY ROUTE SELECTION QA ==='
python3 scripts/sbi_main_caddy_route_patch.py --self-test
python3 scripts/sbi_main_caddy_route_patch.py \
  "$WORK/proposed.Caddyfile" "$CANDIDATE" "$HOST"
echo 'MAIN_CADDY_ROUTE_SELECTOR=PASS'
sudo docker cp "$WORK/proposed.Caddyfile" "$CADDY:/tmp/sbi-main-report-promotion.Caddyfile"
sudo docker exec "$CADDY" caddy validate \
  --config /tmp/sbi-main-report-promotion.Caddyfile >/dev/null
echo 'CADDY_PROMOTION_CONFIG_VALIDATION=PASS'

# Owner requested main AWS live deployment. Make a reversible Caddy-only swap.
CUTOVER=1
sudo cp "$WORK/proposed.Caddyfile" "$CADDY_SOURCE"
sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null
code=000
for i in 1 2 3 4 5 6; do
  code="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    "https://$HOST/login" 2>/dev/null || true)"
  [ "$code" = 200 ] && break
  sleep 2
done
[ "$code" = 200 ] || { echo "STOP_MAIN_LOGIN_HTTP=$code"; exit 1; }
for route in /auth/me /api/bulk-report/status /api/bulk-report/select-invoices-excel; do
  status="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    "https://$HOST$route" 2>/dev/null || true)"
  case "$status" in 401|403) echo "MAIN_ANONYMOUS_DENIED=$route HTTP=$status" ;;
  *) echo "STOP_MAIN_ANONYMOUS_ACCESS=$route HTTP=$status"; exit 1 ;;
  esac
done
sudo cp "$CADDY_SOURCE" "$BACKUP/Caddyfile.deployed"
sudo chmod 0600 "$BACKUP/Caddyfile.deployed"
DONE=1
echo 'SBI_MAIN_LIVE_REPORT_PROMOTION=PASS'
echo "LIVE_MAIN_REPORT_CONTAINER=$CANDIDATE"
echo "LIVE_MAIN_REPORT_IMAGE=$IMAGE"
echo "ROLLBACK_DIRECTORY=$BACKUP"
echo 'ORIGINAL_MAIN_CONTAINER=UNCHANGED'
echo 'PR129_PREVIEW_CONTAINER=UNCHANGED'
echo 'PR129_PREVIEW_ROUTE=UNCHANGED'
echo 'POSTGRESQL_DEPLOYMENT=NOT_PERFORMED'
echo 'FINANCIAL_ENGINE_DEPLOYMENT=NOT_PERFORMED'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
echo 'OWNER_LIVE_AUTHENTICATED_DOWNLOAD=NEXT_VERIFICATION'
