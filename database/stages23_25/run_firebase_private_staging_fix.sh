#!/usr/bin/env bash
# SBI private PR129 Firebase web-configuration remediation, combined safety QA.
# Reads precisely FIREBASE_WEB_API_KEY from live PR129 without displaying its value.
# Starts an ADDITIONAL private staging container; does not remove or mutate
# original private staging, live PR129, Caddy, the central database, or Engine.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
OLD=sbi-pr129-pg-private-stage
NEW=sbi-pr129-pg-firebase-stage
NET=sbi_pr129_pg_staging_only
IMAGE=sbi-pr129-pg-stage23-v2:isolated
DB=sbi_reconciliation_main
BASE=/home/ubuntu/sbi-pr129-pg-private-stage
PGPASS="$BASE/pgpass"
SECRET_ENV="$BASE/staging_web_auth.env"
CREATED=NO
cleanup() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    echo "FIREBASE_PRIVATE_STAGING_QA=FAIL step=$STEP exit=$status"
    if [[ "$CREATED" == YES ]]; then
      sudo -n docker rm -f "$NEW" >/dev/null 2>&1 || true
    fi
    rm -f -- "$SECRET_ENV"
  fi
  echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
  exit "$status"
}
trap cleanup EXIT
sql() {
  sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"
}
counts() {
  sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}

echo "=== A. VERIFY LIVE + EXISTING PRIVATE STAGING BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
sudo -n docker image inspect "$IMAGE" >/dev/null
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$OLD" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$OLD" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ -z "$(sudo -n docker port "$OLD")" ]]
if sudo -n docker inspect "$NEW" >/dev/null 2>&1; then
  echo "TARGET_PRIVATE_STAGE_ALREADY_EXISTS=REVIEW_REQUIRED"
  exit 21
fi
[[ -r "$PGPASS" ]] || { echo "STAGING_POSTGRES_PASSWORD_FILE_MISSING"; exit 22; }
[[ "$(stat -c '%a' "$PGPASS")" == 600 ]] || { echo "STAGING_POSTGRES_PASSWORD_FILE_MODE=REVIEW_REQUIRED"; exit 23; }
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
OLD_BEFORE="$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
COUNTS_BEFORE="$(counts)"
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "LIVE_AND_PRIVATE_BASELINES=PASS"
echo "POSTGRES_REPORT_ROLE_NO_INSERT_PRIVILEGES=PASS"

echo "=== B. COPY ONLY REQUIRED FIREBASE WEB KEY INTO RESTRICTED STAGING FILE ==="
STEP=FIREBASE_CONFIG
if [[ -e "$SECRET_ENV" ]]; then
  echo "STAGING_FIREBASE_CONFIG_FILE_EXISTS=REVIEW_REQUIRED"
  exit 24
fi
mkdir -p "$BASE"
chmod 700 "$BASE"
touch "$SECRET_ENV"
chmod 600 "$SECRET_ENV"
if ! sudo -n docker exec "$LIVE" python3 -B -c '
import os, re, sys
value=os.environ.get("FIREBASE_WEB_API_KEY","")
if not re.fullmatch(r"[A-Za-z0-9_-]{16,120}", value):
    sys.exit(3)
sys.stdout.write("FIREBASE_WEB_API_KEY="+value+"\n")
' > "$SECRET_ENV"; then
  echo "FIREBASE_WEB_KEY_EXTRACTION=FAILED_OR_UNEXPECTED_VALUE"
  exit 25
fi
[[ "$(wc -l < "$SECRET_ENV")" -eq 1 ]]
[[ "$(stat -c '%a' "$SECRET_ENV")" == 600 ]]
echo "STAGING_WEB_AUTH_CONFIG=KEY_COPIED_SECURELY_NOT_DISPLAYED"
echo "STAGING_WEB_AUTH_CONFIG_KEYS=FIREBASE_WEB_API_KEY_ONLY"

echo "=== C. CREATE ADDITIONAL PRIVATE CONTAINER; NO PUBLISHED PORT ==="
STEP=START_AUTH_STAGE
sudo -n docker run -d \
  --name "$NEW" \
  --network "$NET" \
  --restart no \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  --mount "type=bind,source=$PGPASS,target=/run/secrets/sbi_pgpass,readonly" \
  --env-file "$SECRET_ENV" \
  -e PGHOST=/var/run/postgresql \
  -e PGPORT=5432 \
  -e PGDATABASE="$DB" \
  -e PGUSER=sbi_pr129_report_login \
  -e PGPASSFILE=/run/secrets/sbi_pgpass \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$IMAGE" >/dev/null
CREATED=YES
echo "FIREBASE_PRIVATE_STAGING_CONTAINER=CREATED"

