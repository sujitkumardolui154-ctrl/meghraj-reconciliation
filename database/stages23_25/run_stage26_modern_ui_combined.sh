#!/usr/bin/env bash
# Stage26: modern SBI UI in NEW private Firebase+PG candidate, gated compatibility.
# No prod modifications, Caddy routing change, financial write, or public port.
set -Eeuo pipefail
umask 077
STEP=START
LIVE=sbi-bulk-report-pr129-https-preview
BASE_STAGE=sbi-pr129-pg-stage25-firebase-adc
BASE_IMAGE=sbi-pr129-pg-auth-source-parity:isolated
CANDIDATE_IMAGE=sbi-pr129-pg-modernui-stage26:isolated
CANDIDATE=sbi-pr129-pg-modernui-stage26
NET=sbi_pr129_pg_staging_only
DB=sbi_reconciliation_main
PGPASS=/home/ubuntu/sbi-pr129-pg-private-stage/pgpass
WEBENV=/home/ubuntu/sbi-pr129-pg-private-stage/staging_web_auth.env
GOOGLE_CRED=/home/ubuntu/sbi-private-credentials/firebase-stage.json
SOURCE_BRANCH=ui/bulk-report-reports-tab-20261121
URLBASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
HTML_BLOB=80ca71cd50f05994b09cac5c994fc58894d4a793
JS_BLOB=9b33f053dfd1965692101b1fe15d36a0e1d427c8
DIR=""
CREATED=NO
finish() {
 rc=$?
 trap - EXIT
 if [[ -n "$DIR" && "$DIR" == /tmp/sbi_modernui26_* ]]; then
   rm -rf -- "$DIR" || rc=98
 fi
 if (( rc ));then
   echo "STAGE26_MODERN_UI_COMBINED_QA=FAIL step=$STEP exit=$rc"
   if [[ "$CREATED" == YES ]];then
     sudo -n docker rm -f "$CANDIDATE" >/dev/null 2>&1 || true
     echo "FAILED_STAGE26_CONTAINER_REMOVED=YES"
   fi
 else
   echo "STAGE26_MODERN_UI_COMBINED_QA=PASS"
 fi
 echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
 exit "$rc"
}
trap finish EXIT
sql() {
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"
}
counts() {
 sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}

