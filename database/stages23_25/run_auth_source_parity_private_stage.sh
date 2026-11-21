#!/usr/bin/env bash
# SBI Stage24: deploy repaired auth-source-parity image to an additional PRIVATE
# container, then run combined anonymous/session/reporting stability QA.
# Never copies Google credentials or changes live PR129, Caddy, finance data,
# Financial Engine, or any public network route.
set -Eeuo pipefail
umask 077
STEP=START
DB=sbi_reconciliation_main
LIVE=sbi-bulk-report-pr129-https-preview
OLD=sbi-pr129-pg-origin-stage-v2
IMAGE=sbi-pr129-pg-auth-source-parity:isolated
NEW=sbi-pr129-pg-auth-parity-stage
NETWORK=sbi_pr129_pg_staging_only
SECRET_DIR=/home/ubuntu/sbi-pr129-pg-private-stage
PGPASS="$SECRET_DIR/pgpass"
WEBENV="$SECRET_DIR/staging_web_auth.env"
CREATED=NO
cleanup(){
  local rc=$?
  trap - EXIT
  if (( rc )); then
    echo "STAGE24_AUTH_PARITY_PRIVATE_QA=FAIL step=$STEP exit=$rc"
    if [[ "$CREATED" == YES ]]; then
      sudo -n docker rm -f "$NEW" >/dev/null 2>&1 || true
    fi
  else
    echo "STAGE24_AUTH_PARITY_PRIVATE_QA=PASS"
  fi
  echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
  exit "$rc"
}
trap cleanup EXIT
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== A. SAFETY AND ISOLATED IMAGE BASELINE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
sudo -n docker image inspect "$IMAGE" >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
OLD_BEFORE="$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
[[ -z "$(sudo -n docker port "$OLD")" ]]
[[ "$(sudo -n docker inspect "$OLD" --format '{{.HostConfig.NetworkMode}}')" == "$NETWORK" ]]
if sudo -n docker inspect "$NEW" >/dev/null 2>&1; then
  echo "AUTH_PARITY_STAGE_ALREADY_EXISTS=REVIEW_REQUIRED"
  exit 12
fi
[[ -f "$PGPASS" && -f "$WEBENV" ]] || { echo "RESTRICTED_STAGE_SECRET_FILES_MISSING"; exit 13; }
[[ "$(stat -c '%a' "$PGPASS")" == 600 ]]
[[ "$(stat -c '%a' "$WEBENV")" == 600 ]]
[[ "$(wc -l < "$WEBENV")" -eq 1 ]]
grep -Eq '^FIREBASE_WEB_API_KEY=[A-Za-z0-9_-]{16,120}$' "$WEBENV"
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "LIVE_AND_STAGING_BASELINE=PASS"
echo "REPORTING_ROLE_INSERT_PRIVILEGES=DENIED"

echo "=== B. AUTH MODULE + ORIGIN GUARD UNIT GATE (IMAGE ONLY) ==="
STEP=IMAGE_QA
sudo -n docker run --rm -i --network none --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$IMAGE" -B - <<'PY'
import inspect
from app import app
from sbi_report_access import can_view_report
from pathlib import Path

assert Path("/app/cloud_auth.py").is_file()
assert Path("/app/sbi_report_access.py").is_file()
assert list(inspect.signature(can_view_report).parameters)==[
    "user","identity","change_report"
]
session=[
  app.view_functions.get(r.endpoint).__name__
  for r in app.url_map.iter_rules()
  if r.rule=="/auth/session"
]
assert session==["session_login"], session
route=app.test_client().get("/api/reporting/v2/postgresql-summary")
assert route.status_code in (401,403), route.status_code
print("REAL_SESSION_LOGIN_ROUTE=PASS")
print("REAL_REPORT_POLICY_SOURCE=PASS")
print("ANONYMOUS_REPORT_REQUEST=DENIED")

def probe(origin):
    resp=app.test_client().post(
      "/__staging_origin_probe_missing_route__",
      headers={"Origin":origin}
    )
    return resp.status_code,"untrusted request origin" in resp.get_data(as_text=True).lower()

allowed=probe("http://127.0.0.1:18080")
foreign=probe("https://untrusted.example.invalid")
assert not allowed[1], allowed
assert foreign[0]==403 and foreign[1], foreign
print("EXACT_SSH_TUNNEL_ORIGIN=ALLOWED")
print("FOREIGN_ORIGIN=DENIED")
PY

