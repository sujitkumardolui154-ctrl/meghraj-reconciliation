#!/usr/bin/env bash
# Stage 31.4 PRIVATE candidate QA: real isolated Flask test-client and
# Excel source parsers, with synthetic auth/CSRF. NO PR129 route deployment.
# NO financial writes, grants, import APIs, schema DDL or production changes.
set -Eeuo pipefail
umask 077
export PAGER=cat PYTHONDONTWRITEBYTECODE=1
STEP=INIT
DB=sbi_reconciliation_main
SITE=pr129.13-232-241-221.sslip.io
CADDY=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
WORK=/home/ubuntu/sbi-stage31-private-qa
EVID=/home/ubuntu/sbi-release-evidence
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
PIN=e4b8ba918fd1fec307bbe92e876b1eda4ee636d1
LIVE_CONTAINER=sbi-pr129-modern-release-final
IMAGE=""
mkdir -p "$WORK" "$EVID"
chmod 700 "$WORK" "$EVID"
LOG="$EVID/stage31_4_private_integration_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1
BEFORE=""
CADDY_BEFORE=""
LIVE_BEFORE=""
counts(){
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c \
 "BEGIN READ ONLY; SET LOCAL statement_timeout='10000ms';
 SELECT (SELECT count(*) FROM sbi.invoices),
        (SELECT count(*) FROM sbi.payments),
        (SELECT count(*) FROM sbi.allocations),
        (SELECT count(*) FROM sbi.credit_notes);
 COMMIT;" | grep -E '^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$' | tail -1
}
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$BEFORE" ]];then
   local after
   after="$(counts 2>/dev/null || true)"
   if [[ "$BEFORE" == "$after" ]];then
     echo "STAGE31_4_FINANCIAL_RECORD_COUNTS_UNCHANGED=PASS"
   else
     echo "STAGE31_4_FINANCIAL_RECORD_COUNTS_UNCHANGED=FAIL_OR_UNVERIFIED"
     rc=91
   fi
 fi
 if [[ -n "$CADDY_BEFORE" ]];then
   local h
   h="$(sudo -n sha256sum "$CADDY" 2>/dev/null | awk '{print $1}')"
   if [[ "$h" == "$CADDY_BEFORE" ]];then
     echo "STAGE31_4_PRODUCTION_CADDY_UNCHANGED=PASS"
   else
     echo "STAGE31_4_PRODUCTION_CADDY_UNCHANGED=FAIL_OR_UNVERIFIED"
     rc=92
   fi
 fi
 if [[ -n "$LIVE_BEFORE" ]];then
   local current
   current="$(timeout 15s sudo -n docker inspect -f '{{.Id}}|{{.Image}}|{{.State.Running}}' sbi-pr129-modern-release-final 2>/dev/null || true)"
   if [[ "$current" == "$LIVE_BEFORE" ]];then
     echo "STAGE31_4_LIVE_CONTAINER_UNCHANGED=PASS"
   else
     echo "STAGE31_4_LIVE_CONTAINER_UNCHANGED=FAIL_OR_UNVERIFIED"
     rc=93
   fi
 fi
 if ((rc));then
   echo "STAGE31_4_PRIVATE_COMBINED_QA=FAIL step:$STEP exit:$rc"
 else
   echo "STAGE31_4_PRIVATE_COMBINED_QA=PASS_OFFLINE_SYNTHETIC_ONLY"
 fi
 echo "STAGE31_4_REAL_FIREBASE_CALLBACK_BINDING=NOT_PERFORMED"
 echo "STAGE31_4_REAL_AUTHENTICATED_USER_BROWSER_QA=NOT_PERFORMED"
 echo "STAGE31_4_POSTGRESQL_INGEST_WRITER=NOT_DEPLOYED"
 echo "STAGE31_4_ORIGINAL_BANK_ROW_IDENTITY=REVIEW_REQUIRED"
 echo "STAGE31_4_SOURCE_ROW_FK_AND_BRANCH_MAPPING=REVIEW_REQUIRED"
 echo "STAGE31_4_FINANCIAL_ENGINE=LOCKED"
 echo "STAGE31_4_PRODUCTION_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE31_4_NEXT_GATE=VERIFY_REAL_FIREBASE_CALLBACK_AND_APPROVE_SOURCE_MAPPING_IN_PRIVATE_ENV"
 echo "STAGE31_4_LOG=$LOG"
 exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=== A. LIVE PR129 AND CENTRAL POSTGRESQL IMMUTABLE BASELINE ==="
