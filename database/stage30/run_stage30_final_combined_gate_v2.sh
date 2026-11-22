#!/usr/bin/env bash
# STAGE30 FINAL COMBINED SAFETY GATE (NO CUTOVER).
# The release is conditionally owner-approved. Deployment happens only after
# exact routing, production origin and rollback plans are verified.
# This runner never changes production Caddy/Docker networks/financial data.
set -Eeuo pipefail
umask 077

STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
CANDIDATE=sbi-pr129-pg-modernui-stage26r2
STAGE25=sbi-pr129-pg-stage25-firebase-adc
CADDY=aws_lightsail-caddy-1
DB=sbi_reconciliation_main
SITE=pr129.13-232-241-221.sslip.io
NET=sbi_pr129_pg_staging_only
BACKUPS=/home/ubuntu/sbi-db-backups
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
DIR="$(mktemp -d "$EVID/stage30_final_gate_XXXXXXXX")"
chmod 700 "$DIR"
REPORT="$DIR/combined_gate.log"
exec > >(tee "$REPORT") 2>&1
CADDY_SNAPSHOT="$DIR/Caddyfile.original"
ADAPTED="$DIR/caddy_adapted.json"
GATE_ROUTING=UNKNOWN
GATE_ORIGIN=UNKNOWN
GATE_NETWORK=UNKNOWN
GATE_BACKUP=UNKNOWN
GATE_ROLLBACK=UNKNOWN
B_LIVE=""
B_STAGE25=""
B_CAND=""
B_CADDY=""
B_FIN=""
B_CONFIG=""

