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
if [ -n "$(sudo docker inspect "$PREVIEW" --format '{{range .Mounts}}{{println .Destination}}{{end}}')" ]; then
  echo 'STOP_PR129_PREVIEW_MOUNTS_REQUIRE_REPLICATION'; exit 1
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
  --env-file "$WORK/preview.env" "$IMAGE" >/dev/null
echo 'ISOLATED_MAIN_PROMOTION_CANDIDATE=STARTED'

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
resp=requests.get("http://127.0.0.1:8080/login",timeout=15,allow_redirects=False)
assert resp.status_code==200,resp.status_code
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
python3 - "$WORK/proposed.Caddyfile" "$CANDIDATE" "$HOST" <<'PY'
from pathlib import Path
import sys,re
p=Path(sys.argv[1]); target=sys.argv[2]; host=sys.argv[3]
original=p.read_text()
lines=original.splitlines(keepends=True)
headers=[i for i,line in enumerate(lines) if re.match(
    r'^[ \t]*'+re.escape(host)+r'[ \t]*\{[ \t]*(?:#.*)?$',line.strip('\n'))]
if len(headers)!=1:
    raise SystemExit('STOP_MAIN_VHOST_HEADER_NOT_UNIQUE')
start=headers[0]
depth=0
end=None
for i in range(start,len(lines)):
    stripped=lines[i].split('#',1)[0]
    depth+=stripped.count('{')-stripped.count('}')
    if depth==0:
        end=i+1
        break
if end is None or end<=start+1:
    raise SystemExit('STOP_MAIN_VHOST_BOUNDARY_UNREADABLE')
site=''.join(lines[start:end])
# Require the exact known mixed legacy/default/login architecture:
if not re.search(r'handle[ \t]+@legacy[ \t]*\{',site):
    raise SystemExit('STOP_NO_LEGACY_ROUTE_TO_PRESERVE')
if not re.search(r'handle[ \t]+@login[ \t]*\{',site):
    raise SystemExit('STOP_NO_LOGIN_ROUTE_TO_FIX')
if re.search(r'handle_path\s+/api/bulk-report',site):
    raise SystemExit('STOP_REPORT_PATH_STRIPPING_UNSUPPORTED')
login_pattern=(r'(?m)(^[ \t]*handle[ \t]+@login[ \t]*\{[ \t]*\n'
               r'[ \t]*reverse_proxy[ \t]+)sbi-source-reports-v1:8080')
site,login_count=re.subn(login_pattern,lambda m:m.group(1)+target+":8080",site)
default_pattern=(r'(?m)(^[ \t]*handle[ \t]*\{[ \t]*\n'
                 r'[ \t]*reverse_proxy[ \t]+)sbi-preview:8080')
site,default_count=re.subn(default_pattern,lambda m:m.group(1)+target+":8080",site)
if login_count!=1 or default_count!=1:
    raise SystemExit('STOP_MAIN_LOGIN_OR_DEFAULT_ROUTE_UNEXPECTED')
# Named @legacy's old application remains byte-identical.
if not re.search(r'handle[ \t]+@legacy[ \t]*\{[ \t]*\n[ \t]*reverse_proxy[ \t]+sbi-preview:8080',site):
    raise SystemExit('STOP_LEGACY_APPLICATION_ROUTE_CHANGED')
# Explicitly prioritize reporting API above any broad @legacy matcher.
rt=re.search(r'(?m)^([ \t]*)route[ \t]*\{[ \t]*$',site)
if rt is None or len(re.findall(r'(?m)^[ \t]*route[ \t]*\{[ \t]*$',site))!=1:
    raise SystemExit('STOP_ROUTE_CONTAINER_MISMATCH')
indent=rt.group(1)+'    '
insert=('\n'+indent+'handle /api/bulk-report/* {\n'
        +indent+'    reverse_proxy '+target+':8080\n'
        +indent+'}\n')
site=site[:rt.end()]+insert+site[rt.end():]
updated=''.join(lines[:start])+site+''.join(lines[end:])
if original.count('sbi-bulk-report-pr129-https-preview:8080') != updated.count('sbi-bulk-report-pr129-https-preview:8080'):
    raise SystemExit('STOP_PR129_PREVIEW_ROUTE_MODIFIED')
p.write_text(updated)
print("MAIN_LOGIN_PROXY=REPAIRED")
print("MAIN_DEFAULT_DASHBOARD_PROXY=PROMOTED")
print("MAIN_EXPLICIT_REPORT_API_PROXY=ADDED")
print("MAIN_LEGACY_API_UPSTREAM=PRESERVED")
print("ALL_OTHER_VHOSTS=UNCHANGED")
PY
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
