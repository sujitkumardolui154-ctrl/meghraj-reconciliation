#!/usr/bin/env bash
# Stage 30 preflight only. Inspect the Stage26r2->live PR129 cutover pathway,
# read-only. NEVER edit Caddy, connect Docker networks, stop/restart containers,
# use production credentials interactively, approve release, or touch financial rows.
set -Eeuo pipefail
umask 077

STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
CANDIDATE=sbi-pr129-pg-modernui-stage26r2
STAGE25=sbi-pr129-pg-stage25-firebase-adc
CADDY=aws_lightsail-caddy-1
DB=sbi_reconciliation_main
EVIDENCE_DIR=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"
FILE="$EVIDENCE_DIR/stage30_preflight_$(date -u +%Y%m%dT%H%M%SZ).txt"
exec > >(tee "$FILE") 2>&1
finish(){
  local rc=$?
  trap - EXIT
  if ((rc));then
    echo "STAGE30_PREFLIGHT_QA=FAIL step=$STEP exit=$rc"
  else
    echo "STAGE30_PREFLIGHT_QA=PASS_READ_ONLY"
  fi
  echo "STAGE30_OWNER_APPROVAL=NOT_GIVEN"
  echo "STAGE30_PRODUCTION_CUTOVER=NOT_PERFORMED"
  echo "STAGE30_FINANCIAL_WRITES=NONE"
  echo "STAGE30_EVIDENCE_PATH=$FILE"
  exit "$rc"
}
trap finish EXIT
sql(){
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"
}
counts(){
 sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}

echo "=== A. SNAPSHOT ALL RUNNING SERVICES AND DATABASE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for container in "$LIVE" "$STAGE25" "$CANDIDATE" "$CADDY";do
 [[ "$(sudo -n docker inspect "$container" --format '{{.State.Running}}')" == true ]] ||
   { echo "STAGE30_REQUIRED_CONTAINER_DOWN=$container";exit 11; }