echo "=== A. PRESERVE LIVE AND FIREBASE-STAGE25 BASELINES ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
sudo -n docker image inspect "$BASE_IMAGE" >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$BASE_STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$BASE_STAGE" --format '{{.State.Running}}')" == true ]]
[[ -z "$(sudo -n docker port "$BASE_STAGE")" ]]
[[ "$(sudo -n docker inspect "$BASE_STAGE" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
if sudo -n docker inspect "$CANDIDATE" >/dev/null 2>&1;then
 echo "STAGE26_EXISTING_CONTAINER=REVIEW_REQUIRED";exit 11
fi
[[ -f "$PGPASS" && -f "$WEBENV" && -f "$GOOGLE_CRED" ]] || { echo "EXISTING_STAGING_CREDENTIALS=MISSING";exit 12; }
for file in "$PGPASS" "$WEBENV" "$GOOGLE_CRED";do
 [[ -f "$file" && ! -L "$file" && "$(stat -c '%a' "$file")" == 600 ]] ||
   { echo "CREDENTIAL_PERMISSION_PRECHECK=FAIL";exit 13; }
done
FIN_BEFORE="$(counts)"
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "STAGE26_FINANCIAL_WRITE_PRIVILEGES=DENIED"
echo "STAGE25_GOOGLE_CREDENTIAL_FILE=EXISTING_RESTRICTED"

echo "=== B. PINNED MODERN UI BRANCH SOURCE ==="
STEP=SOURCE
DIR="$(mktemp -d /tmp/sbi_modernui26_XXXXXXXX)"
chmod 700 "$DIR"
for file in index.html dashboard.js;do
 curl -4 -fLsS --retry 3 \
   -o "$DIR/$file" "$URLBASE/$SOURCE_BRANCH/dashboard_source/$file"
done
[[ "$(git hash-object "$DIR/index.html")" == "$HTML_BLOB" ]] || {
 echo "MODERN_INDEX_BLOB_VERIFICATION=FAIL";exit 21; }
[[ "$(git hash-object "$DIR/dashboard.js")" == "$JS_BLOB" ]] || {
 echo "MODERN_DASHBOARD_JS_BLOB_VERIFICATION=FAIL";exit 22; }
echo "MODERN_UI_GITHUB_SOURCE_INTEGRITY=PASS"
echo "MODERN_UI_BRANCH=$SOURCE_BRANCH"

echo "=== C. VERIFY MODERN UI FEATURES AND REQUIRED STAGE25 BACKEND ROUTES ==="
STEP=COMPATIBILITY
python3 -B - "$DIR/index.html" "$DIR/dashboard.js" <<'PY'
from pathlib import Path
import sys
html=Path(sys.argv[1]).read_text()
js=Path(sys.argv[2]).read_text()
required=[
 'SBI Reconciliation <span>Workspace</span>',
 'id="dil-tower-panel"',
 'id="dil-reports"',
 'id="dil-imports"',
 'id="dil-db-payments"',
 'id="dil-import-form"',
 'id="bulk-report-form"',
 'id="bulk-selected-form"',
 '/api/bulk-report/generate-excel',
 '/api/bulk-report/select-invoices-excel',
]
missing=[value for value in required if value not in html]
if missing:raise SystemExit("MODERN_UI_FEATURES_MISSING="+",".join(missing))
if "Excel Upload — Dashboard v1.3.0" in html:
 raise SystemExit("MODERN_UI_LEGACY_LABEL=BLOCKED")
for value in ('id="bulk-report-form"','id="bulk-selected-form"'):
 assert html.count(value)==1, "DUPLICATE_FORM_ID"
assert 'const endpoints' in js
print("MODERN_UI_FEATURE_CONTRACT=PASS")
print("MODERN_UI_REPORTS_AND_DATABASE_TABS=PASS")
print("MODERN_UI_JS_SOURCE=PASS")
PY
sudo -n docker exec -i "$BASE_STAGE" python3 -B - <<'PY'
from app import app
routes={r.rule: set(r.methods) for r in app.url_map.iter_rules()}
required={
 "/": "GET",
 "/login": "GET",
 "/auth/session": "POST",
 "/auth/csrf": "GET",
 "/api/reporting/v2": "GET",
 "/api/reporting/v2/postgresql-summary": "GET",
 "/api/bulk-report/generate-excel": "POST",
 "/api/bulk-report/select-invoices-excel": "POST",
 "/api/bulk-report/status": "GET",
 "/dashboard.js": "GET",
 "/account.js": "GET",
 "/dil_floating_assistant.js": "GET",
 "/dashboard-theme.css": "GET",
}
missing=[]
for path,method in required.items():
 present=method in routes.get(path,set())
 print("STAGE25_BACKEND_ROUTE="+path+" METHOD="+method+" PRESENT="+str(present))
 if not present:missing.append(path)
if missing:raise SystemExit("MODERN_UI_BACKEND_COMPATIBILITY=BLOCKED missing_count="+str(len(missing)))
print("MODERN_UI_BACKEND_COMPATIBILITY=PASS")
PY

echo "=== D. BUILD NEW ISOLATED HTML+JS IMAGE (DO NOT MODIFY OLD STAGE) ==="
STEP=BUILD
cat > "$DIR/Dockerfile" <<'DOCKER'
FROM sbi-pr129-pg-auth-source-parity:isolated
USER root
WORKDIR /app
COPY index.html dashboard.js /app/
RUN chmod 0644 /app/index.html /app/dashboard.js \
 && echo "STAGE26_MODERN_UI_FILES=BUILT"
DOCKER
sudo -n docker build --pull=false -t "$CANDIDATE_IMAGE" -f "$DIR/Dockerfile" "$DIR" >/dev/null
echo "STAGE26_NEW_UI_IMAGE=BUILT"

echo "=== E. ISOLATED FLASK AUTH/UI/REPORT REGRESSION QA ==="
STEP=ISOLATED_QA
sudo -n docker run --rm -i --network none --read-only \
 --tmpfs /tmp:rw,nosuid,nodev,size=32m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" --entrypoint python3 \
 -e PYTHONDONTWRITEBYTECODE=1 "$CANDIDATE_IMAGE" -B - <<'PY'
from app import app
from pathlib import Path
import hashlib
html=Path("/app/index.html").read_text()
assert 'SBI Reconciliation <span>Workspace</span>' in html
assert 'id="bulk-selected-form"' in html
assert 'id="dil-db-payments"' in html
r=app.test_client()
assert r.get("/login").status_code==200
assert r.get("/api/reporting/v2/postgresql-summary").status_code in (401,403)
assert r.get("/api/bulk-report/status").status_code in (401,403)
assert r.get("/api/reporting/v2").status_code in (401,403)
print("STAGE26_MODERN_INDEX_SHA256="+hashlib.sha256(html.encode()).hexdigest())
print("STAGE26_ANONYMOUS_REPORTING_DENIAL=PASS")
print("STAGE26_LOGIN_PAGE=PASS")
print("STAGE26_BULK_REPORT_CONTRACT=PASS")
PY

echo "=== F. START ADDITIONAL PRIVATE STAGE26 WITH EXISTING SECURE ADC ==="
STEP=START_STAGE
sudo -n docker run -d --name "$CANDIDATE" \
 --network "$NET" --restart no --read-only \
 --tmpfs /tmp:rw,nosuid,nodev,size=64m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" \
 --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
 --mount "type=bind,source=$PGPASS,target=/run/secrets/sbi_pgpass,readonly" \
 --mount "type=bind,source=$GOOGLE_CRED,target=/run/secrets/firebase-stage.json,readonly" \
 --env-file "$WEBENV" \
 -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-stage.json \
 -e PGHOST=/var/run/postgresql -e PGPORT=5432 \
 -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
 -e PGPASSFILE=/run/secrets/sbi_pgpass -e PYTHONDONTWRITEBYTECODE=1 \
 "$CANDIDATE_IMAGE" >/dev/null
CREATED=YES
ready=NO
for try in 1 2 3 4 5 6 7 8 9 10;do
 [[ "$(sudo -n docker inspect "$CANDIDATE" --format '{{.State.Running}}')" == true ]] || {
 echo "NEW_PRIVATE_CANDIDATE_STOPPED=YES";exit 40; }
 if sudo -n docker exec -i "$CANDIDATE" python3 -B - <<'PY'
import urllib.request,urllib.error,google.auth
assert google.auth.default()[1]=="meghraj-reconciliation"
def status(path):
 try:
  with urllib.request.urlopen("http://127.0.0.1:8080"+path,timeout=5) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
assert status("/login")==200
assert status("/api/reporting/v2/postgresql-summary") in (401,403)
assert status("/api/bulk-report/status") in (401,403)
assert status("/dashboard-theme.css")==200
assert status("/account.js")==200
assert status("/dashboard.js")==200
print("STAGE26_PRIVATE_FIREBASE_ADC=PASS")
print("STAGE26_PRIVATE_UI_STATIC_ASSETS=PASS")
print("STAGE26_PRIVATE_ANONYMOUS_AUTH=DENIED")
PY
 then ready=YES;break;fi
 sleep 2
done
[[ "$ready" == YES ]] || { echo "STAGE26_PRIVATE_HTTP_QA=REVIEW_REQUIRED";exit 41; }

echo "=== G. CENTRAL POSTGRESQL REPORT VIEWS/PRIVILEGE CHECK ==="
STEP=POSTGRES
sudo -n docker exec -i "$CANDIDATE" python3 -B - <<'PY'
import psycopg
with psycopg.connect(connect_timeout=8) as conn:
 conn.execute("SET TRANSACTION READ ONLY")
 identity=conn.execute(
  "SELECT current_user,current_database(),current_setting('transaction_read_only')"
 ).fetchone()
 assert identity==("sbi_pr129_report_login","sbi_reconciliation_main","on")
 assert conn.execute("SELECT count(*) FROM sbi.invoice_financial_summary").fetchone()[0]>=0
 assert conn.execute("SELECT count(*) FROM sbi.payment_financial_summary").fetchone()[0]>=0
 privs=conn.execute(
  "SELECT has_table_privilege(current_user,'sbi.invoices','INSERT'),"
  "has_table_privilege(current_user,'sbi.payments','INSERT'),"
  "has_table_privilege(current_user,'sbi.allocations','INSERT')"
 ).fetchone()
 assert privs==(False,False,False)
print("STAGE26_POSTGRES_REPORT_VIEWS=PASS")
print("STAGE26_POSTGRES_FINANCIAL_INSERT=DENIED")
PY

echo "=== H. LIVE/OLD STAGE PROTECTION AND NEW PRIVATE IP ==="
STEP=SAFETY
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$BASE_STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
[[ -z "$(sudo -n docker port "$CANDIDATE")" ]]
[[ "$(sudo -n docker inspect "$CANDIDATE" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
IP="$(sudo -n docker inspect "$CANDIDATE" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
echo "STAGE26_NEW_PRIVATE_IP=$IP"
echo "STAGE26_PUBLIC_PORTS=NONE"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "STAGE25_FIREBASE_CONTAINER_UNCHANGED=PASS"
echo "FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE26 MODERN UI INTEGRATION ==="
echo "STAGE26_MODERN_UI_INTEGRATION=PASS"
echo "STAGE26_FIREBASE_ADC=PASS"
echo "STAGE26_POSTGRESQL_READ_ONLY=PASS"
echo "STAGE26_PRIVATE_CANDIDATE=RUNNING"
echo "REAL_USER_STAGE26_LOGIN=NOT_YET_TESTED"
echo "AUTHORIZED_POSTGRES_REPORT_HTTP=NOT_YET_TESTED"
echo "OWNER_UI_ACCEPTANCE=NOT_YET_VERIFIED"
echo "FINAL_PR129_CUTOVER=BLOCKED_PENDING_AUTHENTICATED_UI_REPORT_QA_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=OWNER_PREVIEW_STAGE26_VIA_SSH_TUNNEL_AND_AUTHORIZED_REPORT_QA"