echo "=== D. PRIVATE LOGIN AND ANONYMOUS REPORT ROUTE HEALTH ==="
STEP=HTTP_QA
ready=NO
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  [[ "$(sudo -n docker inspect "$NEW" --format '{{.State.Running}}')" == true ]] || {
    echo "FIREBASE_PRIVATE_STAGE_EXITED=YES"
    exit 26
  }
  if sudo -n docker exec "$NEW" python3 -B -c '
import os, urllib.request, urllib.error
assert bool(os.environ.get("FIREBASE_WEB_API_KEY")), "Firebase web API key not loaded"
def request(path):
    try:
        resp=urllib.request.urlopen("http://127.0.0.1:8080"+path,timeout=3)
        return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
login=request("/login")
anon=request("/api/reporting/v2/postgresql-summary")
assert login==200, "Login route not available"
assert anon in (401,403), "Anonymous PostgreSQL route was not denied"
print("PRIVATE_FIREBASE_LOGIN_HTTP=200")
print("PRIVATE_ANONYMOUS_POSTGRES_ENDPOINT=DENIED_"+str(anon))
' >/dev/null 2>&1; then
    ready=YES
    break
  fi
  sleep 2
done
[[ "$ready" == YES ]] || { echo "PRIVATE_FIREBASE_STAGE_HTTP=REVIEW_REQUIRED"; exit 27; }
echo "PRIVATE_FIREBASE_LOGIN_HTTP=PASS"
echo "PRIVATE_ANONYMOUS_POSTGRES_ENDPOINT=DENIED"

echo "=== E. RESTRICTED POSTGRESQL VIEW QUERIES FROM NEW STAGING ==="
STEP=DB_QA
sudo -n docker exec -i "$NEW" python3 -B - <<'PY'
import sys
try:
    import psycopg
    with psycopg.connect(connect_timeout=6) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        user, database, readonly = conn.execute(
            "SELECT current_user,current_database(),current_setting('transaction_read_only')"
        ).fetchone()
        assert user=="sbi_pr129_report_login"
        assert database=="sbi_reconciliation_main"
        assert readonly=="on"
        assert conn.execute(
            "SELECT NOT has_table_privilege(current_user,'sbi.invoices','INSERT') "
            "AND NOT has_table_privilege(current_user,'sbi.payments','INSERT') "
            "AND NOT has_table_privilege(current_user,'sbi.allocations','INSERT')"
        ).fetchone()[0] is True
        invoice=conn.execute("SELECT count(*) FROM sbi.invoice_financial_summary").fetchone()[0]
        payment=conn.execute("SELECT count(*) FROM sbi.payment_financial_summary").fetchone()[0]
        print("STAGING_AUTH_POSTGRES_READONLY=PASS")
        print("STAGING_AUTH_REPORT_VIEWS=PASS")
        print("INVOICE_REPORT_ROWS="+str(invoice))
        print("PAYMENT_REPORT_ROWS="+str(payment))
except Exception as exc:
    print("STAGING_AUTH_POSTGRES_QUERY=FAIL exception_type="+type(exc).__name__)
    sys.exit(2)
PY

echo "=== F. CONFIRM NO PUBLIC PORT / NO CHANGES TO LIVE OR OLD STAGE ==="
STEP=STABILITY
[[ -z "$(sudo -n docker port "$NEW")" ]]
[[ "$(sudo -n docker inspect "$NEW" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$OLD_BEFORE" == "$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$COUNTS_BEFORE" == "$(counts)" ]]
IP="$(sudo -n docker inspect "$NEW" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
echo "NEW_PRIVATE_STAGING_IP=$IP"
echo "NEW_PRIVATE_STAGING_PORT=8080_INTERNAL_ONLY"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "PREVIOUS_PRIVATE_STAGING_UNCHANGED=PASS"
echo "FINANCIAL_RECORD_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FIREBASE PRIVATE STAGING REMEDIATION RESULT ==="
echo "FIREBASE_PRIVATE_STAGING_SAFE_QA=PASS"
echo "FIREBASE_WEB_API_KEY_CONFIGURATION=PRESENT_IN_NEW_PRIVATE_STAGE"
echo "PRIVATE_LOGIN_ROUTE=HTTP_200"
echo "PRIVATE_ANONYMOUS_REPORT=DENIED"
echo "PRIVATE_PUBLISHED_PORTS=NONE"
echo "REAL_FIREBASE_AUTHENTICATED_E2E=NOT_PERFORMED"
echo "AUTHORIZED_POSTGRES_REPORT_ENDPOINT=NOT_TESTED"
echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "FINAL_RELEASE=BLOCKED_PENDING_AUTHENTICATED_STAGING_QA_AND_OWNER_APPROVAL"
echo "NEXT=REPOINT_LOCAL_SSH_TUNNEL_TO_NEW_PRIVATE_STAGING_IP_AND_TEST_LOGIN"
