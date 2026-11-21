#!/usr/bin/env bash
# SBI PR129 private staging: combined read-only DB query + auth surface + SSH readiness.
# No live changes, no Caddy edits, no published ports, no credentials printed,
# no financial writes and no synthetic representation as real-user E2E.
set -Eeuo pipefail
umask 077
STEP=INIT
DB=sbi_reconciliation_main
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-private-stage
NET=sbi_pr129_pg_staging_only
FAILED=NO
on_exit() {
  rc=$?
  trap - EXIT
  if [[ "$rc" -ne 0 ]]; then
    echo "PRIVATE_STAGING_AUTH_DB_READINESS=FAIL step=$STEP exit=$rc"
  fi
  echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
  exit "$rc"
}
trap on_exit EXIT
sql() { sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts() {
  sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}

echo "=== 0. READ-ONLY BASELINE & STAGING ISOLATION ==="
STEP=BASELINE
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
[[ "$(sudo -n docker inspect "$STAGE" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$STAGE" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$(sudo -n docker inspect "$STAGE" --format '{{.HostConfig.ReadonlyRootfs}}')" == true ]]
[[ -z "$(sudo -n docker port "$STAGE")" ]]
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "PRIVATE_STAGING_NETWORK_AND_PORTS=PASS"
echo "STAGING_READONLY_ROOTFS=PASS"
echo "REPORT_ROLE_INSERT_DENIAL=PASS"

echo "=== 1. REAL POSTGRESQL READ AS PRIVATE STAGING LOGIN ==="
STEP=READONLY_DATABASE_QUERY
sudo -n docker exec -i "$STAGE" python3 -B - <<'PY'
import sys
try:
    import psycopg
    with psycopg.connect(connect_timeout=6) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        user, db, ro = conn.execute(
            "SELECT current_user,current_database(),current_setting('transaction_read_only')"
        ).fetchone()
        assert user == "sbi_pr129_report_login", "Unexpected database identity"
        assert db == "sbi_reconciliation_main", "Unexpected database name"
        assert ro == "on", "Database transaction is not read-only"
        perms = conn.execute(
            "SELECT has_table_privilege(current_user,'sbi.invoices','INSERT'), "
            "has_table_privilege(current_user,'sbi.payments','INSERT'), "
            "has_table_privilege(current_user,'sbi.allocations','INSERT')"
        ).fetchone()
        assert perms == (False, False, False), "Write privilege detected"
        invoice_count = conn.execute(
            "SELECT count(*) FROM sbi.invoice_financial_summary"
        ).fetchone()[0]
        payment_count = conn.execute(
            "SELECT count(*) FROM sbi.payment_financial_summary"
        ).fetchone()[0]
        print("STAGING_POSTGRES_LOGIN=PASS")
        print("STAGING_ROLE_READ_ONLY=PASS")
        print("INVOICE_REPORT_VIEW_ACCESS=PASS rows="+str(invoice_count))
        print("PAYMENT_REPORT_VIEW_ACCESS=PASS rows="+str(payment_count))
except Exception as ex:
    print("STAGING_POSTGRES_READ_ONLY_QUERY=FAIL error_type="+type(ex).__name__)
    sys.exit(2)
PY

echo "=== 2. PRIVATE FLASK ROUTE & SESSION CONFIG INSPECTION ==="
STEP=AUTH_SURFACE
sudo -n docker exec -i "$STAGE" python3 -B - <<'PY'
import sys
try:
    from app import app
    from flask import g
    from stage23_auth_bridge import authorize_postgres_report
    with app.test_request_context("/api/reporting/v2/postgresql-summary"):
        assert not authorize_postgres_report(), "Missing identity unexpectedly authorized"
    endpoints=sorted({
        r.rule for r in app.url_map.iter_rules()
        if any(word in r.rule.lower() for word in ("/auth", "/login", "/session"))
        and not ("<" in r.rule or ">" in r.rule)
    })
    assert "/api/reporting/v2/postgresql-summary" in {r.rule for r in app.url_map.iter_rules()}
    print("AUTH_ENDPOINTS="+(",".join(endpoints[:12]) if endpoints else "NONE_FOUND"))
    print("SESSION_COOKIE_SECURE="+str(app.config.get("SESSION_COOKIE_SECURE")))
    print("SESSION_COOKIE_SAMESITE="+str(app.config.get("SESSION_COOKIE_SAMESITE")))
    print("SESSION_COOKIE_DOMAIN_CUSTOM="+str(bool(app.config.get("SESSION_COOKIE_DOMAIN"))))
    print("STAGING_AUTH_CONTEXT_FAIL_CLOSED=PASS")
    print("STAGING_POSTGRES_REPORT_ROUTE_REGISTERED=PASS")
except Exception as ex:
    print("STAGING_AUTH_SURFACE=FAIL error_type="+type(ex).__name__)
    sys.exit(3)
PY

echo "=== 3. LIVE STATE UNCHANGED ==="
STEP=STABILITY
[[ "$(counts)" == "$FIN_BEFORE" ]]
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" == "$LIVE_BEFORE" ]]
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_ROW_COUNTS_UNCHANGED=PASS"

echo "=== 4. PRIVATE BROWSER ACCESS DATA ==="
STEP=TUNNEL
IP="$(sudo -n docker inspect "$STAGE" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
echo "PRIVATE_STAGE_DOCKER_IP=$IP"
echo "STAGING_HTTPS_PUBLIC_PORT=NONE"
echo "STAGING_BROWSER_LOGIN=NOT_PERFORMED"
echo "AUTHORIZED_USER_POSTGRES_ENDPOINT=NOT_TESTED"

STEP=COMPLETE
echo "=== FINAL PRIVATE STAGING QA ==="
echo "PRIVATE_STAGING_AUTH_DB_READINESS=PASS"
echo "STAGING_DATABASE_REPORTS_READ_ONLY=PASS"
echo "STAGING_AUTH_SURFACE_DISCOVERY=PASS"
echo "STAGING_PRIVATE_ACCESS=SSH_TUNNEL_POSSIBLE"
echo "FIREBASE_AUTHENTICATED_USER_E2E=NOT_PERFORMED"
echo "FINAL_RELEASE=BLOCKED_PENDING_REAL_USER_AUTH_QA_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
