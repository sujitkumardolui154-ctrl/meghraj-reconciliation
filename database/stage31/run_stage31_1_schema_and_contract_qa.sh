#!/usr/bin/env bash
# SBI Stage 31.1 — single combined read-only PostgreSQL schema discovery,
# source-contract regression QA and production safety gate.
# DOES NOT create/alter DB objects, deploy Docker, import Excel, enable finance.
set -Eeuo pipefail
umask 077
export PAGER=cat PYTHONDONTWRITEBYTECODE=1
STEP=INIT
DB=sbi_reconciliation_main
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
COMMIT=c27b6e03b6e4a9daf0b1684c56c7d9feaf8192c9
SITE=pr129.13-232-241-221.sslip.io
WORK=/home/ubuntu/sbi-stage31-private-qa
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$WORK" "$EVID"
chmod 700 "$WORK" "$EVID"
LOG="$EVID/stage31_1_schema_contract_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1
BEFORE=""
CONF_SHA=""
failmark=0
counts() {
  sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c \
  "BEGIN READ ONLY; SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes); COMMIT;" |
  grep -E '^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$' | tail -1
}
finish(){
 local code=$?
 trap - EXIT
 if [[ -n "$BEFORE" ]];then
   local after
   after="$(counts 2>/dev/null || true)"
   if [[ "$BEFORE" != "$after" ]];then
     echo "STAGE31_SOURCE_FINANCIAL_COUNTS_UNCHANGED=FAIL_OR_UNVERIFIED"
     code=91
   else
     echo "STAGE31_SOURCE_FINANCIAL_COUNTS_UNCHANGED=PASS"
   fi
 fi
 if [[ -n "$CONF_SHA" ]];then
   local current
   current="$(sudo -n sha256sum /home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile 2>/dev/null | awk '{print $1}')"
   if [[ "$CONF_SHA" != "$current" ]];then
     echo "STAGE31_PRODUCTION_CADDYFILE_UNCHANGED=FAIL_OR_UNVERIFIED"
     code=92
   else
     echo "STAGE31_PRODUCTION_CADDYFILE_UNCHANGED=PASS"
   fi
 fi
 if ((code));then echo "STAGE31_COMBINED_READONLY_QA=FAIL step=$STEP exit=$code"
 else echo "STAGE31_COMBINED_READONLY_QA=PASS";fi
 echo "STAGE31_SCHEMA_MAPPING=CATALOG_CAPTURED_REQUIRES_REVIEW"
 echo "STAGE31_POSTGRESQL_IMPORT_WRITER=NOT_INSTALLED"
 echo "STAGE31_PRODUCTION_DATABASE_WRITES=NOT_AUTHORIZED"
 echo "STAGE31_RECONCILIATION_ENGINE=DISABLED_UNCHANGED"
 echo "STAGE31_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE31_EVIDENCE_FILE=$LOG"
 exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=== A. RECORD LIVE CENTRAL POSTGRESQL BASELINE ==="
STEP=BASELINE
[[ "$(id -un)" == ubuntu ]] || { echo "STAGE31_RUN_AS_UBUNTU_REQUIRED";exit 11; }
[[ -f /home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile ]] ||
 { echo "STAGE31_CADDY_CONFIG_MISSING";exit 12; }
CONF_SHA="$(sudo -n sha256sum /home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile | awk '{print $1}')"
BEFORE="$(counts)"
[[ "$BEFORE" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]] ||
 { echo "STAGE31_FINANCIAL_BASELINE_INVALID";exit 13; }
echo "STAGE31_EXISTING_FINANCIAL_ROW_COUNTS=$BEFORE"
echo "STAGE31_CADDY_BASELINE_SHA256=$CONF_SHA"
echo "STAGE31_DATABASE_CATALOG_ONLY_NO_INVOICE_VALUES=TRUE"

echo "=== B. ACTUAL DATABASE TABLE AND COLUMN CATALOG (NO DATA VALUES) ==="
STEP=CATALOG
sudo -n -u postgres psql -X -A -F '|' -v ON_ERROR_STOP=1 -d "$DB" <<'SQL'
BEGIN READ ONLY;
SET LOCAL statement_timeout='10000ms';
SELECT 'STAGE31_DATABASE',current_database(),current_user,current_setting('server_version'),pg_is_in_recovery();
SELECT 'STAGE31_TABLE',table_name,table_type
FROM information_schema.tables
WHERE table_schema='sbi' ORDER BY table_name;
SELECT 'STAGE31_COLUMN',table_name,ordinal_position,column_name,data_type,is_nullable,COALESCE(character_maximum_length::text,'')
FROM information_schema.columns WHERE table_schema='sbi'
ORDER BY table_name,ordinal_position;
SELECT 'STAGE31_CONSTRAINT',rel.relname, con.conname,con.contype,
  pg_get_constraintdef(con.oid,true)
FROM pg_constraint con JOIN pg_class rel ON rel.oid=con.conrelid
JOIN pg_namespace ns ON ns.oid=rel.relnamespace
WHERE ns.nspname='sbi' ORDER BY rel.relname,con.conname;
SELECT 'STAGE31_INDEX', tablename,indexname,
 CASE WHEN indexdef LIKE 'CREATE UNIQUE INDEX%' THEN 'UNIQUE' ELSE 'NONUNIQUE' END
FROM pg_indexes WHERE schemaname='sbi' ORDER BY tablename,indexname;
SELECT 'STAGE31_ROLE', rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole
FROM pg_roles WHERE rolname IN
  ('sbi_report_reader','sbi_ingest_runtime','sbi_engine_runtime','sbi_pr129_report_login')
ORDER BY rolname;
SELECT 'STAGE31_ROLE_PRIVILEGE',r.rolname,c.relname,
 has_table_privilege(r.rolname,c.oid,'SELECT'),
 has_table_privilege(r.rolname,c.oid,'INSERT'),
 has_table_privilege(r.rolname,c.oid,'UPDATE'),
 has_table_privilege(r.rolname,c.oid,'DELETE')
FROM pg_roles r
JOIN pg_class c ON c.relnamespace='sbi'::regnamespace
WHERE r.rolname IN ('sbi_report_reader','sbi_ingest_runtime','sbi_engine_runtime','sbi_pr129_report_login')
  AND c.relkind IN ('r','v','p')
ORDER BY r.rolname,c.relname;
COMMIT;
SQL
echo "STAGE31_POSTGRESQL_SCHEMA_INTROSPECTION=PASS"

echo "=== C. VERIFY PRODUCTION READ-ONLY AUTH CONTRACT VIA LOCAL CADDY ==="
STEP=AUTH
for request in "login|/login|200" "summary|/api/reporting/v2/postgresql-summary|401" \
 "reports|/api/reporting/v2|401" "bulk_status|/api/bulk-report/status|401"; do
 IFS='|' read -r label path expected <<< "$request"
 code="$(curl --noproxy '*' -4 -sS -o /dev/null --connect-timeout 3 --max-time 8 \
   --resolve "$SITE:443:127.0.0.1" -w '%{http_code}' "https://$SITE$path" || true)"
 echo "STAGE31_AUTH=$label expected:$expected actual:$code"
 [[ "$code" == "$expected" ]] ||
  { echo "STAGE31_LIVE_AUTH_GUARD=FAIL";exit 15; }
done
echo "STAGE31_LIVE_ANONYMOUS_ROUTE_GUARDS=PASS"

echo "=== D. FETCH EXACT APPROVED INVOICE CONTRACT + STRICT PAYMENT PREVIEW QA ==="
STEP=SOURCE
cd "$WORK"
fetch(){
 local path="$1" output="$2" hash="$3"
 curl -4 -fLsS --retry 3 -o "$output" "$BASE/$COMMIT/$path"
 [[ "$(git hash-object "$output")" == "$hash" ]] || {
   echo "STAGE31_SOURCE_HASH_MISMATCH=$output";exit 17; }
}
fetch backend_source/invoice_import_contract.json invoice_import_contract.json 95e166ba8f65ca57ca30d78cd1591bbc63b01c5e
fetch backend_source/invoice_source_schema.py invoice_source_schema.py b70ac295c2f2c63e8662dbe4a596fb05144af1e3
fetch backend_source/invoice_import_rules.py invoice_import_rules.py 2803c1b0d44848b02abe0908b3704d6f35a53703
fetch database/stage31/payment_evidence_contract.py payment_evidence_contract.py a05e53d5d54839fd2b4b122a533946ea46d49479
fetch database/stage31/test_stage31_contracts.py test_stage31_contracts.py d1fdd803540a86c96a9ffd005f8fac8567c6ce8e
python3 -B -m unittest -v test_stage31_contracts.py
echo "STAGE31_APPROVED_INVOICE_34_35_53_AND_PAYMENT_PREVIEW_QA=PASS"

echo "=== E. SAFETY BOUNDARY AND REQUIRED NEXT GATES ==="
STEP=FINAL
echo "STAGE31_INVOICE_HEADERS=EXACT_APPROVED_34_35_53"
echo "STAGE31_PAYMENT_HEADERS=DESCRIPTION_SOL_ID_CREDIT_AMOUNT_EXACT"
echo "STAGE31_PAYMENT_SOURCE_IDENTITY=REVIEW_REQUIRED_FOR_PRODUCTION_IDEMPOTENCY"
echo "STAGE31_DATABASE_WRITER=NOT_CREATED_NOT_DEPLOYED"
echo "STAGE31_FIRESTORE_LEGACY_IMPORT=NOT_CONNECTED_TO_POSTGRES"
echo "STAGE31_NEXT_GATE=REVIEW_LIVE_SCHEMA_AND_DESIGN_ISOLATED_ATOMIC_POSTGRES_INGEST"
STEP=COMPLETE
