#!/usr/bin/env bash
# Stage 17: one-command isolated Flask/PostgreSQL candidate build + combined QA.
# Not a production deploy. No financial imports/writes and no Financial Engine changes.
set -Eeuo pipefail
umask 077
export PAGER=cat
STAGE=PRECHECK
trap 'rc=$?; echo "STAGE17_COMBINED_QA=FAIL step=$STAGE exit=$rc"; echo "LIVE_PR129_DEPLOYMENT=NOT_PERFORMED"; exit "$rc"' ERR

WORK=/home/ubuntu/sbi-pr129-pg-stage17
DB=sbi_reconciliation_main
APP=sbi-bulk-report-pr129-https-preview
PIN=4570df071eedcaf9ef2d122d634a55a9113a8e15
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
mkdir -p "$WORK"
chmod 700 "$WORK"
cd "$WORK"

echo "=== A. PRECHECK: DOCKER, DATABASE AND LIVE CONTAINER ==="
sudo -n docker info >/dev/null || { echo 'DOCKER_SUDO_ACCESS=FAIL'; false; }
LIVE_BEFORE="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
echo "PR129_LIVE_CONTAINER_VERIFIED=YES"
sudo -u postgres pg_isready -d "$DB" >/dev/null
echo "POSTGRESQL_READY=PASS"
count_financial() {
  sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c \
    "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
count_reports() {
  sudo -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c \
    "SELECT (SELECT count(*) FROM sbi.invoice_financial_summary),(SELECT count(*) FROM sbi.payment_financial_summary);"
}
FIN_BEFORE="$(count_financial)"
REP_BEFORE="$(count_reports)"
echo "FINANCIAL_COUNTS_BEFORE=$FIN_BEFORE"
echo "REPORT_COUNTS_BEFORE=$REP_BEFORE"

STAGE=SOURCE_FETCH
echo "=== B. DOWNLOAD STAGE17 SOURCE, PINNED TO GITHUB COMMIT ==="
for f in pg_reporting_blueprint.py patch_stage17_candidate.py test_stage17_blueprint.py; do
  curl -4 -fLsS --retry 3 -o "$f" "$BASE/$PIN/database/stage17/$f"
done
curl -4 -fLsS --retry 3 -o Dockerfile.stage17 "$BASE/$PIN/database/stage17/Dockerfile.stage17.v2"
for f in sbi_pg_reporting.py test_sbi_pg_reporting_combined.py test_live_readonly_stdin_v2.py; do
  curl -4 -fLsS --retry 3 -o "$f" "$BASE/$PIN/database/adapter/$f"
done
python3 -m py_compile pg_reporting_blueprint.py patch_stage17_candidate.py test_stage17_blueprint.py sbi_pg_reporting.py test_sbi_pg_reporting_combined.py test_live_readonly_stdin_v2.py
echo "STAGE17_SOURCE_SYNTAX=PASS"
echo "STAGE17_NONROOT_SOURCE_PERMISSION_FIX=INCLUDED"

STAGE=BUILD
echo "=== C. DERIVE ISOLATED PR129 CANDIDATE IMAGE (NO LIVE REPLACEMENT) ==="
IMAGE_ID="$(sudo -n docker inspect "$APP" --format '{{.Image}}')"
sudo -n docker image tag "$IMAGE_ID" sbi-pr129-stage17-base:locked
sudo -n docker build --pull=false \
  --build-arg PR129_BASE_IMAGE=sbi-pr129-stage17-base:locked \
  -f Dockerfile.stage17 -t sbi-pr129-postgres-stage17:isolated .
echo "STAGE17_CANDIDATE_IMAGE=BUILT"

STAGE=UNIT
echo "=== D. COMBINED SECURITY AND ADAPTER UNIT TESTS ==="
sudo -n docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 sbi-pr129-postgres-stage17:isolated \
  -m unittest -v test_stage17_blueprint.py test_sbi_pg_reporting_combined.py
echo "STAGE17_UNIT_QA=PASS"

STAGE=AUTH_DENY
echo "=== E. VERIFY CANDIDATE ROUTE DENIES WITHOUT VERIFIED AUTH CALLBACK ==="
sudo -n docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 sbi-pr129-postgres-stage17:isolated \
  -c 'from flask import Flask; from pg_reporting_blueprint import pg_reporting_blueprint; app=Flask("security_preflight"); app.register_blueprint(pg_reporting_blueprint); status=app.test_client().get("/api/reporting/v2/postgresql-summary").status_code; assert status==403, status; print("DEFAULT_NEW_ROUTE_AUTH=DENY_403")'

STAGE=AUTH_EXTERNAL
echo "=== F. VERIFY LIVE PR129 REPORTING ROUTE REMAINS PROTECTED ==="
STATUS="$(curl -4 -fsS --max-time 12 -o /dev/null -w '%{http_code}' 'https://pr129.13-232-241-221.sslip.io/api/reporting/v2' || true)"
echo "PR129_REPORT_CATALOG_ANONYMOUS_HTTP=$STATUS"
[[ "$STATUS" == 401 || "$STATUS" == 403 ]] || { echo 'PR129_REPORT_GATE=REVIEW_REQUIRED'; false; }

STAGE=DB_ADAPTER
echo "=== G. LIVE READ-ONLY POSTGRESQL ADAPTER VIA ISOLATED CONTAINER ==="
echo "PostgreSQL reporting password is required; it will not be echoed."
IFS= read -r -s -p "PostgreSQL report password (hidden): " REPORT_PASSWORD </dev/tty
printf '\n'
[[ -n "$REPORT_PASSWORD" ]] || { echo 'REPORT_PASSWORD_EMPTY'; false; }
printf '%s\n' "$REPORT_PASSWORD" | sudo -n docker run --rm -i --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  -e PGHOST=/var/run/postgresql -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
  --entrypoint python3 sbi-pr129-postgres-stage17:isolated \
  test_live_readonly_stdin_v2.py | tee adapter_result.txt
unset REPORT_PASSWORD
grep -qx 'ISOLATED_POSTGRES_ADAPTER_READ_ONLY=PASS' adapter_result.txt
invoice="$(awk -F'= *' '/^invoice_report_rows=/{gsub(/\r/,"",$2);print $2}' adapter_result.txt | tail -1)"
payment="$(awk -F'= *' '/^payment_report_rows=/{gsub(/\r/,"",$2);print $2}' adapter_result.txt | tail -1)"

STAGE=PARITY
echo "=== H. FINANCIAL STABILITY, REPORT PARITY, LIVE IMAGE ID ==="
FIN_AFTER="$(count_financial)"
REP_AFTER="$(count_reports)"
LIVE_AFTER="$(sudo -n docker inspect "$APP" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
echo "FINANCIAL_COUNTS_AFTER=$FIN_AFTER"
echo "REPORT_COUNTS_AFTER=$REP_AFTER"
[[ "$FIN_BEFORE" == "$FIN_AFTER" ]] || { echo 'FINANCIAL_COUNT_STABILITY=FAIL'; false; }
[[ "$REP_BEFORE" == "$REP_AFTER" ]] || { echo 'REPORT_COUNT_STABILITY=FAIL'; false; }
[[ "$REP_AFTER" == "$invoice|$payment" ]] || { echo 'ADAPTER_PARITY=FAIL'; false; }
[[ "$LIVE_BEFORE" == "$LIVE_AFTER" ]] || { echo 'LIVE_CONTAINER_IDENTITY_CHANGED=REVIEW_REQUIRED'; false; }

STAGE=COMPLETE
echo "=== STAGE 17 COMBINED RESULT ==="
echo "STAGE17_COMBINED_QA=PASS"
echo "DERIVED_FLASK_IMAGE=BUILT_NOT_DEPLOYED"
echo "DENY_BY_DEFAULT_REPORT_ROUTE=PASS"
echo "FLASK_AND_ADAPTER_UNIT_TESTS=PASS"
echo "LIVE_POSTGRESQL_READONLY_QUERY=PASS"
echo "REPORT_QUERY_PARITY=PASS"
echo "FINANCIAL_COUNTS_UNCHANGED=PASS"
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "NEXT_GATE=REVIEW_REAL_REPORTING_AUTH_CALLBACK_AND_STAGE_PRIVATE_ROUTE"
echo "PR129_POSTGRESQL_LIVE_APP_INTEGRATION=NOT_DEPLOYED"
