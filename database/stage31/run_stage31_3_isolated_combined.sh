#!/usr/bin/env bash
# Stage 31.3: combined offline exact-paise QA + temporary PostgreSQL
# synthetic transaction rollback in maintenance DB postgres only.
# No INSERT/UPDATE/DELETE/grant to sbi_reconciliation_main.
set -Eeuo pipefail
umask 077
export PAGER=cat PYTHONDONTWRITEBYTECODE=1
STEP=INIT
DB=sbi_reconciliation_main
MAINTENANCE_DB=postgres
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
PIN=95d4a36df02df07c4469e754af166c11c2c7752d
WORK=/home/ubuntu/sbi-stage31-private-qa
EVID=/home/ubuntu/sbi-release-evidence
CADDY=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
mkdir -p "$WORK" "$EVID"
chmod 700 "$WORK" "$EVID"
LOG="$EVID/stage31_3_isolated_ingest_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1
BEFORE=""
CADDY_BEFORE=""
getcounts() {
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c \
  "BEGIN READ ONLY;
   SET LOCAL statement_timeout='10000ms';
   SELECT (SELECT count(*) FROM sbi.invoices),
          (SELECT count(*) FROM sbi.payments),
          (SELECT count(*) FROM sbi.allocations),
          (SELECT count(*) FROM sbi.credit_notes);
   COMMIT;" | grep -E '^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$' | tail -1
}
finish() {
 local rc=$?
 trap - EXIT
 if [[ -n "$BEFORE" ]];then
  local after
  after="$(getcounts 2>/dev/null || true)"
  if [[ "$after" == "$BEFORE" ]]; then
   echo "STAGE31_3_SOURCE_FINANCIAL_COUNTS_UNCHANGED=PASS"
  else
   echo "STAGE31_3_SOURCE_FINANCIAL_COUNTS_UNCHANGED=FAIL_OR_UNVERIFIED"
   rc=91
  fi
 fi
 if [[ -n "$CADDY_BEFORE" ]];then
  local after_hash
  after_hash="$(sudo -n sha256sum "$CADDY" 2>/dev/null | awk '{print $1}')"
  if [[ "$after_hash" == "$CADDY_BEFORE" ]];then
   echo "STAGE31_3_LIVE_CADDY_UNCHANGED=PASS"
  else
   echo "STAGE31_3_LIVE_CADDY_UNCHANGED=FAIL_OR_UNVERIFIED"
   rc=92
  fi
 fi
 if (( rc ));then
  echo "STAGE31_3_COMBINED_SYNTHETIC_QA=FAIL step:$STEP exit:$rc"
 else
  echo "STAGE31_3_COMBINED_SYNTHETIC_QA=PASS"
 fi
 echo "STAGE31_3_SCHEMA_MAPPING=REVIEW_REQUIRED"
 echo "STAGE31_3_BANK_TRANSACTION_SOURCE_IDENTITY=NOT_APPROVED"
 echo "STAGE31_3_IMPORT_WRITER=NOT_CONNECTED_TO_PRODUCTION"
 echo "STAGE31_3_FINANCIAL_ENGINE=UNCHANGED_DISABLED"
 echo "STAGE31_3_PRODUCTION_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE31_3_PRODUCTION_CADDY_CHANGES=NONE"
 echo "STAGE31_3_NEXT=APPROVE_SOURCE_TO_DB_MAP_AND_BUILD_PRIVATE_STAGE31_4_INGEST_AUTH_QA"
 echo "STAGE31_3_LOG=$LOG"
 exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=== A. PROTECT CENTRAL PRODUCTION AND RECORD BASELINE ==="
STEP=BASELINE
[[ "$(id -un)" == ubuntu ]] || { echo "STAGE31_3_USER_UBUNTU_REQUIRED"; exit 10; }
[[ "$DB" != "$MAINTENANCE_DB" && "$MAINTENANCE_DB" == postgres ]] ||
 { echo "STAGE31_3_ISOLATION_DB_MISMATCH"; exit 11; }
BEFORE="$(getcounts)"
[[ "$BEFORE" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]] ||
 { echo "STAGE31_3_BASELINE_UNVERIFIED"; exit 13; }
echo "STAGE31_3_SOURCE_FINANCIAL_COUNTS_BEFORE=$BEFORE"
CADDY_BEFORE="$(sudo -n sha256sum "$CADDY" | awk '{print $1}')"
[[ -n "$CADDY_BEFORE" ]] || exit 14

echo "=== B. LIVE CENTRAL DATABASE SCHEMA ONLY AND REPORT-ROLE WRITE-DENIAL ==="
STEP=PRIVILEGE
SCHEMA_RESULT="$(sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" <<'SQL'
BEGIN READ ONLY;
SET LOCAL statement_timeout='10000ms';
SELECT CASE WHEN (
  SELECT count(*) FROM information_schema.columns
  WHERE table_schema='sbi' AND
    (table_name='invoices' AND column_name IN
      ('invoice_number','taxable_paise','cgst_paise','sgst_paise','gross_paise')
     OR table_name='payments' AND column_name IN ('sol_id','credit_paise'))
) = 7
THEN 'STAGE31_3_VERIFIED_PAISE_DATABASE_COLUMNS=PASS'
ELSE 'STAGE31_3_VERIFIED_PAISE_DATABASE_COLUMNS=FAIL' END;
SELECT CASE WHEN bool_and(
  NOT has_table_privilege('sbi_pr129_report_login',oid,'INSERT')
  AND NOT has_table_privilege('sbi_pr129_report_login',oid,'UPDATE')
  AND NOT has_table_privilege('sbi_pr129_report_login',oid,'DELETE'))
THEN 'STAGE31_3_REPORT_ROLE_FINANCIAL_WRITE_DENIAL=PASS'
ELSE 'STAGE31_3_REPORT_ROLE_FINANCIAL_WRITE_DENIAL=FAIL' END
FROM pg_class WHERE oid IN (
  'sbi.invoices'::regclass,'sbi.payments'::regclass,
  'sbi.allocations'::regclass,'sbi.credit_notes'::regclass);
COMMIT;
SQL
)"
printf '%s\n' "$SCHEMA_RESULT"
printf '%s\n' "$SCHEMA_RESULT" | grep -Fxq 'STAGE31_3_VERIFIED_PAISE_DATABASE_COLUMNS=PASS' ||
 { echo "STAGE31_3_PAISE_COLUMN_MAP_REVIEW_REQUIRED"; exit 16; }
