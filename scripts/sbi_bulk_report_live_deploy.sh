#!/usr/bin/env bash
# Owner-authorized read-only SBI Bulk Report production cutover.
# Blue/green: existing dashboard stays running; Caddy rollback on failure.
# No PostgreSQL, reconciliation engine or financial database writes.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
BASE=/home/ubuntu/sbi-bulk-report-integration
MAIN=aws_lightsail-sbi-preview-1
CADDY=aws_lightsail-caddy-1
PREVIEW=sbi-bulk-report-pr129-https-preview
NETWORK=aws_lightsail_private_web
HOST=sbi-preview.13-232-241-221.sslip.io
BRANCH=release/sbi-bulk-report-readonly-20261121
cd "$REPO"
echo '=== SBI LIVE BULK REPORT — GUARDED BLUE/GREEN DEPLOYMENT ==='
test "$(git branch --show-current)" = "$BRANCH" || { echo 'STOP_WRONG_BRANCH'; exit 1; }
test -z "$(git status --porcelain --untracked-files=no)" || { echo 'STOP_DIRTY_REPOSITORY'; exit 1; }
for c in "$MAIN" "$CADDY" "$PREVIEW"; do
  test "$(sudo docker inspect "$c" --format '{{.State.Running}}')" = true || {
    echo "STOP_REQUIRED_SERVICE_NOT_RUNNING=$c"; exit 1;
  }
done
test "$(sudo docker inspect "$MAIN" --format '{{.HostConfig.NetworkMode}}')" = "$NETWORK" || {
  echo 'STOP_MAIN_NETWORK_MISMATCH'; exit 1;
}
sudo docker inspect "$CADDY" --format '{{range $n,$_ := .NetworkSettings.Networks}}{{println $n}}{{end}}' | grep -Fxq "$NETWORK" || {
  echo 'STOP_CADDY_NOT_ON_MAIN_NETWORK'; exit 1;
}
mounts="$(sudo docker inspect "$MAIN" --format '{{range .Mounts}}{{println .Destination}}{{end}}')"
if [ -n "$mounts" ]; then
  echo 'STOP_MAIN_HAS_PERSISTENT_MOUNTS_REQUIRING_EXACT_REPLICA'
  exit 1
fi

# Do not silently lose a live main-app hotpatch by deriving from an older image.
if sudo docker diff "$MAIN" | grep -Eq '^[ACD] /app/.*\.(py|html|js|json)$'; then
  echo 'STOP_MAIN_APP_RUNTIME_DRIFT_REQUIRE_IMAGE_SNAPSHOT_REVIEW'
  exit 1
fi
echo 'MAIN_RUNTIME_CODE_IMAGE_PARITY=PASS'

revision="$(git rev-parse --short=12 HEAD)"
base_image="$(sudo docker inspect "$MAIN" --format '{{.Image}}')"
candidate="sbi-bulk-report-live-$revision"
image="sbi-bulk-report-live:$revision"
if sudo docker inspect "$candidate" >/dev/null 2>&1; then
  echo 'STOP_CANDIDATE_ALREADY_PRESENT'; exit 1
fi

FILES="bulk_reports.py bulk_report_excel.py bulk_report_selection.py invoice_number_selection.py aws_verified_invoice_lookup.py invoice_source_schema.py invoice_import_contract.json sbi_reporting_bundle.py test_aws_verified_invoice_lookup.py test_bulk_report_combined_excel.py test_bulk_report_selection.py test_invoice_number_selection.py"
for f in $FILES; do
  test -s "dashboard_source/$f" || { echo "STOP_MISSING_RELEASE_FILE=$f"; exit 1; }
done

ROOT="$BASE/releases"
mkdir -p "$ROOT"
chmod 0700 "$ROOT"
TMP="$(mktemp -d "$ROOT/report-build.XXXXXXXX")"
BACKUP="$ROOT/rollback-before-$revision"
test ! -e "$BACKUP" || { echo 'STOP_ROLLBACK_ALREADY_EXISTS'; exit 1; }
mkdir -m 0700 "$BACKUP"
activated=0
success=0
caddy_source=""
finish() {
  result=$?
  if [ "$success" != 1 ]; then
    if [ "$activated" = 1 ]; then
      echo 'ROLLBACK_PUBLIC_GATEWAY=STARTED'
      sudo cp "$BACKUP/Caddyfile" "$caddy_source" || true
      sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null || true
      echo 'ROLLBACK_PUBLIC_GATEWAY=ATTEMPTED'
    fi
    sudo docker stop "$candidate" >/dev/null 2>&1 || true
    sudo docker rm "$candidate" >/dev/null 2>&1 || true
    echo "RELEASE_FAILED_EXIT_CODE=$result"
  fi
  rm -rf "$TMP"
}
trap finish EXIT

