#!/usr/bin/env bash
# Stage30: final EXACT Caddy routing candidate and rollback validation.
# DRY RUN ONLY: writes only under /home/ubuntu/sbi-release-evidence.
# Does NOT edit or reload live Caddy, change networks/containers, enable
# selected-invoice lookup, authorize financial writes or run the engine.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
SOURCE=sbi-pr129-pg-modernui-stage26r2
CANARY=sbi-pr129-modern-release-canary
CADDY=aws_lightsail-caddy-1
CADDYHOST=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
PRIOR=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
OLD_UPSTREAM=sbi-bulk-report-pr129-https-preview:8080
NEW_UPSTREAM=sbi-pr129-modern-release-canary:8080
SITE=pr129.13-232-241-221.sslip.io
DB=sbi_reconciliation_main
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID"
chmod 700 "$EVID"
DIR="$(mktemp -d "$EVID/stage30_caddy_dryrun_XXXXXXXX")"
chmod 700 "$DIR"
exec > >(tee "$DIR/dryrun.log") 2>&1
BASE=""
BASE_LIVE=""
BASE_CADDY=""
BASE_CANARY=""
BASE_FIN=""
counts(){
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" \
 -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$BASE" ]];then
  current="$(sudo -n sha256sum "$CADDYHOST" 2>/dev/null | awk '{print $1}')" || current=ERROR
  if [[ "$current" != "$BASE" ]];then echo "STAGE30_HOST_CADDY_CHANGED=REVIEW_REQUIRED";rc=95;fi
  current="$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile 2>/dev/null | awk '{print $1}')" || current=ERROR
  if [[ "$current" != "$BASE" ]];then echo "STAGE30_CONTAINER_CADDY_CHANGED=REVIEW_REQUIRED";rc=96;fi
 fi
 if [[ -n "$BASE_LIVE" && "$BASE_LIVE" != "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_LIVE_CHANGED=REVIEW_REQUIRED";rc=97
 fi
 if [[ -n "$BASE_CANARY" && "$BASE_CANARY" != "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_CANARY_CHANGED=REVIEW_REQUIRED";rc=98
 fi
 if [[ -n "$BASE_FIN" && "$BASE_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_SOURCE_COUNTS_CHANGED=REVIEW_REQUIRED";rc=99
 fi
 if ((rc));then echo "STAGE30_REVERSIBLE_ROUTING_DRYRUN=FAIL step=$STEP exit=$rc"
 else echo "STAGE30_REVERSIBLE_ROUTING_DRYRUN=PASS";fi
 echo "STAGE30_OWNER_SCOPE_APPROVAL=ALREADY_RECEIVED_CONDITIONALLY"
 echo "STAGE30_CADDY_ROUTING_CHANGE=NONE"
 echo "STAGE30_LIVE_PR129_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_EVIDENCE_DIRECTORY=$DIR"
 exit "$rc"
}
trap finish EXIT

echo "=== A. CAPTURE LIVE, CANARY AND FINANCIAL BASELINE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$SOURCE" "$CANARY" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_REQUIRED_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
BASE_LIVE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CADDY="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CANARY="$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_FIN="$(counts)"
[[ -z "$(sudo -n docker port "$CANARY")" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.Image}}')" == "$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.HostConfig.NetworkMode}}')" == sbi_pr129_preview_net ]]
echo "STAGE30_RELEASE_CANARY_IMAGE_NETWORK_PRIVATE_PORTS=PASS"

echo "=== B. VERIFY EXACT CADDY BIND SOURCE AND HISTORICAL BACKUP ==="
STEP=CONFIG_SOURCE
[[ -f "$CADDYHOST" && ! -L "$CADDYHOST" && -s "$PRIOR" ]] ||
 { echo "STAGE30_CADDY_BIND_OR_BACKUP=MISSING";exit 12; }
sudo -n docker inspect "$CADDY" --format '{{json .Mounts}}' |
python3 -B -c 'import json,sys
mounts=json.load(sys.stdin)
assert any(m.get("Type")=="bind" and
 m.get("Source")=="/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile" and
 m.get("Destination")=="/etc/caddy/Caddyfile" for m in mounts), "Unexpected Caddy bind mount"
print("STAGE30_VERIFIED_CADDY_BIND_MOUNT=PASS")'
BASE="$(sudo -n sha256sum "$CADDYHOST" | awk '{print $1}')"
[[ "$BASE" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]] ||
 { echo "STAGE30_HOST_AND_CONTAINER_FILE=DIFFERENT_BLOCKED";exit 13; }
[[ "$BASE" == "$(sha256sum "$PRIOR" | awk '{print $1}')" ]] ||
 { echo "STAGE30_CADDY_CHANGED_SINCE_STAGED_BACKUP=BLOCKED";exit 14; }
cp "$PRIOR" "$DIR/Caddyfile.original"
chmod 600 "$DIR/Caddyfile.original"
echo "STAGE30_ORIGINAL_CADDYFILE_SHA256=$BASE"
echo "STAGE30_CADDY_ROLLBACK_COPY=PASS"

echo "=== C. BUILD ONE EXACT TEXT SUBSTITUTION, LEAVE LIVE UNMODIFIED ==="
STEP=CANDIDATE
python3 -B - "$DIR/Caddyfile.original" "$DIR/Caddyfile.candidate" "$OLD_UPSTREAM" "$NEW_UPSTREAM" <<'PY'
from pathlib import Path
import sys
original,candidate,old,new=map(str,sys.argv[1:])
data=Path(original).read_bytes()
count=data.count(old.encode())
assert count==1, f"Expected one exact old PR129 upstream, got {count}"
new_data=data.replace(old.encode(),new.encode(),1)
assert new_data!=data
Path(candidate).write_bytes(new_data)
assert new_data.replace(new.encode(),old.encode(),1)==data
print("STAGE30_SINGLE_UPSTREAM_REPLACEMENT=PASS")
print("STAGE30_ROLLBACK_BYTE_FOR_BYTE_ROUNDTRIP=PASS")
PY
chmod 600 "$DIR/Caddyfile.candidate"
echo "STAGE30_PROPOSED_CADDYFILE_SHA256=$(sha256sum "$DIR/Caddyfile.candidate" | awk '{print $1}')"

echo "=== D. ADAPT ORIGINAL AND PROPOSED CADDYFILE WITHOUT RELOAD ==="
STEP=ADAPT
sudo -n docker exec -i "$CADDY" caddy adapt --config - --adapter caddyfile \
 < "$DIR/Caddyfile.original" > "$DIR/old.json" 2>"$DIR/old_adapt.log"
sudo -n docker exec -i "$CADDY" caddy adapt --config - --adapter caddyfile \
 < "$DIR/Caddyfile.candidate" > "$DIR/new.json" 2>"$DIR/new_adapt.log"
chmod 600 "$DIR/old.json" "$DIR/new.json" "$DIR/old_adapt.log" "$DIR/new_adapt.log"
python3 -B - "$DIR/old.json" "$DIR/new.json" "$OLD_UPSTREAM" "$NEW_UPSTREAM" "$SITE" <<'PY'
import json,sys
original,new,old_dial,new_dial,site=sys.argv[1:]
before=json.load(open(original))
after=json.load(open(new))
hits=[0]
def replace(node):
 if isinstance(node,dict):
  r={}
  for k,v in node.items():
   if k=="dial" and v==old_dial:
    hits[0]+=1
    r[k]=new_dial
   else:r[k]=replace(v)
  return r
 if isinstance(node,list):return [replace(x) for x in node]
 return node
assert replace(before)==after,"Adapted config differs beyond intended upstream"
assert hits[0]==1,"Expected exactly one old upstream in adapted config"
# Check that the intended host has a reverse_proxy using that upstream
found=[]
def walk(node,hosts):
 if isinstance(node,dict):
  rules=node.get("match")
  if isinstance(rules,list):
   hs=[x for m in rules if isinstance(m,dict) for x in m.get("host",[]) if isinstance(x,str)]
   if hs: hosts=set(hs)
  if node.get("handler")=="reverse_proxy":
   for entry in node.get("upstreams",[]):
    if isinstance(entry,dict):found.append((set(hosts),entry.get("dial")))
  for k,v in node.items():
   if k not in ("match","upstreams"):walk(v,hosts)
 elif isinstance(node,list):
  for v in node:walk(v,hosts)
for sv in after.get("apps",{}).get("http",{}).get("servers",{}).values():
 walk(sv.get("routes",[]),set())
matches=[dial for hosts,dial in found if site in hosts]
assert matches==[new_dial],f"Unexpected site upstream mapping: {matches}"
print("STAGE30_ADAPTED_CONFIG_PARITY_EXCEPT_ONE_UPSTREAM=PASS")
print("STAGE30_EXACT_SITE_NEW_UPSTREAM=PASS")
PY

echo "=== E. CADDY PROVISIONING VALIDATION, WITHOUT PRODUCTION ROUTE CHANGE ==="
STEP=VALIDATE
if sudo -n docker exec -i "$CADDY" caddy validate --config - --adapter caddyfile \
 < "$DIR/Caddyfile.candidate" >"$DIR/caddy_validate.log" 2>&1;then
 echo "STAGE30_CADDY_CANDIDATE_VALIDATE=PASS"
else
 echo "STAGE30_CADDY_CANDIDATE_VALIDATE=FAILED_REVIEW_REQUIRED"
 echo "STAGE30_CADDY_VALIDATE_LOG=$DIR/caddy_validate.log"
 exit 17
fi
chmod 600 "$DIR/caddy_validate.log"

echo "=== F. VERIFY INTERNAL CANARY HTTP REACHABILITY AND SECURITY ==="
STEP=CANARY
sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
import urllib.request,urllib.error
def status(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=5) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
assert status('/login')==200
assert status('/api/reporting/v2/postgresql-summary') in (401,403)
assert status('/api/bulk-report/status') in (401,403)
print("STAGE30_CANARY_LOGIN_PAGE=PASS")
print("STAGE30_CANARY_ANONYMOUS_REPORT_ACCESS=DENIED")
PY
echo "STAGE30_INTERNAL_CANARY_HTTP_QA=PASS"

echo "=== G. VERIFY ORIGINAL CADDY AND FINANCIAL STATE UNCHANGED ==="
STEP=STABILITY
[[ "$BASE_LIVE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CADDY" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CANARY" == "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE" == "$(sudo -n sha256sum "$CADDYHOST" | awk '{print $1}')" ]]
[[ "$BASE_FIN" == "$(counts)" ]]
echo "STAGE30_CURRENT_LIVE_PR129=UNCHANGED"
echo "STAGE30_CURRENT_CADDY_CONFIG=UNCHANGED"
echo "STAGE30_FINANCIAL_SOURCE_COUNTS=UNCHANGED"

STEP=COMPLETE
echo "=== FINAL STAGE30 REVERSIBLE CADDY CUTOVER DRY RUN ==="
echo "STAGE30_ONE_ROUTE_REPLACEMENT=PASS"
echo "STAGE30_PROPOSED_ROUTE_ADAPTED_PARITY=PASS"
echo "STAGE30_CADDY_VALIDATE=PASS"
echo "STAGE30_ROLLBACK_BYTE_PARITY=PASS"
echo "STAGE30_ORIGINAL_CONFIG_PATH=$DIR/Caddyfile.original"
echo "STAGE30_VALIDATED_CANDIDATE_PATH=$DIR/Caddyfile.candidate"
echo "STAGE30_NEXT=CONTROLLED_LIVE_SWITCH_WITH_AUTO_ROLLBACK_AND_POST_CUTOVER_QA"
echo "STAGE30_LIMITED_SCOPE=UI_FIREBASE_READONLY_REPORTS_ONLY"
echo "STAGE30_FINANCIAL_ENGINE=UNCHANGED"
