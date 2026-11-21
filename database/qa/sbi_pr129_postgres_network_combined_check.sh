#!/usr/bin/env bash
# SBI PR129 + PostgreSQL combined READ-ONLY inspection.
# Does not migrate data, update Docker, or connect the Financial Engine.
set -u
export PAGER=cat
DB=sbi_reconciliation_main
APP=aws_lightsail-sbi-preview-1
PASS=0
REVIEW=0
sql() { sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1" 2>/dev/null; }
check() {
  if [[ "$2" == "$3" ]]; then
    echo "PASS | $1 | $2"
    PASS=$((PASS+1))
  else
    echo "REVIEW | $1 | observed=$2 expected=$3"
    REVIEW=$((REVIEW+1))
  fi
}
echo "=== A. DATABASE FOUNDATION ==="
if sudo -u postgres pg_isready -d "$DB" >/dev/null 2>&1; then
  echo "PASS | PostgreSQL accepts local connections"
  PASS=$((PASS+1))
else
  echo "REVIEW | PostgreSQL local connection unavailable"
  REVIEW=$((REVIEW+1))
fi
check DATABASE_IDENTITY "$(sql 'SELECT current_database();')" "$DB"
check MAIN_TABLES_14 "$(sql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='sbi' AND table_type='BASE TABLE';")" "14"
check INVOICES_EXISTS "$(sql "SELECT to_regclass('sbi.invoices') IS NOT NULL;")" "t"
check PAYMENTS_EXISTS "$(sql "SELECT to_regclass('sbi.payments') IS NOT NULL;")" "t"
check ALLOCATIONS_EXISTS "$(sql "SELECT to_regclass('sbi.allocations') IS NOT NULL;")" "t"
check CREDIT_NOTES_EXISTS "$(sql "SELECT to_regclass('sbi.credit_notes') IS NOT NULL;")" "t"
echo "Migration versions:"
sql 'SELECT version FROM sbi.schema_migrations ORDER BY version;' || true
echo "Financial counts (invoice|payment|allocation|credit_note):"
counts="$(sql 'SELECT (SELECT COUNT(*) FROM sbi.invoices), (SELECT COUNT(*) FROM sbi.payments), (SELECT COUNT(*) FROM sbi.allocations), (SELECT COUNT(*) FROM sbi.credit_notes);' || true)"
echo "$counts"
check EMPTY_FINANCIAL_TABLES "$counts" "0|0|0|0"
echo "Foreign-key count:"
sql "SELECT COUNT(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='sbi' AND c.contype='f';" || true
echo "Reporting view count:"
sql "SELECT COUNT(*) FROM information_schema.views WHERE table_schema='sbi';" || true
echo "=== B. DATABASE SECURITY ==="
echo "SBI role names and flags (no credentials):"
sql "SELECT rolname || ' login=' || rolcanlogin || ' superuser=' || rolsuper FROM pg_roles WHERE rolname LIKE 'sbi_%' ORDER BY rolname;" || true
check SBI_ROLES_NOT_SUPERUSERS "$(sql "SELECT COUNT(*) FROM pg_roles WHERE rolname LIKE 'sbi_%' AND rolsuper;")" "0"
listen="$(sql 'SHOW listen_addresses;' || true)"
echo "listen_addresses=$listen"
if [[ "$listen" == 'localhost' || "$listen" == '127.0.0.1' || "$listen" == '::1' ]]; then
  echo "PASS | PostgreSQL configured for loopback"
  PASS=$((PASS+1))
else
  echo "REVIEW | PostgreSQL network binding requires security review"
  REVIEW=$((REVIEW+1))
fi
echo "Port 5432 listeners:"
sudo ss -lntp | grep ':5432 ' || true
echo "=== C. PR129 AWS BACKEND ==="
if sudo docker inspect "$APP" >/dev/null 2>&1; then
  check BACKEND_STATE "$(sudo docker inspect "$APP" --format '{{.State.Status}}')" "running"
  mode="$(sudo docker inspect "$APP" --format '{{.HostConfig.NetworkMode}}')"
  echo "backend_network_mode=$mode"
  sudo docker inspect "$APP" --format '{{range $name,$net := .NetworkSettings.Networks}}{{println "network=" $name "ip=" $net.IPAddress "gateway=" $net.Gateway}}{{end}}'
  echo "Container mount destinations only:"
  sudo docker inspect "$APP" --format '{{range .Mounts}}{{println .Destination}}{{end}}'
  echo "Database-related environment VARIABLE NAMES only (values hidden):"
  sudo docker inspect "$APP" --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1 | grep -Ei 'DATABASE|POSTGRES|PGHOST|PGPORT|PGUSER|SQLALCHEMY' || true
  if [[ "$mode" != 'host' && "$listen" == 'localhost' ]]; then
    echo "REVIEW | Docker bridge container cannot use host 127.0.0.1 via its own localhost"
    REVIEW=$((REVIEW+1))
  fi
else
  echo "REVIEW | PR129 backend container not found"
  REVIEW=$((REVIEW+1))
fi
echo "=== D. BACKUP ==="
if [[ -r "/home/ubuntu/sbi-db-backups/sbi_main_initial.dump" ]] && pg_restore -l "/home/ubuntu/sbi-db-backups/sbi_main_initial.dump" >/dev/null 2>&1; then
  echo "PASS | Local backup archive list readable (restore not tested)"
  PASS=$((PASS+1))
else
  echo "REVIEW | Local backup not readable from ubuntu account"
  REVIEW=$((REVIEW+1))
fi
echo "=== E. RESULT ==="
echo "DATABASE_TOOLS_ONLY=READ_ONLY"
echo "PR129_POSTGRESQL_CONNECTION=NOT_YET_VERIFIED"
echo "FINANCIAL_ENGINE_CONNECTION=NOT_TESTED"
echo "FINANCIAL_WRITES=NONE"
echo "PASS_COUNT=$PASS REVIEW_COUNT=$REVIEW"
if [[ "$REVIEW" == '0' ]]; then
  echo "COMBINED_INFRASTRUCTURE_QA=PASS (foundation only)"
else
  echo "COMBINED_INFRASTRUCTURE_QA=REVIEW_REQUIRED"
fi
