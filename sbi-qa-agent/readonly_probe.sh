#!/usr/bin/env bash
set -Eeuo pipefail
export PATH=/usr/bin:/bin PGHOST=/var/run/postgresql PGCONNECT_TIMEOUT=5 PAGER=cat
DB=sbi_reconciliation_main
APP_URL=https://pr129.13-232-241-221.sslip.io/
pass=0; fail=0
check() {
  if [[ "$2" == "$3" ]]; then
    echo "PASS|$1|$2"; pass=$((pass+1))
  else
    echo "FAIL|$1|observed=$2|expected=$3"; fail=$((fail+1))
  fi
}
query() { psql -X -qAt -v ON_ERROR_STOP=1 -d "$DB" -c "$1" 2>/dev/null || true; }
echo "SBI_QA_AGENT_VERSION=1"
echo "FINANCIAL_WRITES=NONE"
echo "FINANCIAL_ENGINE_CONNECTION=NOT_TESTED"
if pg_isready -q -h /var/run/postgresql -d "$DB"; then
  check POSTGRESQL_ACCEPTING yes yes
else
  check POSTGRESQL_ACCEPTING no yes
fi
check DB_NAME "$(query 'SELECT current_database()')" "$DB"
check SBI_TABLES "$(query "SELECT COUNT(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='sbi' AND c.relkind='r';")" 14
check FOREIGN_KEYS "$(query "SELECT COUNT(*) FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='sbi' AND c.contype='f';")" 13
check REPORT_VIEWS "$(query "SELECT (COUNT(*)>=2)::int FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='sbi' AND c.relkind='v';")" 1
check LOCALHOST_BINDING "$(query 'SHOW listen_addresses')" localhost
code="$(curl -LsS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 "$APP_URL" 2>/dev/null || true)"
if [[ "$code" =~ ^(200|301|302|303|307|308|401|403)$ ]]; then
  echo "PASS|PR129_HTTPS_RESPONDS|HTTP=$code"; pass=$((pass+1))
else
  echo "FAIL|PR129_HTTPS_RESPONDS|HTTP=$code"; fail=$((fail+1))
fi
echo "QA_PASS=$pass QA_FAIL=$fail"
if (( fail > 0 )); then
  echo 'SBI_LIGHTSAIL_READONLY_QA=REVIEW_REQUIRED'
  exit 1
fi
echo 'SBI_LIGHTSAIL_READONLY_QA=PASS'
