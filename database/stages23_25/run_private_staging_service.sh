#!/usr/bin/env bash
# SBI PR129 PRIVATE staging service only. No public ports, no Caddy changes,
# no database writes and no live PR129 or Financial Engine restart.
set -Eeuo pipefail
umask 077
export PAGER=cat
STEP=INIT
DB=sbi_reconciliation_main
LIVE=sbi-bulk-report-pr129-https-preview
IMAGE=sbi-pr129-pg-stage23-v2:isolated
STAGE=sbi-pr129-pg-private-stage
NET=sbi_pr129_pg_staging_only
BASE=/home/ubuntu/sbi-pr129-pg-private-stage
CREATED=NO
SECRET_FILE="$BASE/pgpass"
cleanup() {
  code=$?
  trap - EXIT
  if [[ "$code" -ne 0 ]]; then
    echo "PRIVATE_STAGE_QA=FAIL step=$STEP code=$code"
    if [[ "$CREATED" == YES ]]; then
      sudo -n docker rm -f "$STAGE" >/dev/null 2>&1 || true
    fi
    rm -f "$SECRET_FILE"
  fi
  echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
  exit "$code"
}
trap cleanup EXIT
sql() { sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() { sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== A. SAFE BASELINE ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
sudo -u postgres pg_isready -d "$DB" >/dev/null
sudo -n docker image inspect "$IMAGE" >/dev/null
sudo -n docker inspect "$LIVE" >/dev/null
if sudo -n docker inspect "$STAGE" >/dev/null 2>&1; then
  echo "PRIVATE_STAGE_ALREADY_EXISTS=REVIEW_REQUIRED"
  exit 12
fi
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
mkdir -p "$BASE"
chmod 700 "$BASE"
echo "FINANCIAL_COUNTS_BEFORE=$FIN_BEFORE"
echo "REPORTING_ROLE_WRITE_ACCESS=DENIED"

echo "=== B. DEDICATED PRIVATE DOCKER NETWORK ==="
STEP=NETWORK
if ! sudo -n docker network inspect "$NET" >/dev/null 2>&1; then
  sudo -n docker network create --driver bridge "$NET" >/dev/null
fi
echo "STAGING_NETWORK=PRIVATE_DEDICATED"

echo "=== C. PASSWORD VIA HIDDEN PROMPT, LOCAL PROTECTED PGPASS ==="
STEP=SECRET
echo "Enter the PostgreSQL REPORT login password (not your Linux sudo password)."
IFS= read -r -s -p "sbi_pr129_report_login password (hidden): " REPORT_PASSWORD </dev/tty
printf '\n'
[[ -n "$REPORT_PASSWORD" ]]
printf '*:5432:%s:%s:' "$DB" sbi_pr129_report_login > "$SECRET_FILE"
# Escape only libpq password-file delimiter characters, never print secret.
printf '%s' "$REPORT_PASSWORD" | python3 -c 'import sys; s=sys.stdin.read(); sys.stdout.write(s.replace("\\", "\\\\").replace(":", "\\:"))' >> "$SECRET_FILE"
printf '\n' >> "$SECRET_FILE"
unset REPORT_PASSWORD
chmod 600 "$SECRET_FILE"
echo "PGPASS_SECRET=PROTECTED_LOCAL_FILE"

echo "=== D. START ISOLATED STAGING CONTAINER (NO PUBLISHED PORTS) ==="
STEP=START_STAGE
set -- sudo -n docker run -d \
  --name "$STAGE" \
  --network "$NET" \
  --restart no \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  --mount "type=bind,source=$SECRET_FILE,target=/run/secrets/sbi_pgpass,readonly" \
  -e PGHOST=/var/run/postgresql \
  -e PGPORT=5432 \
  -e PGDATABASE="$DB" \
  -e PGUSER=sbi_pr129_report_login \
  -e PGPASSFILE=/run/secrets/sbi_pgpass \
  -e PYTHONDONTWRITEBYTECODE=1
# Never import an unreviewed environment file; DATABASE_URL or PG*
# overrides could bypass the established read-only PostgreSQL identity.
if [[ -f "$BASE/staging.env" ]]; then
  echo "STAGING_ENV_FILE_PRESENT=REQUIRES_REVIEW"
  echo "No environment file was loaded; review variable names and least privilege first."
  exit 13
fi
echo "STAGING_ENV=RESTRICTED_REPORTING_ONLY"
"$@" "$IMAGE" >/dev/null
CREATED=YES
echo "PRIVATE_STAGE_CONTAINER_CREATED=PASS"

echo "=== E. PRIVATE SERVICE AND ANONYMOUS ACCESS CHECK ==="
STEP=SMOKE
ready=NO
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  [[ "$(sudo -n docker inspect "$STAGE" --format '{{.State.Running}}')" == true ]] || { echo "PRIVATE_STAGE_PROCESS_EXITED"; exit 14; }
  if sudo -n docker exec "$STAGE" python3 -B -c '
import urllib.request
import urllib.error
url="http://127.0.0.1:8080/api/reporting/v2/postgresql-summary"
try:
    result=urllib.request.urlopen(url,timeout=3)
    status=result.status
except urllib.error.HTTPError as ex:
    status=ex.code
assert status in (401,403), status
print("ANONYMOUS_HTTP="+str(status))
' >/dev/null 2>&1; then
    ready=YES
    break
  fi
  sleep 2
done
[[ "$ready" == YES ]] || { echo "PRIVATE_STAGE_SMOKE=REVIEW_REQUIRED"; exit 15; }
[[ -z "$(sudo -n docker port "$STAGE")" ]] || { echo "PRIVATE_STAGE_PORT_EXPOSURE=FAIL"; exit 16; }
[[ "$(counts)" == "$FIN_BEFORE" ]] || { echo "FINANCIAL_COUNT_CHANGED=REVIEW_REQUIRED"; exit 17; }
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" == "$LIVE_BEFORE" ]] || { echo "LIVE_CONTAINER_CHANGED=REVIEW_REQUIRED"; exit 18; }

STEP=COMPLETE
echo "=== PRIVATE STAGING RESULT ==="
echo "PRIVATE_STAGE_SERVICE=RUNNING"
echo "PRIVATE_STAGE_NETWORK=DEDICATED"
echo "PRIVATE_STAGE_PUBLISHED_PORTS=NONE"
echo "PRIVATE_STAGE_ANONYMOUS_REPORTING=DENIED"
echo "CENTRAL_FINANCIAL_COUNTS_STABLE=PASS"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "FIREBASE_AUTHENTICATED_USER_E2E=NOT_TESTED"
echo "AUTHORIZED_POSTGRES_REPORT_QUERY=NOT_TESTED"
echo "LIVE_RELEASE=BLOCKED_PENDING_AUTHENTICATED_STAGING_QA_AND_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=AUTHENTICATED_STAGING_ACCESS_WITHOUT_PUBLIC_PORTS"