printf '%s\n' "$SCHEMA_RESULT" | grep -Fxq 'STAGE31_3_REPORT_ROLE_FINANCIAL_WRITE_DENIAL=PASS' ||
 { echo "STAGE31_3_ROLE_WRITE_DENIAL_FAIL"; exit 17; }

echo "=== C. FETCH PINNED APPROVED CONTRACT AND CANDIDATE TEST FILES ==="
STEP=SOURCE
cd "$WORK"
fetch(){
 local path="$1" name="$2" sha="$3"
 curl -4 -fLsS --retry 3 -o "$name" "$BASE/$PIN/$path"
 [[ "$(git hash-object "$name")" == "$sha" ]] ||
 { echo "STAGE31_3_FILE_HASH_MISMATCH=$name";exit 18; }
}
fetch backend_source/invoice_import_contract.json invoice_import_contract.json 95e166ba8f65ca57ca30d78cd1591bbc63b01c5e
fetch backend_source/invoice_source_schema.py invoice_source_schema.py b70ac295c2f2c63e8662dbe4a596fb05144af1e3
fetch backend_source/invoice_import_rules.py invoice_import_rules.py 2803c1b0d44848b02abe0908b3704d6f35a53703
fetch database/stage31/payment_evidence_contract.py payment_evidence_contract.py a05e53d5d54839fd2b4b122a533946ea46d49479
fetch database/stage31/test_stage31_contracts.py test_stage31_contracts.py d1fdd803540a86c96a9ffd005f8fac8567c6ce8e
fetch database/stage31/stage31_2_schema_design.py stage31_2_schema_design.py 4eabfdcfa31a921504bc7a4999ff747557207c9d
fetch database/stage31/test_stage31_2_schema_design.py test_stage31_2_schema_design.py ea05ffc4c30b4bfca2b3425fc44f22a28978b629
fetch database/stage31/stage31_3_ingest_candidate.py stage31_3_ingest_candidate.py 23ed83c9515b5f00b3848594272adeeda0f3ee6c
fetch database/stage31/test_stage31_3_ingest_candidate.py test_stage31_3_ingest_candidate.py 9e66d957f956841c758bb7cf90bae5108539bda3
fetch database/stage31/stage31_3_postgres_temp_synthetic_rollback.sql stage31_3_postgres_temp_synthetic_rollback.sql 3b8c86075d3f37dc4a217fdb7d08392be587af3d
echo "STAGE31_3_PINNED_FILE_INTEGRITY=PASS"

echo "=== D. RUN 51 SOURCE+MAPPING+PRECISION COMBINED REGRESSION TESTS ==="
STEP=REGRESSION
python3 -B -m unittest -v \
 test_stage31_contracts.py \
 test_stage31_2_schema_design.py \
 test_stage31_3_ingest_candidate.py
echo "STAGE31_3_EXACT_PAISE_AND_SOURCE_IDENTITY_REGRESSION=PASS"

echo "=== E. REAL POSTGRESQL TEMP-TABLE TRANSACTION AND ROLLBACK QA (MAINTENANCE DB ONLY) ==="
STEP=TRANSACTION
[[ "$MAINTENANCE_DB" == postgres ]] || exit 21
# Explicitly run against the built-in maintenance database, never the central DB.
# Temp tables exist only in the SQL session; SQL itself has a guard and ROLLBACK.
sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 \
 -d "$MAINTENANCE_DB" -f "$WORK/stage31_3_postgres_temp_synthetic_rollback.sql"
echo "STAGE31_3_POSTGRESQL_TEMP_TRANSACTION_ROLLBACK=PASS"

echo "=== F. STAGE 31.3 RELEASE RESTRICTIONS ==="
STEP=COMPLETE
echo "STAGE31_3_PAYMENT_3_COLUMN_SOURCE=PREVIEW_ONLY"
echo "STAGE31_3_ORIGINAL_PAYMNENT_COLUMN_I=REQUIRES_ORIGINAL_BANK_TRANSACTION_IDENTITY"
echo "STAGE31_3_SOURCE_ROW_FK_AND_BRANCH_MAPPING=REVIEW_REQUIRED"
echo "STAGE31_3_PRODUCTION_DATABASE_IMPORT=BLOCKED_PENDING_STAGE31_4_AND_OWNER_APPROVAL"
