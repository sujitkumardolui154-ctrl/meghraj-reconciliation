#!/usr/bin/env bash
# Read-only preflight: SBI PostgreSQL authentication & PR129 Docker readiness.
# No database mutations, no container restarts, no passwords printed.
set -u
export PAGER=cat
DB=sbi_reconciliation_main
APP=aws_lightsail-sbi-preview-1

sql() { sudo -u postgres psql -X -A -t -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
show() { printf '\n=== %s ===\n' "$1"; }

show '1 POSTGRESQL IDENTITY AND AUTH CONFIGURATION'
sql "SELECT current_database(), current_setting('server_version'), current_setting('unix_socket_directories'), current_setting('listen_addresses');" || exit 1

show '2 SBI ROLES (NO PASSWORDS)'
sql "SELECT rolname, rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('sbi_report_reader','sbi_ingest_runtime','sbi_engine_runtime') ORDER BY rolname;" || exit 1

show '3 ROLE PERMISSION CHECK'
sql "SELECT 'reporter_can_read_invoice_view',has_table_privilege('sbi_report_reader','sbi.invoice_financial_summary','SELECT') UNION ALL SELECT 'reporter_can_read_payment_view',has_table_privilege('sbi_report_reader','sbi.payment_financial_summary','SELECT') UNION ALL SELECT 'reporter_cannot_insert_invoice',NOT has_table_privilege('sbi_report_reader','sbi.invoices','INSERT') UNION ALL SELECT 'reporter_cannot_insert_payment',NOT has_table_privilege('sbi_report_reader','sbi.payments','INSERT') UNION ALL SELECT 'ingest_can_insert_invoice',has_table_privilege('sbi_ingest_runtime','sbi.invoices','INSERT') UNION ALL SELECT 'ingest_can_insert_payment',has_table_privilege('sbi_ingest_runtime','sbi.payments','INSERT');" || exit 1

show '4 LOCAL AUTH RULES (NO SECRETS)'
sql "SELECT line_number,type,array_to_string(database,','),array_to_string(user_name,','),coalesce(address,''),auth_method,coalesce(error,'') FROM pg_hba_file_rules WHERE type='local' ORDER BY line_number;" || exit 1

show '5 PG CONFIGURATION ERRORS'
sql "SELECT COUNT(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;" || exit 1

show '6 BACKEND CONTAINER (NETWORK AND MOUNTS)'
if sudo docker inspect "$APP" >/dev/null 2>&1; then
  sudo docker inspect "$APP" --format 'status={{.State.Status}} network={{.HostConfig.NetworkMode}}'
  sudo docker inspect "$APP" --format '{{range .Mounts}}{{println "mount=" .Destination}}{{end}}'
  echo 'PostgreSQL-related environment variable NAMES (values redacted):'
  sudo docker inspect "$APP" --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1 | grep -Ei 'DATABASE|POSTGRES|PGHOST|PGPORT|PGUSER|SQLALCHEMY' || true
else
  echo 'BACKEND_CONTAINER=NOT_FOUND'
fi

show '7 SOCKET REACHABILITY (NOT AUTHENTICATION)'
if sudo docker image inspect postgres:16-alpine >/dev/null 2>&1; then
  sudo docker run --rm --pull=never --network none --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly postgres:16-alpine pg_isready -h /var/run/postgresql -p 5432 -d "$DB" || true
else
  echo 'DOCKER_POSTGRES_CLIENT_IMAGE=NOT_CACHED; socket reachability was already verified previously.'
fi

show 'FINAL'
echo 'READ_ONLY_PREFLIGHT=COMPLETE'
echo 'AUTHENTICATED_APPLICATION_DB_CONNECTION=NOT_YET_TESTED'
echo 'DATABASE_WRITES=NONE'
echo 'FINANCIAL_ENGINE=UNCHANGED'
echo 'NEXT=CREATE_RESTRICTED_LOGIN_ROLE_AND_TEST_AUTHENTICATED_SOCKET_AFTER_HBA_REVIEW'
