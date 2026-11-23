#!/usr/bin/env bash
# SBI STAGE30.6: OWNER-CONDITIONALLY-APPROVED LIMITED PR129 CADDY CUTOVER
# Explicitly changes exactly ONE live PR129 Caddy route only after all guards pass.
# On error AFTER modification, restores old host Caddyfile IN PLACE and reloads.
# No financial engine, financial writes, DB migrations, selected invoice lookup.
set -Eeuo pipefail
umask 077
STEP=INIT
SITE=pr129.13-232-241-221.sslip.io
LIVE=sbi-bulk-report-pr129-https-preview
TARGET=sbi-pr129-modern-release-final
STAGE=sbi-pr129-pg-modernui-stage26r2
CADDY=aws_lightsail-caddy-1
NET=sbi_pr129_preview_net
CADDYFILE=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
READY=/home/ubuntu/sbi-release-evidence/stage30_5_durable_Ft4fao2H
PRIOR=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
DB=sbi_reconciliation_main
EXPECTED_OLD=6aaddeedPLACEHOLDER
EXPECTED_NEW=61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b
DIR="/home/ubuntu/sbi-release-evidence/stage30_6_cutover_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$DIR"
exec > >(tee "$DIR/combined.log") 2>&1
BASE_FIN=""
BASE_LIVE=""
BASE_TARGET=""
BASE_CADDY=""
BASE_CONFIG=""
CHANGED=NO
ROLLBACK_ATTEMPTED=NO
SUCCESS=NO