done
B_LIVE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_STAGE25="$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_CAND="$(sudo -n docker inspect "$CANDIDATE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_CADDY="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_FIN="$(counts)"
[[ -z "$(sudo -n docker port "$CANDIDATE")" ]]
echo "STAGE30_CURRENT_LIVE_AND_PRIVATE_CANDIDATE=RUNNING"
echo "STAGE30_PUBLIC_CANDIDATE_PORTS=NONE"

echo "=== B. REGISTER IMMUTABLE RELEASE/ROLLBACK IMAGE IDENTITIES ==="
STEP=IMAGE
OLD_IMAGE="$(sudo -n docker inspect "$LIVE" --format '{{.Image}}')"
NEW_IMAGE="$(sudo -n docker inspect "$CANDIDATE" --format '{{.Image}}')"
sudo -n docker image inspect "$OLD_IMAGE" "$NEW_IMAGE" >/dev/null
echo "STAGE30_REVERT_IMAGE_AVAILABLE=PASS"
echo "STAGE30_CANDIDATE_IMAGE_AVAILABLE=PASS"
echo "STAGE30_ROLLBACK_IMAGE_ID=$OLD_IMAGE"
echo "STAGE30_RELEASE_IMAGE_ID=$NEW_IMAGE"
echo "STAGE30_CURRENT_LIVE_CONTAINER=$LIVE"
echo "STAGE30_PRIVATE_CANDIDATE=$CANDIDATE"

echo "=== C. CADDY NETWORK TOPOLOGY, NO CONNECTION CHANGES ==="
STEP=NETWORK
CADDY_NETS="$(sudo -n docker inspect "$CADDY" --format '{{range $name,$n := .NetworkSettings.Networks}}{{$name}} {{end}}')"
LIVE_NETS="$(sudo -n docker inspect "$LIVE" --format '{{range $name,$n := .NetworkSettings.Networks}}{{$name}} {{end}}')"
CAND_NETS="$(sudo -n docker inspect "$CANDIDATE" --format '{{range $name,$n := .NetworkSettings.Networks}}{{$name}} {{end}}')"
echo "STAGE30_CADDY_NETWORKS=$CADDY_NETS"
echo "STAGE30_LIVE_NETWORKS=$LIVE_NETS"
echo "STAGE30_CANDIDATE_NETWORKS=$CAND_NETS"
SHARED=NO
for cn in $CADDY_NETS;do
  for nn in $CAND_NETS;do
    if [[ "$cn" == "$nn" ]];then SHARED=YES;fi
  done
done
echo "STAGE30_CADDY_CANDIDATE_SHARED_NETWORK=$SHARED"
if [[ "$SHARED" == NO ]];then
  echo "STAGE30_NETWORK_DEPENDENCY=BLOCKED_NEEDS_EXPLICITLY_APPROVED_NETWORK_ATTACHMENT_OR_ISOLATED_GATEWAY"
else
  echo "STAGE30_NETWORK_DEPENDENCY=SHARED_NETWORK_EXISTS"
fi

echo "=== D. CURRENT CADDY CONFIG INTEGRITY AND LIVE ROUTE DISCOVERY ==="
STEP=ROUTE
if ! sudo -n docker exec "$CADDY" sh -c 'test -r /etc/caddy/Caddyfile';then
  echo "STAGE30_CADDY_SOURCE=NOT_READABLE"
  exit 15
fi
B_CONFIG="$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')"
echo "STAGE30_CADDY_CONFIG_SHA256=$B_CONFIG"
if sudo -n docker exec "$CADDY" sh -c 'grep -q "sbi-bulk-report-pr129-https-preview" /etc/caddy/Caddyfile';then
 echo "STAGE30_EXISTING_PR129_UPSTREAM_REFERENCE=FOUND"
else
 echo "STAGE30_EXISTING_PR129_UPSTREAM_REFERENCE=NOT_FOUND_REVIEW_REQUIRED"
fi
if sudo -n docker exec "$CADDY" sh -c 'grep -q "reverse_proxy" /etc/caddy/Caddyfile';then
 echo "STAGE30_CADDY_PROXY_DIRECTIVES=FOUND"
else
 echo "STAGE30_CADDY_PROXY_DIRECTIVES=MISSING"
fi
echo "STAGE30_CADDYFILE_CHANGE=NONE"
echo "STAGE30_CADDY_RELOAD=NOT_PERFORMED"

echo "=== E. NEW UI AUTH/REPORT GUARDS ON PRIVATE CANDIDATE ==="
STEP=AUTH_REPORT
sudo -n docker exec -i "$CANDIDATE" python3 -B - <<'PY'
from pathlib import Path
from app import app
import google.auth
html=Path('/app/index.html').read_text()
assert 'SBI Reconciliation <span>Workspace</span>' in html
assert 'id="bulk-selected-button" disabled' in html
assert not Path('/app/pr129_aws_invoice_lookup.enabled').exists()
assert google.auth.default()[1]=='meghraj-reconciliation'
client=app.test_client()
for path in ['/api/reporting/v2/postgresql-summary','/api/bulk-report/status']:
 code=client.get(path).status_code
 assert code in (401,403),(path,code)
for path in ['/api/bulk-report/generate-excel','/api/bulk-report/select-invoices-excel']:
 code=client.post(path).status_code
 assert code in (401,403),(path,code)
print('STAGE30_MODERN_UI_AND_FIREBASE_ADC=PASS')
print('STAGE30_ANONYMOUS_GET_AND_POST=DENIED')
print('STAGE30_SELECTED_INVOICE_LOOKUP=DISABLED')
PY
[[ "$(sql "SELECT NOT has_table_privilege('sbi_pr129_report_login','sbi.invoices','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.payments','INSERT') AND NOT has_table_privilege('sbi_pr129_report_login','sbi.allocations','INSERT');")" == t ]]
echo "STAGE30_REPORT_READER_FINANCIAL_INSERT=DENIED"

echo "=== F. RECHECK LIVE IMAGES, CADDY CONFIG, DATABASE AND PRIVATE PORTS ==="
STEP=STABILITY
[[ "$B_LIVE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_STAGE25" == "$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_CAND" == "$(sudo -n docker inspect "$CANDIDATE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_CADDY" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_CONFIG" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ "$B_FIN" == "$(counts)" ]]
[[ -z "$(sudo -n docker port "$CANDIDATE")" ]]
echo "STAGE30_LIVE_PR129_UNCHANGED=PASS"
echo "STAGE30_STAGE25_UNCHANGED=PASS"
echo "STAGE30_STAGE26R2_UNCHANGED=PASS"
echo "STAGE30_CADDY_UNCHANGED=PASS"
echo "STAGE30_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE30 CONTROLLED CUTOVER PREPARATION ONLY ==="
echo "STAGE30_READ_ONLY_PREFLIGHT=PASS"
echo "STAGE30_OWNER_BROWSER_AUTH_QA=STAGE26R2_PREVIOUSLY_OBSERVED"
echo "STAGE30_BACKUP_AND_RESTORE=STAGE28_PREVIOUSLY_VERIFIED"
echo "STAGE30_NEEDS_EXACT_CADDY_ROUTE_AND_NETWORK_MIGRATION_PLAN=YES"
echo "STAGE30_REVERSIBLE_ROUTING_EXECUTION=NOT_PERFORMED"
echo "STAGE30_RELEASE_SCOPE=MODERN_UI_FIREBASE_READ_ONLY_REPORTING"
echo "STAGE30_EXCLUSIONS=FINANCIAL_ENGINE_WRITES_SELECTED_INVOICE_LOOKUP"
echo "STAGE30_RELEASE_GATE=BLOCKED_PENDING_DETAILED_ROUTING_PLAN_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "NEXT=REVIEW_STAGE30_NETWORK_AND_CADDY_RESULTS_THEN_FINALIZE_ROLLBACK_PLAN"