caddy_source="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')"
if [ -z "$caddy_source" ]; then
  caddy_dir="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}')"
  [ -n "$caddy_dir" ] && caddy_source="$caddy_dir/Caddyfile"
fi
test -f "$caddy_source" || { echo 'STOP_PUBLIC_GATEWAY_CONFIG_BIND_MISSING'; exit 1; }
sudo cp "$caddy_source" "$BACKUP/Caddyfile"
sudo chmod 0600 "$BACKUP/Caddyfile"
sudo docker inspect "$MAIN" > "$BACKUP/old-main-inspect.json"
sudo chmod 0600 "$BACKUP/old-main-inspect.json"
echo "BASE_IMAGE_PRESERVED=$base_image"

# Environment is copied to a temporary secret file; NEVER print values.
sudo docker inspect "$MAIN" --format '{{range .Config.Env}}{{println .}}{{end}}' > "$TMP/live.env"
chmod 0600 "$TMP/live.env"
mkdir -m 0700 "$TMP/build"
for f in $FILES; do cp "dashboard_source/$f" "$TMP/build/$f"; done
sudo docker cp "$MAIN:/app/index.html" "$TMP/build/index.html"
sudo docker cp "$MAIN:/app/production_gateway.py" "$TMP/build/production_gateway.py"
sudo chown "$(id -u):$(id -g)" "$TMP/build/index.html" "$TMP/build/production_gateway.py"

# Patch ONLY the exact Reports section in the CURRENT live app. Retain every
# unrelated UI and gateway code path. Fail closed if the layout is different.
python3 - "$TMP/build/index.html" "$TMP/build/production_gateway.py" "$REPO/dashboard_source/index.html" <<'PY'
import sys
from pathlib import Path
ui,api,release_ui=map(Path,sys.argv[1:])
live=ui.read_text()
reference=release_ui.read_text()
start='<!-- Selected-Invoice Bulk Report: read-only database lookup; no financial writes. -->'
end='\n<section class="card" id="dil-reconciliation-changes"'
a=reference.find(start)
b=reference.find(end,a)
if a<0 or b<0 or b<=a: raise SystemExit('STOP_RELEASE_UI_FRAGMENT')
fragment=reference[a:b]
if 'id="bulk-selected-form"' not in fragment or 'id="bulk-report-form"' not in fragment:
    raise SystemExit('STOP_RELEASE_UI_INCOMPLETE')
if 'id="bulk-selected-form"' not in live:
    legacy='<!-- Bulk Report: source-only reporting; no financial database updates. -->'
    i=live.find(legacy)
    j=live.find(end,i)
    if i<0 or j<0 or j<=i: raise SystemExit('STOP_UNRECOGNIZED_LIVE_REPORT_UI')
    live=live[:i]+fragment+live[j:]
    print('EXISTING_UI_REPORT_SECTION_PATCH=PASS')
else:
    if 'fetch("/api/bulk-report/select-invoices-excel"' not in live:
        raise SystemExit('STOP_LIVE_SELECTED_UI_UNEXPECTED')
    print('EXISTING_SELECTED_REPORT_UI=PRESERVED')
for expected in ('id="bulk-selected-form"','id="bulk-report-form"',
                 'id="dil-imports"','fetch("/api/bulk-report/select-invoices-excel"',
                 'fetch("/api/bulk-report/generate-excel"'):
    if expected not in live: raise SystemExit('STOP_UI_MARKER_MISSING')
ui.write_text(live)

gateway=api.read_text()
if 'app.register_blueprint(bulk_report)' not in gateway:
    anchor='install_account_pages(app)\n'
    if gateway.count(anchor)!=1: raise SystemExit('STOP_LIVE_GATEWAY_ANCHOR_MISMATCH')
    gateway=gateway.replace(anchor,anchor+
       '\n# Authenticated read-only SBI Bulk Report.\n'
       'from bulk_reports import bulk_report\n'
       'app.register_blueprint(bulk_report)\n',1)