end(){
 local code=$?
 trap - EXIT
 if [[ -n "$B_LIVE" ]];then
   if [[ "$B_LIVE" != "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
     echo "STAGE30_LIVE_BASELINE_CHANGED=REVIEW_REQUIRED";code=99
   fi
 fi
 if [[ -n "$B_CONFIG" && -f "$CADDY_SNAPSHOT" ]];then
  current="$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile 2>/dev/null | awk '{print $1}')"
  if [[ "$B_CONFIG" != "$current" ]];then echo "STAGE30_CADDYFILE_CHANGED=REVIEW_REQUIRED";code=98;fi
 fi
 if [[ -n "$B_FIN" ]];then
  current_fin="$(sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);" 2>/dev/null)" || current_fin=UNKNOWN
  if [[ "$B_FIN" != "$current_fin" ]];then echo "STAGE30_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";code=97;fi
 fi
 if ((code));then
  echo "STAGE30_ALL_REMAINING_COMBINED_QA=FAIL step=$STEP exit=$code"
 else
  echo "STAGE30_ALL_REMAINING_COMBINED_QA=PASS_INSPECTION"
 fi
 echo "STAGE30_GATE_ROUTING=$GATE_ROUTING"
 echo "STAGE30_GATE_NETWORK=$GATE_NETWORK"
 echo "STAGE30_GATE_PRODUCTION_ORIGIN=$GATE_ORIGIN"
 echo "STAGE30_GATE_BACKUP=$GATE_BACKUP"
 echo "STAGE30_GATE_ROLLBACK=$GATE_ROLLBACK"
 echo "STAGE30_OWNER_APPROVAL=RECEIVED_CONDITIONAL_ON_RELEASE_CHECKS"
 echo "STAGE30_PRODUCTION_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_FINANCIAL_ENGINE=UNCHANGED"
 echo "STAGE30_EVIDENCE_DIRECTORY=$DIR"
 exit "$code"
}
trap end EXIT
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== A. PRODUCTION, STAGING, DB AND BACKUP BASELINE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$STAGE25" "$CANDIDATE" "$CADDY";do
  [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
    { echo "STAGE30_MISSING_RUNNING_CONTAINER=$c";exit 11; }
done
B_LIVE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_STAGE25="$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_CAND="$(sudo -n docker inspect "$CANDIDATE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_CADDY="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
B_FIN="$(counts)"
[[ -z "$(sudo -n docker port "$CANDIDATE")" ]]
[[ "$(sudo -n docker inspect "$CANDIDATE" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
echo "STAGE30_SOURCE_FINANCIAL_BASELINE=RECORDED"
echo "STAGE30_PRIVATE_CANDIDATE_PUBLIC_PORTS=NONE"

echo "=== B. REGISTER IMMUTABLE RELEASE AND ROLLBACK IMAGES ==="
STEP=IMAGES
LIVE_IMG="$(sudo -n docker inspect "$LIVE" --format '{{.Image}}')"
CAND_IMG="$(sudo -n docker inspect "$CANDIDATE" --format '{{.Image}}')"
sudo -n docker image inspect "$LIVE_IMG" "$CAND_IMG" >/dev/null
GATE_ROLLBACK=IMAGE_AVAILABLE
echo "STAGE30_EXISTING_LIVE_IMAGE_ID=$LIVE_IMG"
echo "STAGE30_RELEASE_CANDIDATE_IMAGE_ID=$CAND_IMG"
echo "STAGE30_EXISTING_LIVE_CONTAINED=YES"

echo "=== C. BACKUP CHECK AND ROLLBACK CONFIG SNAPSHOT ==="
STEP=BACKUP
[[ -d "$BACKUPS" ]]
ENC="$(find "$BACKUPS" -maxdepth 2 -type f -name 'sbi_reconciliation_main.dump.enc' -printf '%T@ %p\n' | sort -nr | sed -n '1s/^[^ ]* //p')"
[[ -n "$ENC" && -s "$ENC" && ! -L "$ENC" ]] ||
  { echo "STAGE30_RECOVERY_BACKUP_MISSING=YES";exit 13; }
[[ "$(stat -c '%a' "$ENC")" == 600 ]] ||
  { echo "STAGE30_ENCRYPTED_BACKUP_MODE=REVIEW_REQUIRED";exit 14; }
GATE_BACKUP=LOCAL_ENCRYPTED_PRESENT_OFFHOST_PREVIOUSLY_VERIFIED
echo "STAGE30_RECOVERY_BACKUP_FOLDER=$(basename "$(dirname "$ENC")")"
echo "STAGE30_RECOVERY_BACKUP_SHA256=$(sha256sum "$ENC" | awk '{print $1}')"
echo "STAGE30_OFFHOST_WINDOWS_COPY=PREVIOUS_OWNER_VERIFIED_NOT_RETRANSFERRED"

[[ "$(sudo -n docker exec "$CADDY" sh -c 'test -r /etc/caddy/Caddyfile && echo YES')" == YES ]]
sudo -n docker exec "$CADDY" cat /etc/caddy/Caddyfile > "$CADDY_SNAPSHOT"
chmod 600 "$CADDY_SNAPSHOT"
B_CONFIG="$(sha256sum "$CADDY_SNAPSHOT" | awk '{print $1}')"
[[ "$B_CONFIG" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
echo "STAGE30_ROLLBACK_CADDY_SNAPSHOT=PASS"
echo "STAGE30_ORIGINAL_CADDY_SHA256=$B_CONFIG"
echo "STAGE30_ROLLBACK_CONFIG_PATH=$CADDY_SNAPSHOT"

echo "=== D. ACTUAL CADDY ADAPTED ROUTE STRUCTURE AND HOST MAPPING ==="
STEP=ROUTE
if sudo -n docker exec "$CADDY" caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile > "$ADAPTED" 2>"$DIR/caddy_adapt.err";then
 echo "STAGE30_CADDY_ADAPT=PASS"
else
 echo "STAGE30_CADDY_ADAPT=BLOCKED_REVIEW_REQUIRED"
 exit 17
fi
chmod 600 "$ADAPTED" "$DIR/caddy_adapt.err"
python3 -B - "$ADAPTED" "$SITE" "$LIVE" > "$DIR/routes_result.env" <<'PY'
import json,sys
p,site,live=sys.argv[1:]
d=json.load(open(p))
seen=[]
def walk(node,hosts):
 if isinstance(node,dict):
  match=node.get('match')
  if isinstance(match,list):
   h=[v for rule in match if isinstance(rule,dict) for v in rule.get('host',[]) if isinstance(v,str)]
   if h:hosts=set(h)
  if node.get('handler')=='reverse_proxy':
   dial=[u.get('dial','') for u in node.get('upstreams',[]) if isinstance(u,dict)]
   seen.append((set(hosts),dial))
  for name,obj in node.items():
   if name not in ('match','upstreams'): walk(obj,hosts)
 elif isinstance(node,list):
  for x in node:walk(x,hosts)
for server in d.get('apps',{}).get('http',{}).get('servers',{}).values():
 walk(server.get('routes',[]),set())
pairs=[dial for hosts,dials in seen if site in hosts for dial in dials]
# Strict, fail-closed: an unexpected or ambiguous vhost requires manual route review.
exact=[p for p in pairs if live in p and p.rsplit(':',1)[-1]=='8080']
print("STAGE30_EXACT_VHOST_ROUTE_COUNT="+str(len(pairs)))
print("STAGE30_EXACT_LIVE_UPSTREAM_COUNT="+str(len(exact)))
print("STAGE30_CURRENT_PR129_UPSTREAM="+(exact[0] if len(exact)==1 else "NOT_UNAMBIGUOUS"))
print("STAGE30_ROUTE_CLASS="+("EXACT_ONE_LIVE_UPSTREAM" if len(pairs)==1 and len(exact)==1 else "REVIEW_REQUIRED"))
PY
cat "$DIR/routes_result.env"
if grep -qx 'STAGE30_ROUTE_CLASS=EXACT_ONE_LIVE_UPSTREAM' "$DIR/routes_result.env";then
 GATE_ROUTING=EXACT_UPSTREAM_IDENTIFIED
else
 GATE_ROUTING=BLOCKED_REQUIRE_ROUTE_REVIEW
fi

echo "=== E. PRIVATE NETWORK PATH; DO NOT ALTER CADDY CONNECTIVITY ==="
STEP=NETWORK
CADDY_NETS="$(sudo -n docker inspect "$CADDY" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
LIVE_NETS="$(sudo -n docker inspect "$LIVE" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
CAND_NETS="$(sudo -n docker inspect "$CANDIDATE" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
echo "STAGE30_CADDY_NETWORKS=$CADDY_NETS"
echo "STAGE30_LIVE_NETWORKS=$LIVE_NETS"
echo "STAGE30_CANDIDATE_NETWORKS=$CAND_NETS"
SHARED=NO
for c in $CADDY_NETS;do
  for n in $CAND_NETS;do
    if [[ "$c" == "$n" ]];then SHARED=YES;fi
  done
done
echo "STAGE30_CADDY_CANDIDATE_SHARED_NETWORK=$SHARED"
if [[ "$SHARED" == NO ]];then
 GATE_NETWORK=BLOCKED_NEEDS_SEPARATE_PRODUCTION_NETWORK_RELEASE_CANDIDATE
else
 GATE_NETWORK=SHARED_NETWORK_EXISTS
fi

echo "=== F. FIREBASE PRODUCTION HTTPS ORIGIN AND ANONYMOUS PROTECTION ==="
STEP=ORIGIN
sudo -n docker exec -i "$CANDIDATE" python3 -B - "$SITE" > "$DIR/origin_result.env" <<'PY'
from pathlib import Path
import sys,google.auth,os
from app import app
import dashboard_sessions
site=sys.argv[1]
required="https://"+site
origins=getattr(dashboard_sessions,"ORIGINS",None)
if not isinstance(origins,(list,tuple,set,frozenset)):
 state="UNKNOWN"
else:
 state="YES" if required in origins else "NO"
assert google.auth.default()[1]=="meghraj-reconciliation"
h=Path('/app/index.html').read_text()
assert 'SBI Reconciliation <span>Workspace</span>' in h
assert 'id="bulk-selected-button" disabled' in h
assert not Path('/app/pr129_aws_invoice_lookup.enabled').exists()
assert not os.environ.get('INVOICE_LOOKUP_BACKEND')
r=app.test_client()
for route in ('/api/reporting/v2/postgresql-summary','/api/bulk-report/status'):
 assert r.get(route).status_code in (401,403)
for route in ('/api/bulk-report/generate-excel','/api/bulk-report/select-invoices-excel'):
 assert r.post(route).status_code in (401,403)
print("STAGE30_PRODUCTION_HTTPS_ORIGIN_ALLOWED="+state)
print("STAGE30_FIREBASE_ADC=PASS")
print("STAGE30_ANONYMOUS_REPORT_AND_BULK_POST=DENIED")
print("STAGE30_SELECTED_INVOICE_LOOKUP=DISABLED")
PY
cat "$DIR/origin_result.env"
if grep -qx 'STAGE30_PRODUCTION_HTTPS_ORIGIN_ALLOWED=YES' "$DIR/origin_result.env";then
 GATE_ORIGIN=PRODUCTION_HOST_ALLOWED
else
 GATE_ORIGIN=BLOCKED_PRODUCTION_AUTH_ORIGIN_NOT_VERIFIED
fi

echo "=== G. POSTGRESQL VIEW SECURITY AND RECORD STABILITY ==="
STEP=POSTGRES
sudo -n docker exec -i "$CANDIDATE" python3 -B - <<'PY'
import psycopg
with psycopg.connect(connect_timeout=8) as c:
 c.execute("SET TRANSACTION READ ONLY")
 assert c.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()==("sbi_pr129_report_login","sbi_reconciliation_main","on")
 flags=c.execute(
 "SELECT has_table_privilege(current_user,'sbi.invoices','INSERT'),"
 "has_table_privilege(current_user,'sbi.payments','INSERT'),"
 "has_table_privilege(current_user,'sbi.allocations','INSERT'),"
 "has_table_privilege(current_user,'sbi.credit_notes','INSERT')").fetchone()
 assert flags==(False,False,False,False)
 c.execute('SELECT count(*) FROM sbi.invoice_financial_summary').fetchone()
 c.execute('SELECT count(*) FROM sbi.payment_financial_summary').fetchone()
print("STAGE30_DATABASE_READ_ONLY_AND_REPORT_VIEWS=PASS")
print("STAGE30_FINANCIAL_INSERT_PRIVILEGES=DENIED")
PY

echo "=== H. POST-TEST IMMUTABILITY / ROLLBACK SAFETY ==="
STEP=STABILITY
[[ "$B_LIVE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_STAGE25" == "$(sudo -n docker inspect "$STAGE25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_CAND" == "$(sudo -n docker inspect "$CANDIDATE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_CADDY" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$B_CONFIG" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ "$B_FIN" == "$(counts)" ]]
[[ -z "$(sudo -n docker port "$CANDIDATE")" ]]
echo "STAGE30_LIVE_CONTAINER_AND_CADDY_UNCHANGED=PASS"
echo "STAGE30_FINANCIAL_COUNTS_UNCHANGED=PASS"

cat > "$DIR/rollback_readiness.txt" <<'PLAN'
SBI PR129 limited release — rollback readiness notes (NOT an executable runbook)

Previous live PR129 container must stay running until the new route is fully verified.
The previous live image is retained and recorded in combined_gate.log.
The original Caddyfile is saved as Caddyfile.original with mode 0600.

An executable rollback procedure must be validated against the actual Caddy
route and candidate network before changing live traffic:
  1. Restore the saved original Caddyfile if the new route was activated.
  2. Validate its syntax and confirm the old upstream is still running.
  3. Reload Caddy only after a verified config and exact route check.
  4. Confirm live login, anonymous access denial and read-only reporting.
  5. Never change PostgreSQL financial data or enable the Financial Engine.

No production rollback should depend on an untested host/network assumption.
PLAN
chmod 600 "$DIR/rollback_readiness.txt"

STEP=COMPLETE
echo "=== FINAL STAGE30 SINGLE COMBINED REMAINING-GATE REPORT ==="
echo "STAGE30_SCOPE_APPROVAL=RECORDED_CONDITIONAL"
echo "STAGE30_ROLLBACK_SOURCE_CADDYFILE=SNAPSHOT_CAPTURED"
echo "STAGE30_ROLLBACK_LIVE_IMAGE=PRESENT"
echo "STAGE30_ORIGIN_GATE=$GATE_ORIGIN"
echo "STAGE30_NETWORK_GATE=$GATE_NETWORK"
echo "STAGE30_ROUTING_GATE=$GATE_ROUTING"
if [[ "$GATE_ROUTING" == EXACT_UPSTREAM_IDENTIFIED && "$GATE_NETWORK" == SHARED_NETWORK_EXISTS && "$GATE_ORIGIN" == PRODUCTION_HOST_ALLOWED ]];then
 echo "STAGE30_RELEASE_CANDIDATE=GATES_MET_FOR_DETAILED_ROLLBACK_AND_CANARY_PLAN"
else
 echo "STAGE30_RELEASE_CANDIDATE=BLOCKED_UNTIL_PRODUCTION_ORIGIN_NETWORK_AND_ROUTE_REMEDIATED"
fi
echo "STAGE30_PREVIEW_AND_LIVE=UNCHANGED"
echo "STAGE30_NEXT=FINALIZE_EXACT_ROLLBACK_AND_CONTROLLED_SWITCH_FROM_GATE_EVIDENCE"
