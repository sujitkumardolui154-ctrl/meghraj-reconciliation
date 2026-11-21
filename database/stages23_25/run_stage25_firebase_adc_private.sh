#!/usr/bin/env bash
# Stage25: Firebase ADC in NEW isolated PR129 container; no production cutover.
set -Eeuo pipefail
umask 077
STEP=PRECHECK
LIVE=sbi-bulk-report-pr129-https-preview
OLD=sbi-pr129-pg-auth-parity-stage
NEW=sbi-pr129-pg-stage25-firebase-adc
IMAGE=sbi-pr129-pg-auth-source-parity:isolated
NET=sbi_pr129_pg_staging_only
DB=sbi_reconciliation_main
SECRET_DIR=/home/ubuntu/sbi-pr129-pg-private-stage
PGPASS="$SECRET_DIR/pgpass"
WEBENV="$SECRET_DIR/staging_web_auth.env"
CRED=/home/ubuntu/sbi-private-credentials/firebase-stage.json
ADC=/run/secrets/firebase-stage.json
CREATED=NO
finish() {
  rc=$?
  trap - EXIT
  if ((rc)); then
    echo "STAGE25_FIREBASE_ADC_COMBINED_QA=FAIL step=$STEP exit=$rc"
    if [[ "$CREATED" == YES ]]; then
      sudo -n docker rm -f "$NEW" >/dev/null 2>&1 || true
      echo "FAILED_NEW_PRIVATE_CONTAINER_REMOVED=YES"
    fi
  else
    echo "STAGE25_FIREBASE_ADC_COMBINED_QA=PASS"
  fi
  echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
  exit "$rc"
}
trap finish EXIT
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== A. PRIVATE CREDENTIAL, LIVE AND FINANCIAL PRECHECK ==="
sudo -n docker info >/dev/null
sudo -n docker image inspect "$IMAGE" >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
OLD_BEFORE="$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$OLD" --format '{{.State.Running}}')" == true ]]
[[ -z "$(sudo -n docker port "$OLD")" ]]
[[ "$(sudo -n docker inspect "$OLD" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
FIN_BEFORE="$(counts)"
if sudo -n docker inspect "$NEW" >/dev/null 2>&1; then
  echo "TARGET_ALREADY_EXISTS=REVIEW_REQUIRED"; exit 11
fi
[[ -f "$CRED" && ! -L "$CRED" && "$(stat -c '%a' "$CRED")" == 600 ]] || { echo "FIREBASE_CREDENTIAL_FILE=REVIEW_REQUIRED"; exit 12; }
[[ "$(stat -c '%u' "$CRED")" == "$(id -u)" ]] || { echo "FIREBASE_CREDENTIAL_OWNER=REVIEW_REQUIRED"; exit 13; }
[[ "$(stat -c '%a' "$(dirname "$CRED")")" == 700 ]] || { echo "FIREBASE_CREDENTIAL_DIRECTORY=REVIEW_REQUIRED"; exit 14; }
[[ -f "$PGPASS" && -f "$WEBENV" ]] || { echo "STAGING_SECRET_FILES=MISSING"; exit 15; }
[[ "$(stat -c '%a' "$PGPASS")" == 600 && "$(stat -c '%a' "$WEBENV")" == 600 ]]
[[ "$(wc -l < "$WEBENV")" == 1 ]]
grep -Eq '^FIREBASE_WEB_API_KEY=[A-Za-z0-9_-]{16,120}$' "$WEBENV"
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "CREDENTIAL_FILE_AND_FINANCIAL_ROLE_SECURITY=PASS"

echo "=== B. OFFLINE GOOGLE ADC AND FIREBASE SDK INITIALIZATION ==="
STEP=OFFLINE_FIREBASE
sudo -n docker run --rm -i --network none --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$CRED,target=$ADC,readonly" \
  -e GOOGLE_APPLICATION_CREDENTIALS="$ADC" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$IMAGE" -B - <<'PY'
import inspect,sys
try:
    import google.auth
    import firebase_admin
    from app import app
    from sbi_report_access import can_view_report
    credentials,project=google.auth.default()
    assert type(credentials).__name__=="Credentials"
    assert project=="meghraj-reconciliation"
    assert list(inspect.signature(can_view_report).parameters)==["user","identity","change_report"]
    handlers=[app.view_functions.get(r.endpoint) for r in app.url_map.iter_rules() if r.rule=="/auth/session"]
    assert len(handlers)==1 and handlers[0].__name__=="session_login"
    scope=inspect.getclosurevars(handlers[0])
    init=scope.nonlocals.get("firebase_app") or scope.globals.get("firebase_app")
    assert callable(init)
    sdk_app=init()
    assert firebase_admin.get_app(sdk_app.name) is sdk_app
    print("STAGING_GOOGLE_ADC_PROJECT=PASS")
    print("STAGING_FIREBASE_ADMIN_INITIALIZATION=PASS")
    print("STAGING_SESSION_HANDLER=PASS")
    resp=app.test_client().get("/api/reporting/v2/postgresql-summary")
    assert resp.status_code in (401,403)
    print("ANONYMOUS_POSTGRES_REPORT_ACCESS=DENIED")
except Exception as exc:
    print("STAGING_ADC_INITIALIZATION=FAIL type="+type(exc).__name__)
    sys.exit(2)
PY

echo "=== C. START NEW CONTAINER ON PRIVATE NETWORK ONLY ==="
STEP=LAUNCH
sudo -n docker run -d --name "$NEW" --network "$NET" --restart no \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  --mount "type=bind,source=$PGPASS,target=/run/secrets/sbi_pgpass,readonly" \
  --mount "type=bind,source=$CRED,target=$ADC,readonly" \
  --env-file "$WEBENV" \
  -e GOOGLE_APPLICATION_CREDENTIALS="$ADC" \
  -e PGHOST=/var/run/postgresql -e PGPORT=5432 -e PGDATABASE="$DB" \
  -e PGUSER=sbi_pr129_report_login -e PGPASSFILE=/run/secrets/sbi_pgpass \
  -e PYTHONDONTWRITEBYTECODE=1 "$IMAGE" >/dev/null
CREATED=YES

echo "=== D. PRIVATE LOGIN / ANONYMOUS DENIAL / POSTGRESQL QA ==="
STEP=PRIVATE_QA
READY=NO
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  [[ "$(sudo -n docker inspect "$NEW" --format '{{.State.Running}}')" == true ]] || { echo "NEW_STAGE_STOPPED"; exit 20; }
  if sudo -n docker exec -i "$NEW" python3 -B - <<'PY'
import google.auth,urllib.request,urllib.error
assert google.auth.default()[1]=="meghraj-reconciliation"
def status(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080"+path,timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
assert status("/login")==200
assert status("/auth/me") in (401,403)
assert status("/api/reporting/v2/postgresql-summary") in (401,403)
print("PRIVATE_LOGIN_PAGE=HTTP_200")
print("PRIVATE_ANONYMOUS_AUTH_AND_REPORTING=DENIED")
PY
  then READY=YES;break;fi
  sleep 2
done
[[ "$READY" == YES ]] || { echo "PRIVATE_HTTP_QA=REVIEW_REQUIRED"; exit 21; }
sudo -n docker exec -i "$NEW" python3 -B - <<'PY'
import psycopg
with psycopg.connect(connect_timeout=6) as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    who,db,ro=conn.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()
    assert (who,db,ro)==("sbi_pr129_report_login","sbi_reconciliation_main","on")
    perms=conn.execute(
      "SELECT has_table_privilege(current_user,'sbi.invoices','INSERT'),"
      "has_table_privilege(current_user,'sbi.payments','INSERT'),"
      "has_table_privilege(current_user,'sbi.allocations','INSERT')").fetchone()
    assert perms==(False,False,False)
    assert conn.execute("SELECT count(*) FROM sbi.invoice_financial_summary").fetchone()[0]>=0
    assert conn.execute("SELECT count(*) FROM sbi.payment_financial_summary").fetchone()[0]>=0
print("PRIVATE_POSTGRES_REPORT_VIEWS=PASS")
print("PRIVATE_POSTGRES_FINANCIAL_WRITES=DENIED")
PY

echo "=== E. PROTECT LIVE APPLICATION AND FINANCIAL DATA ==="
STEP=STABILITY
[[ -z "$(sudo -n docker port "$NEW")" ]]
[[ "$(sudo -n docker inspect "$NEW" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$OLD_BEFORE" == "$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
IP="$(sudo -n docker inspect "$NEW" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
echo "NEW_STAGE25_PRIVATE_IP=$IP"
echo "STAGE25_PUBLIC_PORTS=NONE"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "PRIOR_PRIVATE_STAGING_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE25 FIREBASE ADC COMBINED QA ==="
echo "STAGE25_GOOGLE_ADC_AND_FIREBASE_INIT=PASS"
echo "STAGE25_PRIVATE_LOGIN_PAGE=AVAILABLE"
echo "STAGE25_POSTGRES_REPORTING=READ_ONLY"
echo "STAGE25_REAL_FIREBASE_USER_E2E=NOT_PERFORMED"
echo "STAGE25_AUTHORIZED_POSTGRES_REPORT_HTTP=NOT_TESTED"
echo "STAGE25_LIVE_RELEASE=BLOCKED_PENDING_AUTHENTICATED_QA_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=REPOINT_SSH_TUNNEL_TO_NEW_STAGE25_PRIVATE_IP_AND_TEST_USER_LOGIN"
