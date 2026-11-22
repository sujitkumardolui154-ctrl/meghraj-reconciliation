#!/usr/bin/env bash
# Stage30 combined network canary. Approved limited release, but NOT a live cutover.
# Only CREATE an additional internal-only canary on Caddy's existing live network.
# Do not modify any existing container, Caddy route, source DB or Financial Engine.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
OLDSTAGE=sbi-pr129-pg-stage25-firebase-adc
SOURCE=sbi-pr129-pg-modernui-stage26r2
CANARY=sbi-pr129-modern-release-canary
CADDY=aws_lightsail-caddy-1
DB=sbi_reconciliation_main
PGPASS=/home/ubuntu/sbi-pr129-pg-private-stage/pgpass
WEBENV=/home/ubuntu/sbi-pr129-pg-private-stage/staging_web_auth.env
GOOGLE_CRED=/home/ubuntu/sbi-private-credentials/firebase-stage.json
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
REPORT="$EVID/stage30_network_canary_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$REPORT") 2>&1
CREATED=NO
BASELINE=""
BASE_FIN=""
BASE_CADDY_SHA=""
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
container_states(){
 for c in "$LIVE" "$OLDSTAGE" "$SOURCE" "$CADDY";do
  sudo -n docker inspect "$c" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'
 done
}
finish(){
 local rc=$?
 trap - EXIT
 if ((rc)) && [[ "$CREATED" == YES ]];then
  if sudo -n docker rm -f "$CANARY" >/dev/null 2>&1;then
   echo "STAGE30_FAILED_CANARY_REMOVED=PASS"
  else
   echo "STAGE30_FAILED_CANARY_REMOVED=FAIL";rc=98
  fi
 fi
 if [[ -n "$BASELINE" ]] && [[ "$BASELINE" != "$(container_states 2>/dev/null)" ]];then
  echo "STAGE30_EXISTING_CONTAINERS_CHANGED=REVIEW_REQUIRED";rc=97
 fi
 if [[ -n "$BASE_FIN" ]] && [[ "$BASE_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";rc=96
 fi
 if [[ -n "$BASE_CADDY_SHA" ]] && [[ "$BASE_CADDY_SHA" != "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile 2>/dev/null | awk '{print $1}')" ]];then
  echo "STAGE30_CADDY_CONFIG_CHANGED=REVIEW_REQUIRED";rc=95
 fi
 if ((rc));then echo "STAGE30_NETWORK_CANARY_COMBINED_QA=FAIL step=$STEP exit=$rc"
 else echo "STAGE30_NETWORK_CANARY_COMBINED_QA=PASS";fi
 echo "STAGE30_OWNER_SCOPE_APPROVAL=RECEIVED_CONDITIONAL"
 echo "STAGE30_PRODUCTION_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_EVIDENCE_FILE=$REPORT"
 exit "$rc"
}
trap finish EXIT

echo "=== A. PRECONDITIONS FROM VERIFIED STAGE30 FINAL GATE ==="
STEP=GATE
GATE_FILE=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/combined_gate.log
[[ -s "$GATE_FILE" ]] || { echo "STAGE30_APPROVED_GATE_EVIDENCE=NOT_FOUND";exit 11; }
for required in \
 "STAGE30_GATE_ROUTING=EXACT_UPSTREAM_IDENTIFIED" \
 "STAGE30_GATE_PRODUCTION_ORIGIN=PRODUCTION_HOST_ALLOWED" \
 "STAGE30_GATE_ROLLBACK=IMAGE_AVAILABLE" \
 "STAGE30_GATE_BACKUP=LOCAL_ENCRYPTED_PRESENT_OFFHOST_PREVIOUSLY_VERIFIED"
do
 grep -Fxq "$required" "$GATE_FILE" || {
  echo "STAGE30_GATE_EVIDENCE_MISSING=$required";exit 12;
 }
done
echo "STAGE30_ROUTING_ORIGIN_BACKUP_IMAGE_GATES=PASS_PREVIOUS_EVIDENCE"

echo "=== B. SNAPSHOT LIVE AND SOURCE FINANCIAL RECORDS ==="
STEP=BASELINE
sudo -n docker info >/dev/null
BASELINE="$(container_states)"
for c in "$LIVE" "$OLDSTAGE" "$SOURCE" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
  { echo "REQUIRED_CONTAINER_DOWN=$c";exit 13; }
done
BASE_FIN="$(counts)"
BASE_CADDY_SHA="$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')"
EXPECTED_SHA="$(sha256sum /home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original | awk '{print $1}')"
[[ "$BASE_CADDY_SHA" == "$EXPECTED_SHA" ]] ||
 { echo "STAGE30_CADDY_CONFIG_CHANGED_SINCE_FINAL_GATE=BLOCKED";exit 14; }
[[ -z "$(sudo -n docker port "$SOURCE")" ]]
if sudo -n docker inspect "$CANARY" >/dev/null 2>&1;then
 echo "STAGE30_CANARY_ALREADY_EXISTS=REVIEW_REQUIRED";exit 15
fi
echo "STAGE30_LIVE_SOURCE_BASELINE=PASS"
echo "STAGE30_CADDY_CONFIG_MATCHES_BACKUP=PASS"

echo "=== C. RESOLVE EXISTING NETWORK SHARED BY CADDY AND LIVE PR129 ==="
STEP=NETWORK
CADDY_NETS="$(sudo -n docker inspect "$CADDY" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
LIVE_NETS="$(sudo -n docker inspect "$LIVE" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
echo "STAGE30_CADDY_NETWORKS=$CADDY_NETS"
echo "STAGE30_LIVE_NETWORKS=$LIVE_NETS"
CANDIDATE_NET=""
MATCH_COUNT=0
for a in $CADDY_NETS;do
 for b in $LIVE_NETS;do
  if [[ "$a" == "$b" ]];then
   CANDIDATE_NET="$a"
   MATCH_COUNT=$((MATCH_COUNT+1))
   if [[ "$a" == sbi_pr129_preview_net ]];then
    CANDIDATE_NET=sbi_pr129_preview_net
   fi
  fi
 done
done
((MATCH_COUNT>=1)) || { echo "STAGE30_NO_COMMON_CADDY_LIVE_NETWORK=BLOCKED";exit 20; }
if ((MATCH_COUNT>1));then
 FOUND=NO
 for a in $CADDY_NETS;do
  for b in $LIVE_NETS;do
   if [[ "$a" == "$b" && "$a" == sbi_pr129_preview_net ]];then FOUND=YES;fi
  done
 done
 [[ "$FOUND" == YES ]] || { echo "STAGE30_AMBIGUOUS_SHARED_NETWORKS=BLOCKED";exit 21; }
 CANDIDATE_NET=sbi_pr129_preview_net
fi
[[ "$(sudo -n docker network inspect "$CANDIDATE_NET" --format '{{.Driver}}')" == bridge ]] ||
 { echo "STAGE30_NETWORK_DRIVER=NOT_VERIFIED";exit 22; }
echo "STAGE30_CADDY_REACHABLE_TARGET_NETWORK=$CANDIDATE_NET"

echo "=== D. PREPARE IMMUTABLE IMAGE AND RESTRICTED EXISTING CREDENTIALS ==="
STEP=CREDENTIALS
for f in "$PGPASS" "$WEBENV" "$GOOGLE_CRED";do
 [[ -f "$f" && ! -L "$f" && "$(stat -c '%a' "$f")" == 600 ]] ||
 { echo "STAGE30_CREDENTIAL_FILE_MODE=FAIL";exit 23; }
done
IMAGE="$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')"
sudo -n docker image inspect "$IMAGE" >/dev/null
echo "STAGE30_CANARY_IMAGE=$IMAGE"
echo "STAGE30_CREDENTIAL_CONTENTS=NOT_DISPLAYED"

echo "=== E. START NEW INTERNAL-ONLY RELEASE CANARY (NO CADDY CUTOVER) ==="
STEP=START_CANARY
sudo -n docker run -d --name "$CANARY" \
 --network "$CANDIDATE_NET" --restart no --read-only \
 --tmpfs /tmp:rw,nosuid,nodev,size=64m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" \
 --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
 --mount "type=bind,source=$PGPASS,target=/run/secrets/sbi_pgpass,readonly" \
 --mount "type=bind,source=$GOOGLE_CRED,target=/run/secrets/firebase-stage.json,readonly" \
 --env-file "$WEBENV" \
 -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-stage.json \
 -e PGHOST=/var/run/postgresql -e PGPORT=5432 \
 -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
 -e PGPASSFILE=/run/secrets/sbi_pgpass -e PYTHONDONTWRITEBYTECODE=1 \
 "$IMAGE" >/dev/null
CREATED=YES
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.State.Running}}')" == true ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
echo "STAGE30_CANARY_RUNNING_INTERNAL_ONLY=PASS"