api.write_text(gateway)
print('GATEWAY_BULK_REPORT_REGISTERED=PASS')
PY

cat > "$TMP/build/Dockerfile" <<'EOF'
ARG BASE_IMAGE
FROM $BASE_IMAGE
ARG APP_USER
USER root
WORKDIR /app
RUN python -c "import openpyxl" || python -m pip install --no-cache-dir 'openpyxl>=3.1,<4'
COPY *.py /app/
COPY index.html invoice_import_contract.json /app/
RUN printf 'AWS_FIRESTORE_READONLY_PR129\n' > /app/pr129_aws_invoice_lookup.enabled
LABEL io.sbi.release.scope="bulk-report-only"
USER $APP_USER
EOF
echo '=== BUILDING RELEASE IMAGE FROM EXISTING MAIN APP ==='
app_user="$(sudo docker inspect "$MAIN" --format '{{.Config.User}}')"
[ -n "$app_user" ] || app_user=root
sudo docker build --pull=false --build-arg "BASE_IMAGE=$base_image" \
  --build-arg "APP_USER=$app_user" \
  -t "$image" "$TMP/build" >/dev/null
echo 'MAIN_BASED_IMMUTABLE_IMAGE=BUILT'

# Use the same main app base, user and environment. Any persistent
# mount was rejected above so the live app cannot silently lose shared state.
sudo docker run -d --restart unless-stopped --name "$candidate" \
  --network "$NETWORK" --cap-drop ALL --security-opt no-new-privileges \
  --env-file "$TMP/live.env" "$image" >/dev/null
echo 'REPORT_CANDIDATE=STARTED'

# Synthetic QA and backend map; NO financial records changed.
sudo docker exec -w /app "$candidate" python -B -m unittest -v \
  test_invoice_number_selection test_bulk_report_selection \
  test_bulk_report_combined_excel test_aws_verified_invoice_lookup >/dev/null
echo 'RELEASE_CANDIDATE_SYNTHETIC_QA=PASS'
sudo docker exec -i -w /app "$candidate" python -B - <<'PY'
from app import app
from pathlib import Path
from bulk_report_excel import _excel_money, _excel_date
routes={str(rule):set(rule.methods) for rule in app.url_map.iter_rules()}
assert "POST" in routes.get("/api/bulk-report/select-invoices-excel",set())
assert "POST" in routes.get("/api/bulk-report/generate-excel",set())
assert "GET" in routes.get("/api/bulk-report/status",set())
assert _excel_money("2.4299999999999997")==2.43
assert _excel_date("2023-10-17T00:00:00").strftime("%d/%m/%Y")=="17/10/2023"
assert Path("/app/pr129_aws_invoice_lookup.enabled").read_text()=="AWS_FIRESTORE_READONLY_PR129\n"
print('RELEASE_CANDIDATE_ROUTES_AND_FORMAT=PASS')
PY

# Existing AWS credentials must verify the same READ-ONLY source metadata;
# no invoice rows, payments or personal records are queried during deployment.
sudo docker exec -i -w /app "$candidate" python -B - <<'PY'
import google.auth
from google.auth.transport.requests import AuthorizedSession
from aws_verified_invoice_lookup import _metadata, PROJECT
cred,project=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
assert project in (None,PROJECT)
with AuthorizedSession(cred) as session:
    assert _metadata(session)["rows"]==14374
print('CANDIDATE_VERIFIED_SOURCE_METADATA=PASS')
print('FIRESTORE_INVOICE_ROWS_READ=NONE')
PY

# Running candidate login and anonymous report access.
sudo docker exec -i -w /app "$candidate" python -B - <<'PY'
import requests
for path,allowed in (("/login",(200,)),("/api/bulk-report/status",(401,403))):
    r=requests.get("http://127.0.0.1:8080"+path,timeout=15,allow_redirects=False)
    assert r.status_code in allowed,(path,r.status_code)
print('CANDIDATE_LOGIN_AND_AUTH_GUARD=PASS')
PY

