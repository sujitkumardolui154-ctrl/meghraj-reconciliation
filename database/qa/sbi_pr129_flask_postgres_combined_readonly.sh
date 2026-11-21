#!/usr/bin/env bash
# SBI PR129 + PostgreSQL combined READ-ONLY QA.
# No imports, financial writes, Docker restarts, or Financial Engine changes.
set -u
export PAGER=cat
DB=sbi_reconciliation_main
APP=aws_lightsail-sbi-preview-1
PASS=0
REVIEW=0
pass() { echo "PASS | $1"; PASS=$((PASS+1)); }
review() { echo "REVIEW | $1"; REVIEW=$((REVIEW+1)); }
info() { echo "INFO | $1"; }
sql() { sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1" 2>/dev/null; }
check() {
  local title="$1" got="$2" want="$3"
  if [ "$got" = "$want" ]; then pass "$title"; else review "$title (observed=$got expected=$want)"; fi
}
echo "=== A. CENTRAL POSTGRESQL DATABASE ==="
if sudo -u postgres pg_isready -d "$DB" >/dev/null 2>&1; then pass "Local PostgreSQL readiness"; else review "Local PostgreSQL readiness"; fi
check "Database identity" "$(sql 'SELECT current_database();' || true)" "$DB"
check "14 SBI base tables" "$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema='sbi' AND table_type='BASE TABLE';" || true)" "14"
check "HBA parse errors absent" "$(sql "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;" || true)" "0"
check "Reporting login enabled" "$(sql "SELECT rolcanlogin FROM pg_roles WHERE rolname='sbi_pr129_report_login';" || true)" "t"
check "Reporting login not superuser" "$(sql "SELECT NOT rolsuper FROM pg_roles WHERE rolname='sbi_pr129_report_login';" || true)" "t"
check "Reporting role membership" "$(sql "SELECT pg_has_role('sbi_pr129_report_login','sbi_report_reader','MEMBER');" || true)" "t"
check "Invoice report SELECT permission" "$(sql "SELECT has_table_privilege('sbi_pr129_report_login','sbi.invoice_financial_summary','SELECT');" || true)" "t"
check "Payment report SELECT permission" "$(sql "SELECT has_table_privilege('sbi_pr129_report_login','sbi.payment_financial_summary','SELECT');" || true)" "t"
check "No invoice INSERT permission" "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT');" || true)" "t"
check "No payment INSERT permission" "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT');" || true)" "t"
check "No allocation INSERT permission" "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');" || true)" "t"
check "Private SCRAM authentication rule" "$(sql "SELECT EXISTS (SELECT 1 FROM pg_hba_file_rules WHERE type='local' AND auth_method='scram-sha-256' AND 'sbi_pr129_report_login'=ANY(user_name) AND 'sbi_reconciliation_main'=ANY(database) AND error IS NULL);" || true)" "t"
info "Current report view row counts:"
sql "SELECT 'invoice_view_rows='||count(*) FROM sbi.invoice_financial_summary;" || true
sql "SELECT 'payment_view_rows='||count(*) FROM sbi.payment_financial_summary;" || true
echo "=== B. NETWORK AND BACKUP ==="
listen="$(sql 'SHOW listen_addresses;' || true)"
if [ "$listen" = "localhost" ] || [ "$listen" = "127.0.0.1" ]; then pass "Postgres localhost binding"; else review "Review listen_addresses=$listen"; fi
if [ -r /home/ubuntu/sbi-db-backups/sbi_main_initial.dump ] && pg_restore -l /home/ubuntu/sbi-db-backups/sbi_main_initial.dump >/dev/null 2>&1; then pass "Local backup archive readable (restore untested)"; else review "Local backup archive not readable"; fi
echo "=== C. ISOLATED DOCKER SOCKET ==="
if sudo docker image inspect postgres:16-alpine >/dev/null 2>&1; then
  result="$(sudo docker run --rm --pull=never --network none --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly postgres:16-alpine pg_isready -h /var/run/postgresql -p 5432 -d "$DB" 2>&1 || true)"
  info "$result"
  if [[ "$result" == *"accepting connections"* ]]; then pass "Isolated Docker socket reachability"; else review "Isolated Docker socket reachability"; fi
else
  review "postgres:16-alpine test image absent"
fi
echo "=== D. PR129 FLASK BACKEND ==="
if sudo docker inspect "$APP" >/dev/null 2>&1; then
  check "Backend running" "$(sudo docker inspect "$APP" --format '{{.State.Status}}')" "running"
  info "Image=$(sudo docker inspect "$APP" --format '{{.Config.Image}}')"
  info "Network=$(sudo docker inspect "$APP" --format '{{.HostConfig.NetworkMode}}')"
  info "Workdir=$(sudo docker inspect "$APP" --format '{{.Config.WorkingDir}}')"
  info "Mount destinations (not host paths):"
  sudo docker inspect "$APP" --format '{{range .Mounts}}{{println .Destination}}{{end}}' || true
  info "Framework and driver availability:"
  sudo docker exec "$APP" python3 -c 'import importlib.util as u; print({m:bool(u.find_spec(m)) for m in ("flask","psycopg","psycopg2","sqlalchemy")})' || review "Python package inspection error"
  info "Candidate source filenames:"
  sudo docker exec "$APP" sh -c 'pwd; for d in /app /srv/app /workspace; do if [ -d "$d" ]; then find "$d" -maxdepth 2 -type f \( -name "*.py" -o -name "requirements*.txt" -o -name "Dockerfile" \) -print 2>/dev/null | head -25; fi; done' || true
else
  review "PR129 backend container not found"
fi
echo "=== E. PR129 ANONYMOUS HTTPS GUARDS ==="
for path in /auth/me /api/bulk-report/status; do
  code="$(curl -4 --max-time 12 -sS -o /dev/null -w '%{http_code}' "https://pr129.13-232-241-221.sslip.io$path" 2>/dev/null || true)"
  if [ "$code" = "401" ] || [ "$code" = "403" ]; then pass "$path anonymous blocked HTTP=$code"; else review "$path HTTP=$code (check reachability separately)"; fi
done
echo "=== F. FINAL ==="
echo "PASS_COUNT=$PASS"
echo "REVIEW_COUNT=$REVIEW"
echo "DATABASE_WRITES=NONE"
echo "CONTAINERS_RESTARTED=NONE"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "PR129_POSTGRESQL_ADAPTER=NOT_YET_VERIFIED"
if [ "$REVIEW" -eq 0 ]; then echo "COMBINED_READ_ONLY_QA=PASS"; else echo "COMBINED_READ_ONLY_QA=REVIEW_REQUIRED"; fi
