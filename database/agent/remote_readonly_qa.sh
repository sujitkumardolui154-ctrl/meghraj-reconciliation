#!/usr/bin/env bash
# SBI read-only remote QA, intended only for a forced-command SSH identity.
# DO NOT accept arbitrary commands, SQL, shell snippets, filenames or code from SSH clients.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PAGER=cat
unset BASH_ENV ENV CDPATH PYTHONPATH LD_PRELOAD LD_LIBRARY_PATH
DB="sbi_reconciliation_main"
APP="aws_lightsail-sbi-preview-1"
pass=0
review=0
check() {
  local name="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    printf 'PASS | %s\n' "$name"
    pass=$((pass+1))
  else
    printf 'REVIEW | %s | observed=%s expected=%s\n' "$name" "$actual" "$expected"
    review=$((review+1))
  fi
}
db_read() {
  /usr/sbin/runuser -u postgres -- /usr/bin/psql -X -qAt -v ON_ERROR_STOP=1 \
    -d "$DB" -c "$1"
}
echo 'SBI_REMOTE_QA_MODE=READ_ONLY'
if /usr/sbin/runuser -u postgres -- /usr/bin/pg_isready -d "$DB" >/dev/null 2>&1; then
  check POSTGRESQL_READY PASS PASS
else
  check POSTGRESQL_READY REVIEW PASS
fi
check DATABASE_IDENTITY "$(db_read 'SELECT current_database();')" "$DB"
check TABLE_COUNT "$(db_read "SELECT count(*) FROM information_schema.tables WHERE table_schema='sbi' AND table_type='BASE TABLE';")" 14
check FOREIGN_KEY_COUNT "$(db_read "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='sbi' AND c.contype='f';")" 13
check SOURCE_TABLES "$(db_read "SELECT count(*) FROM (VALUES ('invoices'),('payments'),('allocations'),('credit_notes')) AS v(t) WHERE to_regclass('sbi.'||v.t) IS NOT NULL;")" 4
check REPORT_VIEWS "$(db_read "SELECT count(*) FROM information_schema.views WHERE table_schema='sbi';")" 2
check FINANCIAL_RECORDS_EMPTY "$(db_read 'SELECT (SELECT count(*) FROM sbi.invoices)+(SELECT count(*) FROM sbi.payments)+(SELECT count(*) FROM sbi.allocations)+(SELECT count(*) FROM sbi.credit_notes);')" 0
check NON_SUPERUSER_SBI_ROLES "$(db_read "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'sbi_%' AND rolsuper;")" 0
listen="$(db_read 'SHOW listen_addresses;')"
if [[ "$listen" == localhost || "$listen" == 127.0.0.1 || "$listen" == ::1 ]]; then
  check PRIVATE_POSTGRES_BIND PASS PASS
else
  check PRIVATE_POSTGRES_BIND REVIEW PASS
fi
container_state="$(/usr/bin/docker inspect "$APP" --format '{{.State.Status}}' 2>/dev/null || true)"
check PR129_BACKEND_RUNNING "$container_state" running
backup="/home/ubuntu/sbi-db-backups/sbi_main_initial.dump"
if [[ -r "$backup" ]] && /usr/bin/pg_restore -l "$backup" >/dev/null 2>&1; then
  check BACKUP_ARCHIVE_READABLE PASS PASS
else
  check BACKUP_ARCHIVE_READABLE REVIEW PASS
fi
printf 'PASS_COUNT=%s REVIEW_COUNT=%s\n' "$pass" "$review"
echo 'PR129_POSTGRESQL_AUTHENTICATED_CONNECTION=NOT_TESTED'
echo 'FINANCIAL_ENGINE_CONNECTION=NOT_TESTED'
echo 'FINANCIAL_WRITES=NONE'
echo 'BACKUP_FULL_RESTORE=NOT_TESTED'
if [[ "$review" -eq 0 ]]; then
  echo 'LIGHTSAIL_READONLY_AGENT_QA=PASS'
else
  echo 'LIGHTSAIL_READONLY_AGENT_QA=REVIEW_REQUIRED'
  exit 2
fi