# Caddy cutover changes only known live app/report upstream names.
# PR129 preview upstream remains untouched. Unsupported syntax => stop.
sudo cp "$BACKUP/Caddyfile" "$TMP/proposed.Caddyfile"
sudo chown "$(id -u):$(id -g)" "$TMP/proposed.Caddyfile"
python3 - "$TMP/proposed.Caddyfile" "$candidate" "$HOST" <<'PY'
import re,sys
from pathlib import Path
p=Path(sys.argv[1]); new=sys.argv[2]; host=sys.argv[3]
original=p.read_text()
lines=original.splitlines(keepends=True)
headers=[i for i,line in enumerate(lines)
  if re.fullmatch(r'\s*'+re.escape(host)+r'\s*\{\s*(?:#[^\n]*)?\n?',line)]
if len(headers)!=1:
    raise SystemExit('STOP_MAIN_CADDY_SITE_HEADER_NOT_EXACTLY_ONE')
start=headers[0]
depth=0; end=None
for i in range(start,len(lines)):
    line=lines[i].split('#',1)[0]
    depth+=line.count('{')-line.count('}')
    if depth==0:
        end=i+1
        break
if end is None or end<=start+1:
    raise SystemExit('STOP_MAIN_CADDY_SITE_BLOCK_UNPARSEABLE')
site=''.join(lines[start:end])
if re.search(r'\bhandle_path\s+/?api/bulk-report',site):
    raise SystemExit('STOP_CADDY_REPORT_PATH_STRIPPING_UNSUPPORTED')
pattern=r'\b(?:aws_lightsail-sbi-preview-1|sbi-preview|sbi-source-reports-v1):8080\b'
patched,n=re.subn(pattern,new+":8080",site)
if n<1 or n>8:
    raise SystemExit('STOP_MAIN_SITE_UPSTREAM_MATCH_COUNT_UNEXPECTED')
lines[start:end]=[patched]
updated=''.join(lines)
if 'sbi-bulk-report-pr129-https-preview:8080' in original:
    if original.count('sbi-bulk-report-pr129-https-preview:8080')!=updated.count('sbi-bulk-report-pr129-https-preview:8080'):
        raise SystemExit('STOP_PR129_PREVIEW_ROUTE_CHANGED')
p.write_text(updated)
print('CADDY_MAIN_SITE_UPSTREAMS_REPLACED='+str(n))
print('OTHER_GATEWAY_SITES=UNCHANGED')
PY
sudo docker cp "$TMP/proposed.Caddyfile" "$CADDY:/tmp/sbi-release-candidate.Caddyfile"
sudo docker exec "$CADDY" caddy validate --config /tmp/sbi-release-candidate.Caddyfile >/dev/null
echo 'CADDY_NEW_CONFIG_VALIDATED=PASS'

echo '=== ACTIVATING MAIN SBI REPORTING ==='
activated=1
sudo cp "$TMP/proposed.Caddyfile" "$caddy_source"
sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null
code=000
for attempt in 1 2 3 4 5 6; do
  code="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    "https://$HOST/login" 2>/dev/null || true)"
  [ "$code" = 200 ] && break
  sleep 2
done
test "$code" = 200 || { echo "STOP_PUBLIC_LOGIN_HTTP=$code"; exit 1; }
anon="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
  -sS --max-time 10 -o /dev/null -w '%{http_code}' \
  "https://$HOST/api/bulk-report/status" 2>/dev/null || true)"
case "$anon" in 401|403) ;; *) echo "STOP_PUBLIC_ANON_HTTP=$anon"; exit 1 ;; esac

sudo cp "$caddy_source" "$BACKUP/Caddyfile.deployed"
sudo chmod 0600 "$BACKUP/Caddyfile.deployed"
success=1
echo 'SBI_BULK_REPORT_LIVE_DEPLOYMENT=PASS'
echo "LIVE_IMAGE=$image"
echo "LIVE_CONTAINER=$candidate"
echo "LIVE_LOGIN_HTTP=$code"
echo "ANONYMOUS_REPORT_HTTP=$anon"
echo "ROLLBACK_CADDY_FILE=$BACKUP/Caddyfile"
echo "ORIGINAL_MAIN_IMAGE_PRESERVED=$base_image"
echo 'OLD_MAIN_CONTAINER=UNCHANGED'
echo 'PR129_PREVIEW=UNCHANGED'
echo 'POSTGRESQL_DEPLOYMENT=NOT_PERFORMED'
echo 'FINANCIAL_ENGINE_DEPLOYMENT=NOT_PERFORMED'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
echo 'FINAL_AUTHENTICATED_REPORT_DOWNLOAD=NEEDS_BROWSER_VERIFICATION'
