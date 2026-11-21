#!/usr/bin/env bash
# Fix only the known "Untrusted request origin" error for the 18080 SSH tunnel,
# in a NEW PRIVATE image/container. NO live changes, no Caddy changes,
# no public ports, no financial writes and no bypass of Firebase/session checks.
set -Eeuo pipefail
umask 077
STEP=START
BASE_IMAGE=sbi-pr129-pg-stage23-v2:isolated
IMAGE=sbi-pr129-pg-origin18080:isolated
STAGE=sbi-pr129-pg-origin-stage
LIVE=sbi-bulk-report-pr129-https-preview
EXISTING=sbi-pr129-pg-firebase-stage
NET=sbi_pr129_pg_staging_only
DB=sbi_reconciliation_main
SECRET_DIR=/home/ubuntu/sbi-pr129-pg-private-stage
WEB_ENV="$SECRET_DIR/staging_web_auth.env"
PGPASS="$SECRET_DIR/pgpass"
WORK=/home/ubuntu/sbi-stage-origin-fix
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
PIN=826283f3aa923e48f9e3805cf844b960a99cad5c
NEW_CREATED=NO
cleanup() {
  rc=$?
  trap - EXIT
  if [[ "$rc" -ne 0 ]]; then
    echo "STAGING_ORIGIN_FIX_QA=FAIL step=$STEP exit=$rc"
    if [[ "$NEW_CREATED" == YES ]]; then sudo -n docker rm -f "$STAGE" >/dev/null 2>&1 || true; fi
  fi
  echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
  exit "$rc"
}
trap cleanup EXIT
sql() { sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() { sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== A. PRIVATE STAGING SECURITY BASELINE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
sudo -n docker image inspect "$BASE_IMAGE" >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
EXISTING_BEFORE="$(sudo -n docker inspect "$EXISTING" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ -z "$(sudo -n docker port "$EXISTING")" ]]
[[ "$(sudo -n docker inspect "$EXISTING" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
if sudo -n docker inspect "$STAGE" >/dev/null 2>&1; then
  echo "TARGET_ORIGIN_STAGE_ALREADY_EXISTS=REVIEW_REQUIRED"
  exit 21
fi
[[ -r "$PGPASS" && -r "$WEB_ENV" ]] || { echo "STAGE_SECRETS_MISSING=REVIEW_REQUIRED"; exit 22; }
[[ "$(stat -c '%a' "$PGPASS")" == 600 && "$(stat -c '%a' "$WEB_ENV")" == 600 ]] || { echo "STAGE_SECRET_PERMISSIONS=REVIEW_REQUIRED"; exit 23; }
# The staging env must contain exactly one recognized public Firebase config key.
[[ "$(wc -l < "$WEB_ENV")" == 1 ]]
grep -Eq '^FIREBASE_WEB_API_KEY=[A-Za-z0-9_-]{16,120}$' "$WEB_ENV"
FIN_BEFORE="$(counts)"
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "PRIVATE_STAGE_BASELINE=PASS"
echo "STAGING_AUTH_CONFIG=RESTRICTED"
echo "FINANCIAL_ROLE_WRITES=DENIED"

echo "=== B. FETCH PINNED STAGING-ONLY ORIGIN PATCH ==="
STEP=FETCH
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"
for f in patch_private_tunnel_origin.py Dockerfile.private-origin; do
  curl -4 -fLsS --retry 3 -o "$f" "$BASE/$PIN/database/stages23_25/$f"
done
python3 -m py_compile patch_private_tunnel_origin.py
echo "ORIGIN_PATCH_SOURCE_SYNTAX=PASS"

echo "=== C. CREATE NEW PRIVATE IMAGE; DO NOT CHANGE LIVE OR OLD STAGES ==="
STEP=IMAGE
sudo -n docker build --pull=false --build-arg STAGE23_IMAGE="$BASE_IMAGE" \
  -f Dockerfile.private-origin -t "$IMAGE" .
echo "PRIVATE_ORIGIN_DERIVED_IMAGE=BUILT"

echo "=== D. FLASK ORIGIN ALLOWLIST POSITIVE + NEGATIVE QA ==="
STEP=ORIGIN_TEST
sudo -n docker run --rm -i --network none --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$IMAGE" -B - <<'PY'
from app import app
from pathlib import Path
source=Path("/app/dashboard_sessions.py").read_text()
assert "SBI_PRIVATE_TUNNEL_ORIGIN_18080_ONLY = True" in source
assert "http://127.0.0.1:18080" in source
def origin_probe(value):
    # A deliberately nonexistent route prevents any real login attempt.
    r=app.test_client().post("/__stage_origin_guard_probe_no_route__", headers={"Origin":value})
    return r.status_code, r.get_data(as_text=True).lower()
allow_status, allow_body=origin_probe("http://127.0.0.1:18080")
deny_status, deny_body=origin_probe("https://untrusted.example.invalid")
print("STAGING_TUNNEL_ORIGIN_PROBE_HTTP="+str(allow_status))
print("STAGING_UNTRUSTED_ORIGIN_PROBE_HTTP="+str(deny_status))
assert "untrusted request origin" not in allow_body, "Tunnel origin still untrusted"
assert "untrusted request origin" in deny_body, "Untrusted foreign origin unexpectedly accepted"
print("STAGING_TUNNEL_ORIGIN_ALLOWED=PASS")
print("STAGING_UNTRUSTED_FOREIGN_ORIGIN_DENIED=PASS")
print("STAGING_ORIGIN_GUARD_REMAINS_ENABLED=PASS")
PY

echo "=== E. LAUNCH ADDITIONAL PRIVATE STAGING CONTAINER ==="
STEP=STAGE_START
sudo -n docker run -d \
  --name "$STAGE" \
  --network "$NET" --restart no \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  --mount "type=bind,source=$PGPASS,target=/run/secrets/sbi_pgpass,readonly" \
  --env-file "$WEB_ENV" \
  -e PGHOST=/var/run/postgresql -e PGPORT=5432 \
  -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
  -e PGPASSFILE=/run/secrets/sbi_pgpass -e PYTHONDONTWRITEBYTECODE=1 \
  "$IMAGE" >/dev/null
NEW_CREATED=YES

echo "=== F. PRIVATE HTTP AND REPORT ROLE READ-ONLY CHECKS ==="
STEP=STAGE_SMOKE
ready=NO
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  [[ "$(sudo -n docker inspect "$STAGE" --format '{{.State.Running}}')" == true ]] || { echo "STAGE_PROCESS_EXITED=FAIL"; exit 24; }
  if sudo -n docker exec "$STAGE" python3 -B -c '
import urllib.request,urllib.error
def status(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080"+path,timeout=3) as r:return r.status
    except urllib.error.HTTPError as e:return e.code
assert status("/login")==200
assert status("/api/reporting/v2/postgresql-summary") in (401,403)
' >/dev/null 2>&1; then ready=YES;break;fi
  sleep 2
done
[[ "$ready" == YES ]] || { echo "STAGE_HTTP_SMOKE=REVIEW_REQUIRED"; exit 25; }
sudo -n docker exec -i "$STAGE" python3 -B - <<'PY'
import psycopg
with psycopg.connect(connect_timeout=6) as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    who,db,ro=conn.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()
    assert (who,db,ro)==("sbi_pr129_report_login","sbi_reconciliation_main","on")
    assert conn.execute("SELECT count(*) FROM sbi.invoice_financial_summary").fetchone()[0]>=0
    assert conn.execute("SELECT count(*) FROM sbi.payment_financial_summary").fetchone()[0]>=0
print("STAGING_READ_ONLY_POSTGRES_REPORTS=PASS")
PY

echo "=== G. LIVE SAFETY AND PRIVATE IP ==="
STEP=STABILITY
[[ -z "$(sudo -n docker port "$STAGE")" ]]
[[ "$(sudo -n docker inspect "$STAGE" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$EXISTING_BEFORE" == "$(sudo -n docker inspect "$EXISTING" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
IP="$(sudo -n docker inspect "$STAGE" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
echo "NEW_PRIVATE_ORIGIN_STAGING_IP=$IP"
echo "PRIVATE_ORIGIN_STAGING_PORT=8080_INTERNAL_ONLY"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "PREVIOUS_FIREBASE_STAGE_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_ROW_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL PRIVATE ORIGIN ALLOWLIST QA ==="
echo "STAGING_ORIGIN_FIX_QA=PASS"
echo "TUNNEL_ORIGIN=http://127.0.0.1:18080"
echo "UNTRUSTED_ORIGIN_DENIAL=PASS"
echo "ORIGIN_VALIDATION=ENABLED"
echo "PRIVATE_STAGE_PUBLISHED_PORTS=NONE"
echo "PRIVATE_STAGE_FIREBASE_WEB_CONFIG=PRESENT"
echo "PRIVATE_STAGE_POSTGRES_REPORTING=READ_ONLY"
echo "REAL_FIREBASE_AUTHENTICATED_USER_E2E=NOT_PERFORMED"
echo "AUTHORIZED_POSTGRES_REPORT_ENDPOINT=NOT_TESTED"
echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "FINAL_RELEASE=BLOCKED_PENDING_AUTHENTICATED_STAGING_QA_AND_OWNER_APPROVAL"
echo "NEXT=REPOINT_SSH_TUNNEL_TO_NEW_PRIVATE_ORIGIN_STAGING_IP_AND_LOGIN"
