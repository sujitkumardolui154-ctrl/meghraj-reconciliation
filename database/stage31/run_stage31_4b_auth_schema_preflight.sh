#!/usr/bin/env bash
# STAGE31.4B - PREDEPLOY combined real source/auth/schema audit + isolated unit
# QA. Read-only access to deployed code; no financial values, cookie or secrets.
# No live app registration, no new public service, no production writer.
set -Eeuo pipefail
umask 077
export PAGER=cat PYTHONDONTWRITEBYTECODE=1
STEP=INIT
DB=sbi_reconciliation_main
LIVE=sbi-pr129-modern-release-final
SITE=pr129.13-232-241-221.sslip.io
CADDY=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
EVID=/home/ubuntu/sbi-release-evidence
WORK=/home/ubuntu/sbi-stage31-private-qa
BASE=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
PIN=842f54085bf069d04b239ffe81bf6bdb6e3ce222
BEFORE=""
CADDY_BEFORE=""
LIVE_BEFORE=""
mkdir -p "$EVID" "$WORK"
chmod 700 "$WORK" "$EVID"
LOG="$EVID/stage31_4b_auth_schema_preflight_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1

count_source(){
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
  after="$(count_source 2>/dev/null || true)"
  if [[ "$BEFORE" == "$after" ]];then
   echo "STAGE31_4B_SOURCE_FINANCIAL_COUNTS_UNCHANGED=PASS"
  else
   echo "STAGE31_4B_SOURCE_FINANCIAL_COUNTS_UNCHANGED=FAIL_OR_UNVERIFIED"
   rc=91
  fi
 fi
 if [[ -n "$CADDY_BEFORE" ]];then
  local h
  h="$(sudo -n sha256sum "$CADDY" 2>/dev/null | awk '{print $1}')"
  if [[ "$h" == "$CADDY_BEFORE" ]];then
   echo "STAGE31_4B_CADDY_UNCHANGED=PASS"
  else
   echo "STAGE31_4B_CADDY_UNCHANGED=FAIL_OR_UNVERIFIED"
   rc=92
  fi
 fi
 if [[ -n "$LIVE_BEFORE" ]];then
  local now
  now="$(timeout 20s sudo -n docker inspect -f '{{.Id}}|{{.Image}}|{{.State.Running}}' "$LIVE" 2>/dev/null || true)"
  if [[ "$now" == "$LIVE_BEFORE" ]];then
   echo "STAGE31_4B_LIVE_PR129_IMAGE_AND_CONTAINER_UNCHANGED=PASS"
  else
   echo "STAGE31_4B_LIVE_PR129_IMAGE_AND_CONTAINER_UNCHANGED=FAIL_OR_UNVERIFIED"
   rc=93
  fi
 fi
 if ((rc));then
  echo "STAGE31_4B_PREDEPLOY_COMBINED_QA=FAIL step:$STEP exit:$rc"
 else
  echo "STAGE31_4B_PREDEPLOY_COMBINED_QA=PASS_INSPECTION_AND_OFFLINE_CONTRACTS_ONLY"
 fi
 echo "STAGE31_4B_REAL_OWNER_AUTHENTICATED_BROWSER_UAT=NOT_PERFORMED"
 echo "STAGE31_4B_REAL_FIREBASE_PRIVATE_UPLOAD_ROUTE=NOT_DEPLOYED"
 echo "STAGE31_4B_REAL_CSRF_OWNER_UPLOAD=NOT_PERFORMED"
 echo "STAGE31_4B_POSTGRESQL_FINANCIAL_IMPORT_WRITER=NOT_DEPLOYED"
 echo "STAGE31_4B_PAYMENT_BANK_TRANSACTION_IDENTITY=REVIEW_REQUIRED"
 echo "STAGE31_4B_INVOICE_BRANCH_SOURCE_FK=REVIEW_REQUIRED"
 echo "STAGE31_4B_FINANCIAL_ENGINE=LOCKED"
 echo "STAGE31_4B_PRODUCTION_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE31_4B_NEXT=OWNER_BROWSER_UAT_AND_PRIVATE_STAGING_AUTH_ORIGIN_REVIEW"
 echo "STAGE31_4B_EVIDENCE=$LOG"
 exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=== A. PROTECT RUNNING PR129, CADDY AND CENTRAL FINANCIAL DATA ==="
STEP=BASELINE
[[ "$(id -un)" == ubuntu ]] || { echo "STAGE31_4B_UBUNTU_USER_REQUIRED";exit 10; }
BEFORE="$(count_source)"
[[ "$BEFORE" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]] || exit 11
echo "STAGE31_4B_SOURCE_FINANCIAL_COUNTS_BEFORE=$BEFORE"
CADDY_BEFORE="$(sudo -n sha256sum "$CADDY" | awk '{print $1}')"
LIVE_BEFORE="$(timeout 20s sudo -n docker inspect -f '{{.Id}}|{{.Image}}|{{.State.Running}}' "$LIVE")"
[[ "$LIVE_BEFORE" == *'|true' ]] || { echo "STAGE31_4B_PR129_NOT_RUNNING";exit 12; }
IMAGE="$(printf '%s\n' "$LIVE_BEFORE" | cut -d '|' -f 2)"
[[ "$IMAGE" == sha256:* ]] || { echo "STAGE31_4B_IMAGE_NOT_PINNED";exit 13; }
echo "STAGE31_4B_LIVE_PROTECTION_BASELINE=PASS"

echo "=== B. VERIFY POSTGRESQL ROLES READ ONLY AND CAPTURE FINANCIAL SCHEMA METADATA ==="
STEP=SCHEMA
ROLE="$(sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "
SELECT CASE WHEN bool_and(
 NOT has_table_privilege('sbi_pr129_report_login',oid,'INSERT')
 AND NOT has_table_privilege('sbi_pr129_report_login',oid,'UPDATE')
 AND NOT has_table_privilege('sbi_pr129_report_login',oid,'DELETE'))
 THEN 'PASS' ELSE 'FAIL' END
FROM pg_class WHERE oid IN (
 'sbi.invoices'::regclass, 'sbi.payments'::regclass,
 'sbi.allocations'::regclass, 'sbi.credit_notes'::regclass);
" | tail -1)"
echo "STAGE31_4B_REPORTING_USER_WRITE_DENIAL=$ROLE"
[[ "$ROLE" == PASS ]] || exit 14
META="$EVID/stage31_4b_schema_metadata_$(date -u +%Y%m%dT%H%M%SZ).txt"
sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" >"$META" <<'SQL'
BEGIN READ ONLY;
SET LOCAL statement_timeout='10000ms';
SELECT 'STAGE31_4B_DATABASE='||current_database();
SELECT 'STAGE31_4B_SBI_TABLE='||table_name
FROM information_schema.tables
WHERE table_schema='sbi' AND table_type='BASE TABLE'
ORDER BY table_name;
SELECT 'STAGE31_4B_TARGET_COLUMN='||table_name||'.'||column_name
 ||' TYPE='||data_type||' NULLABLE='||is_nullable
FROM information_schema.columns
WHERE table_schema='sbi'
 AND table_name IN ('invoices','payments','source_rows',
                   'source_files','import_batches','branches','branch_master')
ORDER BY table_name,ordinal_position;
SELECT 'STAGE31_4B_INVOICE_UNIQUE_INDEX='||indexname||' '||indexdef
FROM pg_indexes
WHERE schemaname='sbi' AND tablename='invoices'
 AND indexdef LIKE 'CREATE UNIQUE INDEX%'
ORDER BY indexname;
SELECT 'STAGE31_4B_SOURCE_FK='||conrelid::regclass||'.'||conname||' '||pg_get_constraintdef(oid)
FROM pg_constraint
WHERE contype='f' AND connamespace='sbi'::regnamespace
 AND conrelid IN ('sbi.invoices'::regclass,'sbi.payments'::regclass)
ORDER BY conrelid::regclass::text,conname;
COMMIT;
SQL
[[ -s "$META" ]] || { echo "STAGE31_4B_SCHEMA_CAPTURE_FAILED";exit 15; }
echo "STAGE31_4B_SCHEMA_ONLY_EVIDENCE=$META"
grep '^STAGE31_4B_' "$META" || true
echo "STAGE31_4B_SCHEMA_METADATA_READ_ONLY=PASS"

echo "=== C. DOWNLOAD GIT-PINNED AUDIT AND PRIVATE AUTH SOURCE ONLY ==="
STEP=SOURCES
cd "$WORK"
fetch(){
 local src="$1" name="$2" sha="$3"
 curl -4 -fLsS --retry 3 -o "$name" "$BASE/$PIN/$src"
 [[ "$(git hash-object "$name")" == "$sha" ]] ||
  { echo "STAGE31_4B_INTEGRITY_MISMATCH=$name";exit 16; }
}
fetch database/stage31/stage31_4b_deployed_auth_inspect.py stage31_4b_deployed_auth_inspect.py ec73fb9da71e862a5b96aa4fcebb85bd107b4051
fetch database/stage31/stage31_4b_runtime_csrf_probe.py stage31_4b_runtime_csrf_probe.py ee6a4981b7a00c7fb03fc376edfc5bc3ad937dfe
fetch database/stage31/stage31_4b_auth_binding_candidate.py stage31_4b_auth_binding_candidate.py 1f8c94460859acf866c497f7e2661c4ba31687c2
fetch database/stage31/test_stage31_4b_auth_binding_candidate.py test_stage31_4b_auth_binding_candidate.py 00567563fb130ab13451b83279ffbfceef453a8d
fetch dashboard_source/dashboard_sessions.py dashboard_sessions.py de5656b33e0b4ff56e82086474c855316162a10e
fetch dashboard_source/sbi_report_access.py sbi_report_access.py b53c005d2b57fdd3a840c7f4d7e3c55654068d46
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
echo "STAGE31_4B_PINNED_SOURCE_INTEGRITY=PASS"

echo "=== D. REAL LIVE CONTAINER AUTH/CSRF/ORIGIN SOURCE INSPECTION (NO COOKIES) ==="
STEP=LIVE_SOURCE
INSPECT="$EVID/stage31_4b_deployed_auth_inspection_$(date -u +%Y%m%dT%H%M%SZ).txt"
timeout --signal=TERM --kill-after=5s 30s sudo -n docker exec -i "$LIVE" \
 python3 -B - < "$WORK/stage31_4b_deployed_auth_inspect.py" >"$INSPECT"
cat "$INSPECT"
grep -Fxq 'STAGE31_4B_SOURCE_INSPECTION=COMPLETE_REVIEW_REQUIRED_BEFORE_PRIVATE_DEPLOYMENT' "$INSPECT" ||
 { echo "STAGE31_4B_DEPLOYED_AUTH_SOURCE_AUDIT_FAILED";exit 22; }
echo "=== D2. REAL DEPLOYED CSRF FUNCTION / SYNTHETIC ORIGIN PROBE (NO SESSION COOKIE) ==="
STEP=CSRF_RUNTIME
CSRF_PROBE="$EVID/stage31_4b_runtime_csrf_$(date -u +%Y%m%dT%H%M%SZ).txt"
timeout --signal=TERM --kill-after=5s 30s sudo -n docker exec -i "$LIVE" \
 python3 -B - < "$WORK/stage31_4b_runtime_csrf_probe.py" >"$CSRF_PROBE"
cat "$CSRF_PROBE"
if grep -Eq '^STAGE31_4B_CSRF_(UNTRUSTED_ORIGIN|MISMATCHED_TOKEN|MISSING_ORIGIN)_DENIED=FAIL

echo "=== E. COMPARE EXISTING ANONYMOUS HTTPS AUTH GATES (NO POST/SESSION) ==="
STEP=HTTPS
for route in 'login|/login|200' \
  'auth_me|/auth/me|401' \
  'postgres_readonly|/api/reporting/v2/postgresql-summary|401' \
  'bulk_status|/api/bulk-report/status|401';do
 IFS='|' read -r label path status <<<"$route"
 code="$(curl --noproxy '*' -4 -sS -o /dev/null \
   --connect-timeout 4 --max-time 12 \
   --resolve "$SITE:443:127.0.0.1" \
   -w '%{http_code}' "https://$SITE$path" || true)"
 echo "STAGE31_4B_ANONYMOUS_HTTPS=$label expected:$status actual:$code"
 [[ "$code" == "$status" ]] || { echo "STAGE31_4B_ANONYMOUS_HTTPS=FAIL";exit 23; }
done
echo "STAGE31_4B_ANONYMOUS_HTTPS=PASS"

echo "=== F. 96 PRIVATE SOURCE AND AUTH CONTRACT REGRESSIONS, ISOLATED ==="
STEP=ISOLATED_TESTS
# 75 previously passing upload-source tests + 21 new ownership+CSRF tests.
# This is NOT a real Firebase ID/session-token validation.
timeout --signal=TERM --kill-after=5s 160s sudo -n docker run --rm \
 --name "sbi-stage31-4b-qa-$$" \
 --network none --read-only \
 --cap-drop ALL --security-opt no-new-privileges \
 --pids-limit 64 --memory 256m --cpus 0.5 \
 --user "$(id -u):$(id -g)" \
 --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --mount "type=bind,src=$WORK,dst=/qa,readonly" \
 --workdir /qa --entrypoint python3 \
 "$IMAGE" -B -m unittest -v \
 test_stage31_contracts.py \
 test_stage31_2_schema_design.py \
 test_stage31_3_ingest_candidate.py \
 test_stage31_4_private_preview.py \
 test_stage31_4b_auth_binding_candidate.py
echo "STAGE31_4B_OFFLINE_FLASK_AUTH_AND_PREVIEW_QA=PASS"
echo "STAGE31_4B_NEW_PREVIEW_CALLBACK=CODE_ONLY_NOT_REGISTERED"

echo "=== G. STATUS: NO PRODUCTION AUTH CHANGE OR WRITE ROLE ==="
STEP=COMPLETE
echo "STAGE31_4B_FINAL_SOURCE_POLICY_AUDIT=PASS_INSPECTION_NOT_AUTHENTICATED_E2E"
echo "STAGE31_4B_PRIVATE_PREVIEW_ROLE=PROPOSED_NOT_GRANTED"
echo "STAGE31_4B_PRIVATE_ENDPOINT_ACTIVATION=BLOCKED_UNTIL_OWNER_REVIEW"
 "$CSRF_PROBE";then
 echo "STAGE31_4B_CSRF_NEGATIVE_CONTROLS=FAIL"
 exit 24
fi
if grep -Fxq 'STAGE31_4B_CSRF_ORIGIN_RUNTIME=PASS_SYNTHETIC_PRODUCTION_ORIGIN' "$CSRF_PROBE";then
 echo "STAGE31_4B_LIVE_ORIGIN_PREFLIGHT=RUNTIME_SYNTHETIC_CSRF_PASS_BROWSER_POST_STILL_PENDING"
else
 echo "STAGE31_4B_LIVE_ORIGIN_PREFLIGHT=REVIEW_REQUIRED_NO_PRIVATE_ROUTE_DEPLOYMENT"
fi
echo "STAGE31_4B_RUNTIME_CSRF_SOURCE_PROBE=COMPLETE_NO_REAL_FIREBASE_TOKENS"

echo "=== E. COMPARE EXISTING ANONYMOUS HTTPS AUTH GATES (NO POST/SESSION) ==="
STEP=HTTPS
for route in 'login|/login|200' \
  'auth_me|/auth/me|401' \
  'postgres_readonly|/api/reporting/v2/postgresql-summary|401' \
  'bulk_status|/api/bulk-report/status|401';do
 IFS='|' read -r label path status <<<"$route"
 code="$(curl --noproxy '*' -4 -sS -o /dev/null \
   --connect-timeout 4 --max-time 12 \
   --resolve "$SITE:443:127.0.0.1" \
   -w '%{http_code}' "https://$SITE$path" || true)"
 echo "STAGE31_4B_ANONYMOUS_HTTPS=$label expected:$status actual:$code"
 [[ "$code" == "$status" ]] || { echo "STAGE31_4B_ANONYMOUS_HTTPS=FAIL";exit 23; }
done
echo "STAGE31_4B_ANONYMOUS_HTTPS=PASS"

echo "=== F. 96 PRIVATE SOURCE AND AUTH CONTRACT REGRESSIONS, ISOLATED ==="
STEP=ISOLATED_TESTS
# 75 previously passing upload-source tests + 21 new ownership+CSRF tests.
# This is NOT a real Firebase ID/session-token validation.
timeout --signal=TERM --kill-after=5s 160s sudo -n docker run --rm \
 --name "sbi-stage31-4b-qa-$$" \
 --network none --read-only \
 --cap-drop ALL --security-opt no-new-privileges \
 --pids-limit 64 --memory 256m --cpus 0.5 \
 --user "$(id -u):$(id -g)" \
 --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --mount "type=bind,src=$WORK,dst=/qa,readonly" \
 --workdir /qa --entrypoint python3 \
 "$IMAGE" -B -m unittest -v \
 test_stage31_contracts.py \
 test_stage31_2_schema_design.py \
 test_stage31_3_ingest_candidate.py \
 test_stage31_4_private_preview.py \
 test_stage31_4b_auth_binding_candidate.py
echo "STAGE31_4B_OFFLINE_FLASK_AUTH_AND_PREVIEW_QA=PASS"
echo "STAGE31_4B_NEW_PREVIEW_CALLBACK=CODE_ONLY_NOT_REGISTERED"

echo "=== G. STATUS: NO PRODUCTION AUTH CHANGE OR WRITE ROLE ==="
STEP=COMPLETE
echo "STAGE31_4B_FINAL_SOURCE_POLICY_AUDIT=PASS_INSPECTION_NOT_AUTHENTICATED_E2E"
echo "STAGE31_4B_PRIVATE_PREVIEW_ROLE=PROPOSED_NOT_GRANTED"
echo "STAGE31_4B_PRIVATE_ENDPOINT_ACTIVATION=BLOCKED_UNTIL_OWNER_REVIEW"
