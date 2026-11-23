#!/usr/bin/env bash
# Stage 31.2: one combined metadata-only source -> live PostgreSQL crosswalk.
# NEVER import/UPDATE/DELETE/INSERT, grant privileges, deploy, or enable Finance Apply.
set -Eeuo pipefail
umask 077
export PAGER=cat PYTHONDONTWRITEBYTECODE=1
DB=sbi_reconciliation_main
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
REF=322ea8f412b8fc2a9cede22c2b5b192298721b4e
WORK=/home/ubuntu/sbi-stage31-private-qa
DIR=/home/ubuntu/sbi-release-evidence
STEP=INIT
BEFORE=""
CADDY_BEFORE=""
mkdir -p "$WORK" "$DIR"
chmod 700 "$WORK" "$DIR"
LOG="$DIR/stage31_2_ingestion_mapping_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1

counts() {
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c \
  "BEGIN READ ONLY; SET LOCAL statement_timeout='10000ms';
   SELECT (SELECT count(*) FROM sbi.invoices),
          (SELECT count(*) FROM sbi.payments),
          (SELECT count(*) FROM sbi.allocations),
          (SELECT count(*) FROM sbi.credit_notes);
   COMMIT;" | grep -E '^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$' | tail -1
}
finish() {
 local code=$?
 trap - EXIT
 if [[ -n "$BEFORE" ]]; then
   local after
   after="$(counts 2>/dev/null || true)"
   if [[ "$after" == "$BEFORE" ]]; then
      echo "STAGE31_2_FINANCIAL_ROW_COUNTS_UNCHANGED=PASS"
   else
      echo "STAGE31_2_FINANCIAL_ROW_COUNTS_UNCHANGED=FAIL_OR_UNVERIFIED"
      code=92
   fi
 fi
 if [[ -n "$CADDY_BEFORE" ]]; then
   local hash
   hash="$(sudo -n sha256sum /home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile 2>/dev/null | awk '{print $1}')"
   if [[ "$hash" == "$CADDY_BEFORE" ]]; then
      echo "STAGE31_2_LIVE_CADDY_UNCHANGED=PASS"
   else
      echo "STAGE31_2_LIVE_CADDY_UNCHANGED=FAIL_OR_UNVERIFIED"
      code=93
   fi
 fi
 if ((code)); then
  echo "STAGE31_2_COMBINED_READ_ONLY_QA=FAIL step=$STEP exit=$code"
 else
  echo "STAGE31_2_COMBINED_READ_ONLY_QA=PASS"
 fi
 echo "STAGE31_2_POSTGRES_PRODUCTION_WRITER=NOT_INSTALLED"
 echo "STAGE31_2_PRODUCTION_FINANCIAL_WRITES=NONE"
 echo "STAGE31_2_FINANCIAL_ENGINE=UNCHANGED_LOCKED"
 echo "STAGE31_2_OWNER_APPROVAL_FOR_DB_WRITES=NOT_REQUESTED_NOT_GRANTED"
 echo "STAGE31_2_LOG=$LOG"
 exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=== A. ONE CENTRAL POSTGRESQL READ-ONLY BASELINE ==="
STEP=BASELINE
[[ "$(id -un)" == ubuntu ]] || { echo "STAGE31_2_USER_UBUNTU_REQUIRED";exit 10; }
BEFORE="$(counts)"
[[ "$BEFORE" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]] || exit 11
echo "STAGE31_2_FINANCIAL_COUNTS_BEFORE=$BEFORE"
CADDY_BEFORE="$(sudo -n sha256sum /home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile | awk '{print $1}')"

echo "=== B. LIVE POSTGRESQL TABLE/COLUMN/INDEX METADATA ONLY (NO RECORD VALUES) ==="
STEP=CATALOG
CATALOG="$DIR/stage31_2_postgres_catalog_$(date -u +%Y%m%dT%H%M%SZ).json"
sudo -n -u postgres psql -X -A -t -q -v ON_ERROR_STOP=1 -d "$DB" > "$CATALOG" <<'SQL'
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10000ms';
SELECT jsonb_build_object(
 'database',current_database(),
 'tables',COALESCE(
    (SELECT jsonb_object_agg(table_name, cols)
     FROM (SELECT table_name,
             jsonb_agg(jsonb_build_object(
                'name',column_name,'data_type',data_type,'nullable',is_nullable
             ) ORDER BY ordinal_position) AS cols
           FROM information_schema.columns
           WHERE table_schema='sbi' GROUP BY table_name) t),
    '{}'::jsonb),
 'indexes',COALESCE(
    (SELECT jsonb_agg(jsonb_build_object(
       'table',tablename,
       'index',indexname,
       'unique', left(indexdef,19)='CREATE UNIQUE INDEX',
       'definition',indexdef
    ) ORDER BY tablename,indexname)
     FROM pg_indexes WHERE schemaname='sbi'),
    '[]'::jsonb)
)::text;
COMMIT;
SQL
python3 -B -c 'import json,sys; f=sys.argv[1]; x=json.loads(open(f).read()); assert x["database"]=="sbi_reconciliation_main"; assert all(t in x["tables"] for t in ("invoices","payments")); print("STAGE31_2_LIVE_DATABASE_CATALOG=PASS")' "$CATALOG"
echo "STAGE31_2_CATALOG_PATH=$CATALOG"

echo "=== C. CONFIRM LIVE REPORT LOGIN WRITE-DENIAL ==="
STEP=ROLE_GUARD
ROLE="$(sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "
SELECT CASE WHEN bool_and(
   NOT has_table_privilege('sbi_pr129_report_login',oid,'INSERT')
   AND NOT has_table_privilege('sbi_pr129_report_login',oid,'UPDATE')
   AND NOT has_table_privilege('sbi_pr129_report_login',oid,'DELETE'))
 THEN 'PASS' ELSE 'FAIL' END
 FROM pg_class
 WHERE oid IN (
  'sbi.invoices'::regclass,'sbi.payments'::regclass,
  'sbi.allocations'::regclass,'sbi.credit_notes'::regclass);
" | tail -1)"
echo "STAGE31_2_PRODUCTION_REPORT_ROLE_WRITE_DENIED=$ROLE"
[[ "$ROLE" == PASS ]] || exit 12

echo "=== D. FETCH PINNED SOURCE RULES AND 29 COMBINED TESTS ==="
STEP=SOURCE
cd "$WORK"
fetch(){
 local path="$1" out="$2" sha="$3"
 curl -4 -fLsS --retry 3 -o "$out" "$BASE/$REF/$path"
 [[ "$(git hash-object "$out")" == "$sha" ]] || {
   echo "STAGE31_2_HASH_MISMATCH=$out";exit 16; }
}
fetch backend_source/invoice_import_contract.json invoice_import_contract.json 95e166ba8f65ca57ca30d78cd1591bbc63b01c5e
fetch backend_source/invoice_source_schema.py invoice_source_schema.py b70ac295c2f2c63e8662dbe4a596fb05144af1e3
fetch backend_source/invoice_import_rules.py invoice_import_rules.py 2803c1b0d44848b02abe0908b3704d6f35a53703
fetch database/stage31/payment_evidence_contract.py payment_evidence_contract.py a05e53d5d54839fd2b4b122a533946ea46d49479
fetch database/stage31/test_stage31_contracts.py test_stage31_contracts.py d1fdd803540a86c96a9ffd005f8fac8567c6ce8e
fetch database/stage31/stage31_2_schema_design.py stage31_2_schema_design.py 4eabfdcfa31a921504bc7a4999ff747557207c9d
fetch database/stage31/test_stage31_2_schema_design.py test_stage31_2_schema_design.py ea05ffc4c30b4bfca2b3425fc44f22a28978b629
python3 -B -m unittest -v test_stage31_contracts.py test_stage31_2_schema_design.py
echo "STAGE31_2_OFFLINE_SOURCE_AND_MAPPING_REGRESSION=PASS"

echo "=== E. GENERATE REVIEW-ONLY EXPLICIT SOURCE TO DATABASE FIELD CROSSWALK ==="
STEP=MAPPING
MAPPING="$DIR/stage31_2_mapping_REVIEW_REQUIRED_$(date -u +%Y%m%dT%H%M%SZ).json"
python3 -B - "$CATALOG" "$MAPPING" <<'PY'
import sys,json
from pathlib import Path
from stage31_2_schema_design import catalog_to_mapping,render_summary,assert_safe_report
source=Path(sys.argv[1]); dest=Path(sys.argv[2])
catalog=json.loads(source.read_text())
mapping=catalog_to_mapping(catalog)
assert assert_safe_report(mapping)
dest.write_text(json.dumps(mapping,indent=2,sort_keys=True)+"\n")
dest.chmod(0o600)
print(render_summary(mapping))
print("STAGE31_2_MAPPING_PATH="+str(dest))
print("STAGE31_2_MAPPING_CONTAINS_ONLY_CATALOG_NO_FINANCIAL_RECORDS=PASS")
PY

echo "=== F. FINAL STAGE 31.2 SECURITY BOUNDARY ==="
STEP=COMPLETE
echo "STAGE31_2_NEXT_GATE=OWNER_REVIEW_MAPPING_THEN_ISOLATED_POSTGRESQL_TRANSACTIONAL_ADAPTER_QA"
echo "STAGE31_2_LEGACY_FIRESTORE_IMPORT=NOT_SWITCHED_TO_POSTGRESQL"
echo "STAGE31_2_WRITER_ENABLEMENT=BLOCKED_SEPARATE_APPROVAL_REQUIRED"