echo "=== C. LAUNCH ADDITIONAL PRIVATE STAGING CONTAINER ==="
STEP=START
sudo -n docker run -d \
  --name "$NEW" --network "$NETWORK" --restart no \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  --mount "type=bind,source=$PGPASS,target=/run/secrets/sbi_pgpass,readonly" \
  --env-file "$WEBENV" \
  -e PGHOST=/var/run/postgresql \
  -e PGPORT=5432 -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
  -e PGPASSFILE=/run/secrets/sbi_pgpass -e PYTHONDONTWRITEBYTECODE=1 \
  "$IMAGE" >/dev/null
CREATED=YES
echo "NEW_AUTH_SOURCE_PARITY_STAGING_CONTAINER=CREATED"

echo "=== D. PRIVATE HTTP LOGIN + ANONYMOUS REPORTING ROUTES ==="
STEP=HTTP
READY=NO
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  [[ "$(sudo -n docker inspect "$NEW" --format '{{.State.Running}}')" == true ]] || { echo "PRIVATE_STAGE_PROCESS_STOPPED"; exit 14; }
  if sudo -n docker exec -i "$NEW" python3 -B - <<'PY'
import urllib.request,urllib.error
def get_status(path):
 try:
  with urllib.request.urlopen("http://127.0.0.1:8080"+path,timeout=3) as response:
   return response.status
 except urllib.error.HTTPError as exc:
  return exc.code
assert get_status("/login")==200
assert get_status("/api/reporting/v2/postgresql-summary") in (401,403)
assert get_status("/auth/me") in (401,403)
print("PRIVATE_LOGIN_PAGE_HTTP_200=PASS")
print("PRIVATE_ANONYMOUS_REPORTING=DENIED")
PY
  then READY=YES; break; fi
  sleep 2
done
[[ "$READY" == YES ]] || { echo "PRIVATE_STAGE_HTTP_QA=REVIEW_REQUIRED"; exit 15; }

echo "=== E. PRIVATE POSTGRESQL REPORT ACCESS AS READ-ONLY LOGIN ==="
STEP=POSTGRES
sudo -n docker exec -i "$NEW" python3 -B - <<'PY'
import psycopg
with psycopg.connect(connect_timeout=6) as conn:
 conn.execute("SET TRANSACTION READ ONLY")
 who,db,ro=conn.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()
 assert (who,db,ro)==("sbi_pr129_report_login","sbi_reconciliation_main","on")
 assert conn.execute("SELECT count(*) FROM sbi.invoice_financial_summary").fetchone()[0]>=0
 assert conn.execute("SELECT count(*) FROM sbi.payment_financial_summary").fetchone()[0]>=0
 print("AUTH_PARITY_STAGE_POSTGRES_READ_ONLY=PASS")
 print("AUTH_PARITY_STAGE_REPORT_VIEWS=PASS")
PY

echo "=== F. PROTECT EXISTING PR129 AND FINANCIAL STATE ==="
STEP=SAFETY
[[ -z "$(sudo -n docker port "$NEW")" ]]
[[ "$(sudo -n docker inspect "$NEW" --format '{{.HostConfig.NetworkMode}}')" == "$NETWORK" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$OLD_BEFORE" == "$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
IP="$(sudo -n docker inspect "$NEW" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
echo "NEW_AUTH_PARITY_STAGING_IP=$IP"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "OLD_PRIVATE_STAGING_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_ROWS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE 24 PRIVATE AUTH-SOURCE DEPLOYMENT ==="
echo "STAGE24_NEW_PRIVATE_STAGE=RUNNING"
echo "STAGE24_NEW_PUBLIC_PORTS=NONE"
echo "STAGE24_AUTH_SESSION_HANDLER=session_login"
echo "STAGE24_EXISTING_REPORT_AUTH_POLICY=AVAILABLE"
echo "STAGE24_AUTH_REPORTING_DATABASE=READ_ONLY"
echo "GOOGLE_APPLICATION_CREDENTIALS_STAGING=NOT_CONFIGURED"
echo "REAL_FIREBASE_AUTHENTICATED_USER_E2E=NOT_PERFORMED"
echo "AUTHORIZED_POSTGRES_REPORT_ENDPOINT=NOT_TESTED"
echo "FINAL_RELEASE=BLOCKED_PENDING_REAL_AUTHENTICATED_STAGING_QA_AND_OWNER_APPROVAL"
echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=VERIFY_SCOPED_STAGING_FIREBASE_SERVER_CREDENTIAL_REQUIREMENT"