counts(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
id(){ sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'; }
sha(){ sudo -n sha256sum "$1" | awk '{print $1}'; }
restore_in_place(){
  local src="$1" dest="$2"
  sudo -n python3 -B - "$src" "$dest" <<'PY'
import os,sys
from pathlib import Path
src,dest=sys.argv[1:]
data=Path(src).read_bytes()
fd=os.open(dest,os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 st=os.fstat(fd)
 assert os.path.isfile(dest)
 os.lseek(fd,0,os.SEEK_SET)
 os.write(fd,data)
 os.ftruncate(fd,len(data))
 os.fsync(fd)
finally:os.close(fd)
PY
}
reload_caddy(){
 timeout 20s sudo -n docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
}
active_route(){
 local expect="$1"
 sudo -n docker exec "$CADDY" wget -qO- http://127.0.0.1:2019/config/ |
 python3 -B -c 'import json,sys
site,dial=sys.argv[1:]
config=json.load(sys.stdin)
found=[]
def walk(node,hosts):
 if isinstance(node,list):
  for item in node:walk(item,hosts)
 elif isinstance(node,dict):
  matches=node.get("match")
  if isinstance(matches,list):
   names=[h for m in matches if isinstance(m,dict) for h in m.get("host",[]) if isinstance(h,str)]
   if names:hosts=set(names)
  if node.get("handler")=="reverse_proxy":
   found.extend(u.get("dial") for u in node.get("upstreams",[]) if isinstance(u,dict) and site in hosts)
  for k,v in node.items():
   if k not in ("match","upstreams"):walk(v,hosts)
for server in config.get("apps",{}).get("http",{}).get("servers",{}).values():
 walk(server.get("routes",[]),set())
if found!=[dial]:
 print("STAGE30_ACTIVE_CADDY_UPSTREAM=UNEXPECTED",flush=True)
 sys.exit(2)
print("STAGE30_ACTIVE_CADDY_UPSTREAM=EXPECTED",flush=True)' "$SITE" "$expect"
}
https_probe(){
 python3 -B - "$SITE" <<'PY'
import subprocess,sys,time
site=sys.argv[1]
paths=[('/login',200),('/api/reporting/v2/postgresql-summary',401),('/api/bulk-report/status',401)]
for path,want in paths:
 command=[
 'curl','-fsS' if want==200 else '-sS','-o','/dev/null','-w','%{http_code}',
 '--connect-timeout','4','--max-time','8',
 '--resolve',site+':443:127.0.0.1','https://'+site+path
 ]
 started=time.monotonic()
 p=subprocess.run(command,capture_output=True,text=True,timeout=10)
 code=p.stdout.strip()
 elapsed=round(time.monotonic()-started,2)
 print('STAGE30_HTTPS_SMOKE='+path+' STATUS='+code+' SECONDS='+str(elapsed),flush=True)
 if p.returncode or code!=str(want) or elapsed>3.0:
  sys.exit(1)
print('STAGE30_HTTPS_SMOKE=PASS',flush=True)
PY
}
finish(){
 local rc=$?
 trap - EXIT
 if [[ "$CHANGED" == YES && "$SUCCESS" != YES ]];then
  ROLLBACK_ATTEMPTED=YES
  echo "STAGE30_AUTOMATIC_ROLLBACK=STARTED step=$STEP"
  if restore_in_place "$DIR/Caddyfile.original" "$CADDYFILE" && \
     [[ "$(sha "$CADDYFILE")" == "$BASE_CONFIG" ]] && \
     reload_caddy && \
     active_route "$LIVE:8080" && \
     https_probe;then
    echo "STAGE30_AUTOMATIC_ROLLBACK=PASS_OLD_PR129_RESTORED"
  else
    echo "STAGE30_AUTOMATIC_ROLLBACK=CRITICAL_MANUAL_RECOVERY_REQUIRED"
    echo "STAGE30_RECOVERY_ORIGINAL=$DIR/Caddyfile.original"
    echo "STAGE30_RECOVERY_HOST_CADDYFILE=$CADDYFILE"
    rc=99
  fi
 fi
 if [[ -n "$BASE_LIVE" && "$BASE_LIVE" != "$(id "$LIVE" 2>/dev/null)" ]];then
  echo "STAGE30_PREVIOUS_LIVE_CONTAINER_CHANGED=REVIEW_REQUIRED";rc=96
 fi
 if [[ -n "$BASE_TARGET" && "$BASE_TARGET" != "$(id "$TARGET" 2>/dev/null)" ]];then
  echo "STAGE30_RELEASE_TARGET_CHANGED=REVIEW_REQUIRED";rc=97
 fi
 if [[ -n "$BASE_CADDY" && "$BASE_CADDY" != "$(id "$CADDY" 2>/dev/null)" ]];then
  echo "STAGE30_CADDY_CONTAINER_CHANGED=REVIEW_REQUIRED";rc=98
 fi
 if [[ -n "$BASE_FIN" && "$BASE_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_RECORD_COUNTS_CHANGED=CRITICAL";rc=99
 fi
 if ((rc));then
  echo "STAGE30_CONTROLLED_CUTOVER=FAIL_OR_ROLLED_BACK step=$STEP exit=$rc"
 else
  echo "STAGE30_CONTROLLED_CUTOVER=PASS_LIMITED_PR129"
 fi
 echo "STAGE30_FINANCIAL_ENGINE=UNCHANGED"
 echo "STAGE30_FINANCIAL_WRITES_BY_CUTOVER=NONE"
 echo "STAGE30_SELECTED_INVOICE_LOOKUP=DISABLED_AS_TESTED_STAGE30_5"
 echo "STAGE30_AUTHENTICATED_USER_PRODUCTION_E2E=PENDING_STAGE30_7"
 echo "STAGE30_EVIDENCE_DIRECTORY=$DIR"
 exit "$rc"
}
trap finish EXIT

echo "=== A. STRICT OWNER-APPROVED SCOPE, STAGE30.5 EVIDENCE, AND BACKUPS ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
for c in "$LIVE" "$TARGET" "$STAGE" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_REQUIRED_CONTAINER_MISSING=$c";exit 11; }
done
BASE_LIVE="$(id "$LIVE")"
BASE_TARGET="$(id "$TARGET")"
BASE_CADDY="$(id "$CADDY")"
BASE_FIN="$(counts)"
BASE_CONFIG="$(sha "$CADDYFILE")"
[[ -s "$READY/Caddyfile.proposed" && -s "$READY/Caddyfile.original" && -s "$PRIOR" ]] ||
 { echo "STAGE30_APPROVED_RELEASE_EVIDENCE_MISSING=BLOCKED";exit 12; }
[[ "$BASE_CONFIG" == "$(sha "$PRIOR")" ]] &&
[[ "$BASE_CONFIG" == "$(sha "$READY/Caddyfile.original")" ]] ||
 { echo "STAGE30_ORIGINAL_CADDY_CHANGED_SINCE_APPROVAL=BLOCKED";exit 13; }
[[ "$(sha "$READY/Caddyfile.proposed")" == "$EXPECTED_NEW" ]] ||
 { echo "STAGE30_PROPOSED_CADDY_HASH_MISMATCH=BLOCKED";exit 14; }
[[ "$BASE_CONFIG" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]] ||
 { echo "STAGE30_CADDY_MOUNT_HASH_MISMATCH=BLOCKED";exit 15; }
sudo -n docker inspect "$CADDY" --format '{{json .Mounts}}' |
 python3 -B -c 'import json,sys
assert any(x.get("Type")=="bind" and x.get("Destination")=="/etc/caddy/Caddyfile" and x.get("Source")=="/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile" for x in json.load(sys.stdin))'
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.Image}}')" == "$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')" ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.RestartPolicy.Name}}')" == unless-stopped ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.ReadonlyRootfs}}')" == true ]]
[[ -z "$(sudo -n docker port "$TARGET")" ]]
cp "$READY/Caddyfile.original" "$DIR/Caddyfile.original"
cp "$READY/Caddyfile.proposed" "$DIR/Caddyfile.proposed"
chmod 600 "$DIR/"*
echo "STAGE30_STAGE30_5_PINNED_CONFIG_HASH_AND_RESTART_POLICY=PASS"