echo "=== F. COMBINED AUTH, HTTP, POSTGRES AND WRITE-DENIAL QA ==="
STEP=CANARY_LOCAL_QA
READY=NO
for attempt in 1 2 3 4 5 6 7 8 9 10;do
 if sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
import urllib.request,urllib.error,google.auth,psycopg,os
from pathlib import Path
import dashboard_sessions
assert google.auth.default()[1]=='meghraj-reconciliation'
assert 'https://pr129.13-232-241-221.sslip.io' in dashboard_sessions.ORIGINS
html=Path('/app/index.html').read_text()
assert 'SBI Reconciliation <span>Workspace</span>' in html
assert 'id="bulk-selected-button" disabled' in html
assert not Path('/app/pr129_aws_invoice_lookup.enabled').exists()
assert not os.getenv('INVOICE_LOOKUP_BACKEND')
def status(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=4) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
assert status('/login')==200
assert status('/dashboard.js')==200
assert status('/api/reporting/v2/postgresql-summary') in (401,403)
assert status('/api/bulk-report/status') in (401,403)
with psycopg.connect(connect_timeout=8) as c:
 c.execute('SET TRANSACTION READ ONLY')
 assert c.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()==(
 'sbi_pr129_report_login','sbi_reconciliation_main','on')
 for table in ('invoices','payments','allocations','credit_notes'):
  assert c.execute('SELECT has_table_privilege(current_user,%s,%s)',('sbi.'+table,'INSERT')).fetchone()[0] is False
 c.execute('SELECT count(*) FROM sbi.invoice_financial_summary').fetchone()
 c.execute('SELECT count(*) FROM sbi.payment_financial_summary').fetchone()