STEP=BASELINE
[[ "$(id -un)" == ubuntu ]] || { echo "STAGE31_4_UBUNTU_USER_REQUIRED";exit 10; }
BEFORE="$(counts)"
[[ "$BEFORE" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]] || exit 11
echo "STAGE31_4_FINANCIAL_COUNTS_BEFORE=$BEFORE"
CADDY_BEFORE="$(sudo -n sha256sum "$CADDY" | awk '{print $1}')"
LIVE_BEFORE="$(timeout 15s sudo -n docker inspect -f '{{.Id}}|{{.Image}}|{{.State.Running}}' "$LIVE_CONTAINER")"
[[ "$LIVE_BEFORE" == *'|true' ]] || { echo "STAGE31_4_LIVE_PR129_NOT_RUNNING";exit 12; }
IMAGE="$(printf '%s\n' "$LIVE_BEFORE" | cut -d '|' -f 2)"
[[ "$IMAGE" == sha256:* ]] || { echo "STAGE31_4_RELEASE_IMAGE_DIGEST_NOT_VERIFIED";exit 12; }
echo "STAGE31_4_TEST_IMAGE_PINNED_TO_RUNNING_RELEASE=PASS"
echo "STAGE31_4_EXISTING_RELEASE_BASELINE=PASS"

echo "=== B. PRODUCTION REPORTING ROLE CAN NEVER WRITE FINANCIAL TABLES ==="
STEP=PRIVILEGE
ROLE="$(sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "
SELECT CASE WHEN bool_and(
  NOT has_table_privilege('sbi_pr129_report_login',oid,'INSERT')
  AND NOT has_table_privilege('sbi_pr129_report_login',oid,'UPDATE')
  AND NOT has_table_privilege('sbi_pr129_report_login',oid,'DELETE'))
THEN 'PASS' ELSE 'FAIL' END
FROM pg_class WHERE oid IN (
 'sbi.invoices'::regclass,'sbi.payments'::regclass,
 'sbi.allocations'::regclass,'sbi.credit_notes'::regclass);
" | tail -1)"
echo "STAGE31_4_REPORT_ROLE_FINANCIAL_WRITE_DENIAL=$ROLE"
[[ "$ROLE" == PASS ]] || exit 13

echo "=== C. BOUNDED LIVE ANONYMOUS AUTH CONTRACT ==="
STEP=ROUTES
for spec in "login|/login|200" "summary|/api/reporting/v2/postgresql-summary|401" \
            "bulk|/api/bulk-report/status|401"; do
 IFS='|' read -r label url expected <<<"$spec"
 code="$(curl --noproxy '*' -4 -sS -o /dev/null \
   --connect-timeout 3 --max-time 8 --resolve "$SITE:443:127.0.0.1" \
   -w '%{http_code}' "https://$SITE$url" || true)"
 echo "STAGE31_4_LIVE_ROUTE=$label expected:$expected actual:$code"
 [[ "$code" == "$expected" ]] || { echo "STAGE31_4_LIVE_AUTH_GUARDS=FAIL";exit 14; }
done
echo "STAGE31_4_LIVE_AUTH_GUARDS=PASS"

