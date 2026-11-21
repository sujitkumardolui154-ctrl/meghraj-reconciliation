#!/usr/bin/env bash
# SBI Reconciliation — pre-release recovery + private-staging readiness gate.
# Runs a RESTORE of an existing local archive ONLY into a NEW temporary QA DB.
# NEVER writes to sbi_reconciliation_main or deploys/restarts live PR129.
set -Eeuo pipefail
umask 077
export PAGER=cat
STEP=INIT
APP=sbi-bulk-report-pr129-https-preview
CANDIDATE=sbi-pr129-pg-stage23-v2:isolated
DB=sbi_reconciliation_main
BACKUP=/home/ubuntu/sbi-db-backups/sbi_main_initial.dump
WORK=/home/ubuntu/sbi-stage25-restore-qa
ARCHIVE_COPY=""
TEMP_DIR=""
SCRATCH=""
PRESERVE=no
cleanup() {
  local rc=$?
  trap - EXIT ERR INT TERM
  if [[ -n "$SCRATCH" && "$SCRATCH" =~ ^sbi_restore_qa_[a-z0-9_]+$ && "$SCRATCH" != "$DB" ]]; then
    sudo -n -u postgres dropdb --if-exists "$SCRATCH" || {
      echo "WARNING_TEMPORARY_QA_DATABASE_NOT_CLEANED=$SCRATCH"
      PRESERVE=yes
    }
  fi
  if [[ -n "$TEMP_DIR" && "$TEMP_DIR" == /tmp/sbi_restore_qa_* && "$PRESERVE" == no ]]; then
    sudo -n rm -rf -- "$TEMP_DIR"
  fi
  if [[ "$rc" -ne 0 ]]; then
    echo "STAGE25_RECOVERY_QA=FAIL step=$STEP exit=$rc"
  fi
  echo "LIVE_PR129_DEPLOYMENT=NOT_PERFORMED"
  exit "$rc"
}
trap cleanup EXIT
sql() { sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() {
  sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
reports() {
  sql "SELECT (SELECT count(*) FROM sbi.invoice_financial_summary),(SELECT count(*) FROM sbi.payment_financial_summary);"
}
echo "=== 0. ROOTLESS SAFETY PREFLIGHT ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
sudo -n -u postgres psql -X -A -t -d "$DB" -c 'SELECT 1;' >/dev/null
sudo -n docker inspect "$APP" >/dev/null
sudo -n docker image inspect "$CANDIDATE" >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
REP_BEFORE="$(reports)"
echo "CENTRAL_DATABASE=$DB"
echo "FINANCIAL_ROWS_BEFORE=$FIN_BEFORE"
echo "REPORT_ROWS_BEFORE=$REP_BEFORE"

echo "=== 1. EXISTING ARCHIVE AND SPACE ==="
STEP=BACKUP_PREFLIGHT
test -r "$BACKUP"
pg_restore -l "$BACKUP" >/dev/null
BYTES="$(stat -c '%s' "$BACKUP")"
DBBYTES="$(sql "SELECT pg_database_size('$DB');")"
FREE_KB="$(df -Pk /var/lib/postgresql | awk 'END{print $4}')"
REQUIRED_KB=$(( (2*DBBYTES + 3*BYTES)/1024 + 262144 ))
echo "BACKUP_ARCHIVE_BYTES=$BYTES"
echo "CURRENT_DATABASE_SIZE_BYTES=$DBBYTES"
echo "POSTGRES_DISK_AVAILABLE_KB=$FREE_KB"
echo "MINIMUM_QA_SPACE_KB=$REQUIRED_KB"
if (( FREE_KB < REQUIRED_KB )); then
  echo "RESTORE_PRECHECK=INSUFFICIENT_DISK_SPACE"
  false
fi
echo "BACKUP_FORMAT_CHECK=PASS"

echo "=== 2. RESTORE ONLY INTO A NEW TEMPORARY DATABASE ==="
STEP=RESTORE
mkdir -p "$WORK"; chmod 700 "$WORK"
TEMP_DIR="$(mktemp -d /tmp/sbi_restore_qa_XXXXXXXX)"
sudo -n chown postgres:postgres "$TEMP_DIR"
sudo -n chmod 700 "$TEMP_DIR"
ARCHIVE_COPY="$TEMP_DIR/sbi_main_initial.dump"
sudo -n install -o postgres -g postgres -m 0600 "$BACKUP" "$ARCHIVE_COPY"
SCRATCH="sbi_restore_qa_$(date -u +%Y%m%d%H%M%S)_$RANDOM"
if sudo -n -u postgres psql -X -A -t -d postgres -c "SELECT 1 FROM pg_database WHERE datname='$SCRATCH';" | grep -qx 1; then
  echo "QA_DATABASE_NAME_COLLISION=FAIL"
  false
fi
sudo -n -u postgres createdb --template=template0 --encoding=UTF8 "$SCRATCH"
sudo -n -u postgres pg_restore --exit-on-error --no-owner --no-privileges --dbname="$SCRATCH" "$ARCHIVE_COPY"
RESTORED_DB="$(sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$SCRATCH" -c 'SELECT current_database();')"
[[ "$RESTORED_DB" == "$SCRATCH" ]]
RESTORED_TABLES="$(sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$SCRATCH" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='sbi' AND table_type='BASE TABLE';")"
[[ "$RESTORED_TABLES" == 14 ]] || { echo "RESTORE_SCHEMA_PARITY=REVIEW_REQUIRED restored_tables=$RESTORED_TABLES expected=14"; false; }
# Verify the reporting views are actually queryable inside the restored archive.
sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$SCRATCH" -c 'BEGIN READ ONLY; SELECT count(*) FROM sbi.invoice_financial_summary; SELECT count(*) FROM sbi.payment_financial_summary; COMMIT;' >/dev/null
echo "ISOLATED_RESTORE_QA=PASS"
echo "RESTORED_SBI_BASE_TABLES=$RESTORED_TABLES"
echo "RESTORED_REPORT_VIEWS=QUERYABLE"

echo "=== 3. EXISTING CANDIDATE AUTH & FLASK GUARD ==="
STEP=CANDIDATE
sudo -n docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$CANDIDATE" -B -c '
from app import app
assert callable(app.config.get("SBI_PG_REPORT_AUTH_CHECK"))
r=app.test_client().get("/api/reporting/v2/postgresql-summary")
assert r.status_code in (401,403), r.status_code
print("STAGE23_CANDIDATE_ANONYMOUS_DENIAL=PASS")
'
echo "STAGE24_ISOLATED_CANDIDATE_SECURITY=PASS"

echo "=== 4. LIVE PR129 & CENTRAL FINANCIAL DATA STABILITY ==="
STEP=STABILITY
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
[[ "$REP_BEFORE" == "$(reports)" ]]
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_ROW_COUNTS_UNCHANGED=PASS"
echo "CENTRAL_REPORT_ROW_COUNTS_UNCHANGED=PASS"

echo "=== FINAL PRE-RELEASE RECOVERY QA ==="
STEP=COMPLETE
echo "STAGE25_RESTORE_REHEARSAL=PASS"
echo "STAGE24_CANDIDATE_ANONYMOUS_ACCESS=DENIED"
echo "PRIVATE_STAGING_DEPLOYMENT=NOT_PERFORMED"
echo "REAL_FIREBASE_AUTHENTICATED_E2E=NOT_PERFORMED"
echo "PRODUCTION_RELEASE=BLOCKED_PENDING_PRIVATE_STAGING_AUTH_QA_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "CENTRAL_DATABASE_FINANCIAL_WRITES=NONE"
echo "TEMPORARY_RESTORE_DATABASE=REMOVED_ON_EXIT"
echo "NEXT=PREPARE_PRIVATE_STAGING_RUNTIME_AND_AUTHENTICATED_USER_TEST"