echo "=== B. VERIFY CADDY ADMIN CONTROL, CURRENT ACTIVE ROUTE, TLS ==="
STEP=ACTIVE_PREFLIGHT
# Preflight must succeed before even considering modifying the mounted Caddyfile.
active_route "$LIVE:8080"
https_probe
echo "STAGE30_PRE_SWITCH_PRODUCTION_TLS_AND_AUTH_GUARDS=PASS"

echo "=== C. ONE EXACT ROUTE CHANGE; NO CHANGE TO ANY OTHER SITE ==="
STEP=ROUTE_CHANGE
sudo -n docker exec -i "$CADDY" caddy validate --config - --adapter caddyfile \
 < "$DIR/Caddyfile.proposed" > "$DIR/validation.log" 2>&1
[[ "$(sha "$CADDYFILE")" == "$BASE_CONFIG" ]] || { echo "STAGE30_CADDY_CHANGED_DURING_GATE=BLOCKED";exit 16; }
CHANGED=YES
restore_in_place "$DIR/Caddyfile.proposed" "$CADDYFILE"
[[ "$(sha "$CADDYFILE")" == "$EXPECTED_NEW" ]] ||
 { echo "STAGE30_HOST_CADDY_CHANGE_HASH=FAIL";exit 17; }
[[ "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" == "$EXPECTED_NEW" ]] ||
 { echo "STAGE30_CADDY_BIND_INODE_NOT_UPDATED=FAIL";exit 18; }
reload_caddy
echo "STAGE30_CADDY_RELOAD=SUCCESS"

echo "=== D. VERIFY ACTIVE SITE ROUTING, TLS, PROTECTED REPORTS ==="
STEP=POSTCUTOVER
active_route "$TARGET:8080"
for round in 1 2 3 4 5;do
 https_probe
 if ((round<5));then sleep 3;fi
done
echo "STAGE30_POSTCUTOVER_TLS_ANONYMOUS_GUARDS=PASS_5_ROUNDS"
[[ "$BASE_FIN" == "$(counts)" ]] || { echo "STAGE30_FINANCIAL_COUNTS_CHANGED=FAIL";exit 19; }
[[ "$BASE_LIVE" == "$(id "$LIVE")" ]]
[[ "$BASE_TARGET" == "$(id "$TARGET")" ]]
[[ "$BASE_CADDY" == "$(id "$CADDY")" ]]
[[ "$(sha "$CADDYFILE")" == "$EXPECTED_NEW" ]]
echo "STAGE30_OLD_LIVE_AND_RELEASE_TARGET_CONTAINER_IDS=UNCHANGED"
echo "STAGE30_FINANCIAL_RECORD_COUNTS=UNCHANGED"
SUCCESS=YES
STEP=COMPLETE
echo "=== STAGE30.6 LIMITED PRODUCTION PR129 ROUTE SWITCH COMPLETE ==="
echo "STAGE30_FINAL_CADDY_ACTIVE_UPSTREAM=$TARGET:8080"
echo "STAGE30_ROLLBACK_COPY=$DIR/Caddyfile.original"
echo "STAGE30_NEXT=OWNER_AUTHENTICATED_USER_PRODUCTION_UI_REPORT_QA_STAGE30_7"