echo "=== D. REPRODUCIBLE PRIVATE CODE (NO AWS SOURCE, PASSWORDS OR DATA ROWS) ==="
STEP=SOURCE
cd "$WORK"
fetch(){
 local src="$1" out="$2" sha="$3"
 curl -4 -fLsS --retry 3 -o "$out" "$BASE/$PIN/$src"
 [[ "$(git hash-object "$out")" == "$sha" ]] ||
   { echo "STAGE31_4_SOURCE_HASH_MISMATCH=$out";exit 16; }
}
fetch backend_source/invoice_import_contract.json invoice_import_contract.json 95e166ba8f65ca57ca30d78cd1591bbc63b01c5e
fetch backend_source/invoice_source_schema.py invoice_source_schema.py b70ac295c2f2c63e8662dbe4a596fb05144af1e3
fetch backend_source/invoice_import_rules.py invoice_import_rules.py 2803c1b0d44848b02abe0908b3704d6f35a53703
fetch backend_source/upload_api.py upload_api.py ff47c644acecba98d527b67d490ee94761642e1d
fetch backend_source/invoice_excel_parser.py invoice_excel_parser.py 38927c0b1ea793a47b649c14101caa0175663a5d
fetch backend_source/invoice_import_preview.py invoice_import_preview.py 22af119657dcc6e98eb1bec02ce16b3eba6978ac
fetch database/stage31/payment_evidence_contract.py payment_evidence_contract.py a05e53d5d54839fd2b4b122a533946ea46d49479
fetch database/stage31/test_stage31_contracts.py test_stage31_contracts.py d1fdd803540a86c96a9ffd005f8fac8567c6ce8e
fetch database/stage31/stage31_2_schema_design.py stage31_2_schema_design.py 4eabfdcfa31a921504bc7a4999ff747557207c9d
fetch database/stage31/test_stage31_2_schema_design.py test_stage31_2_schema_design.py ea05ffc4c30b4bfca2b3425fc44f22a28978b629
fetch database/stage31/stage31_3_ingest_candidate.py stage31_3_ingest_candidate.py 23ed83c9515b5f00b3848594272adeeda0f3ee6c
fetch database/stage31/test_stage31_3_ingest_candidate.py test_stage31_3_ingest_candidate.py 9e66d957f956841c758bb7cf90bae5108539bda3
fetch database/stage31/stage31_4_private_preview.py stage31_4_private_preview.py df16907e24e751b3c6cd3136de8aecd934397e03
fetch database/stage31/test_stage31_4_private_preview.py test_stage31_4_private_preview.py 1c60abd1469323b335836daf3b24d3e1f236fc90
echo "STAGE31_4_PINNED_SOURCE_HASH_QA=PASS"

echo "=== E. RUN PRIVATE 75-TEST SOURCE/FLASK/CSRF/EXCEL COMBINED QA ==="
STEP=TESTS
# Single isolated short-lived container, no network, no database credentials,
# no AWS routing change; bind-mounted sources read-only; actual live
# container remains unmodified. No public port exposed.
timeout --signal=TERM --kill-after=5s 150s sudo -n docker run --rm \
  --name "sbi-stage31-4-test-$$" \
  --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --memory 256m --cpus 0.5 \
  --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --mount "type=bind,src=$WORK,dst=/qa,readonly" \
  --workdir /qa \
  --entrypoint python3 \
  "$IMAGE" -B -m unittest -v \
    test_stage31_contracts.py \
    test_stage31_2_schema_design.py \
    test_stage31_3_ingest_candidate.py \
    test_stage31_4_private_preview.py
echo "STAGE31_4_FLASK_TEST_CLIENT_AUTH_CSRF_EXCEL_QA=PASS"
echo "STAGE31_4_OPTIONAL_XLS_READER=NOT_INSTALLED_FAIL_CLOSED_WHEN_UNAVAILABLE"
echo "STAGE31_4_NO_PUBLIC_PRIVATE_ENDPOINT=PASS_NOT_REGISTERED"

echo "=== F. STAGE 31.4 GATES: PRIVATE SYNTHETIC ONLY ==="
STEP=COMPLETE
echo "STAGE31_4_PRIVATE_APPLY_ENDPOINT=LOCKED_423"
echo "STAGE31_4_FIREBASE_PRODUCTION_AUTH=NOT_WIRED"
echo "STAGE31_4_CENTRAL_POSTGRESQL_WRITER=NOT_WIRED"
echo "STAGE31_4_STATUS=OFFLINE_PRIVATE_CANDIDATE_REQUIRES_AUTHENTICATED_UAT_AND_MAPPING"