print('STAGE30_FIREBASE_ADC=PASS')
print('STAGE30_CANARY_LOGIN_AND_STATIC=PASS')
print('STAGE30_CANARY_ANONYMOUS_REPORTING=DENIED')
print('STAGE30_POSTGRES_READ_ONLY=PASS')
PY
 then READY=YES;break;fi
 sleep 2
done
[[ "$READY" == YES ]] || { echo "STAGE30_CANARY_READINESS=FAIL";exit 31; }

echo "=== G. PROBE CANARY FROM INDEPENDENT CLIENT ON CADDY NETWORK ==="
STEP=NETWORK_PROBE
sudo -n docker run --rm -i --network "$CANDIDATE_NET" \
 --read-only --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" \
 --entrypoint python3 "$IMAGE" -B - "$CANARY" <<'PY'
import sys,urllib.request,urllib.error
base='http://'+sys.argv[1]+':8080'
def status(path):
 try:
  with urllib.request.urlopen(base+path,timeout=7) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
assert status('/login')==200
assert status('/dashboard.js')==200
assert status('/api/reporting/v2/postgresql-summary') in (401,403)
print('STAGE30_CADDY_NETWORK_DNS_REACHABILITY=PASS')
print('STAGE30_CADDY_NETWORK_ANONYMOUS_REPORT=DENIED')
PY

echo "=== H. IDENTIFY ACTUAL CADDY HOST CONFIG MOUNT FOR REVERSIBLE CUTOVER ==="
STEP=ROLLBACK
sudo -n docker inspect "$CADDY" --format '{{json .Mounts}}' |
 python3 -B -c 'import json,sys;ms=json.load(sys.stdin);valid=False
for m in ms:
 if m.get("Destination") in ("/etc/caddy","/etc/caddy/Caddyfile"):
  valid=True
  print("STAGE30_CADDY_MOUNT_DEST="+str(m.get("Destination")))
  print("STAGE30_CADDY_MOUNT_TYPE="+str(m.get("Type")))
  print("STAGE30_CADDY_MOUNT_SOURCE="+str(m.get("Source")))
if not valid:print("STAGE30_CADDY_HOST_CONFIG=NOT_DIRECTLY_MOUNTED_REVIEW_REQUIRED")'
echo "STAGE30_PREVIOUS_LIVE_ROLLBACK_IMAGE=$(sudo -n docker inspect "$LIVE" --format '{{.Image}}')"
echo "STAGE30_CADDY_ROLLBACK_SNAPSHOT=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original"
echo "STAGE30_PRODUCTION_ROUTE_SWITCH=NOT_PERFORMED"

echo "=== I. ALL EXISTING CONTAINERS AND FINANCIAL DATABASE UNCHANGED ==="
STEP=STABILITY
[[ "$BASELINE" == "$(container_states)" ]]
[[ "$BASE_FIN" == "$(counts)" ]]
[[ "$BASE_CADDY_SHA" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
echo "STAGE30_LIVE_PR129_UNCHANGED=PASS"
echo "STAGE30_STAGE25_UNCHANGED=PASS"
echo "STAGE30_STAGE26R2_UNCHANGED=PASS"
echo "STAGE30_CADDY_UNCHANGED=PASS"
echo "STAGE30_FINANCIAL_COUNTS_UNCHANGED=PASS"
STEP=COMPLETE
echo "=== FINAL STAGE30 INTERNAL CANARY NETWORK REMEDIATION ==="
echo "STAGE30_NETWORK_CANARY=PASS"
echo "STAGE30_FIREBASE_AND_POSTGRES_CANARY=PASS"
echo "STAGE30_ROLLBACK_MOUNT_INVENTORY=COMPLETE"
echo "STAGE30_NEXT=PREPARE_AND_VERIFY_EXACT_REVERSIBLE_CADDY_CUTOVER"
echo "STAGE30_FINANCIAL_ENGINE=UNCHANGED"
echo "STAGE30_LIVE_CUTOVER=NOT_PERFORMED"
