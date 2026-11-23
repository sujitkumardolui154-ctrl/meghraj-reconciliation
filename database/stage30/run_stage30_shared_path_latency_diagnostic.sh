#!/usr/bin/env bash
# SBI Stage 30.4 — shared host vs Docker HTTP latency isolation.
# No network changes, no production Caddy change, no container restarts,
# no credential reads, no financial writes. Uses Python stdlib on AWS host.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
SOURCE=sbi-pr129-pg-modernui-stage26r2
CANARY=sbi-pr129-modern-release-canary
CADDY=aws_lightsail-caddy-1
NET=sbi_pr129_preview_net
DB=sbi_reconciliation_main
CADDYHOST=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
BACKUP=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
OUT="$EVID/stage30_shared_path_latency_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$OUT") 2>&1
B_LIVE=""
B_CANARY=""
B_SOURCE=""
B_CADDY=""
B_CONF=""
B_FIN=""
ERRORS=0
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
identity(){ sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'; }
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$B_LIVE" && "$B_LIVE" != "$(identity "$LIVE" 2>/dev/null)" ]];then
  echo "STAGE30_LIVE_CHANGED=REVIEW_REQUIRED";rc=91;fi
 if [[ -n "$B_CANARY" && "$B_CANARY" != "$(identity "$CANARY" 2>/dev/null)" ]];then
  echo "STAGE30_CANARY_CHANGED=REVIEW_REQUIRED";rc=92;fi
 if [[ -n "$B_SOURCE" && "$B_SOURCE" != "$(identity "$SOURCE" 2>/dev/null)" ]];then
  echo "STAGE30_STAGE26_CHANGED=REVIEW_REQUIRED";rc=93;fi
 if [[ -n "$B_CADDY" && "$B_CADDY" != "$(identity "$CADDY" 2>/dev/null)" ]];then
  echo "STAGE30_CADDY_CHANGED=REVIEW_REQUIRED";rc=94;fi
 if [[ -n "$B_CONF" && "$B_CONF" != "$(sudo -n sha256sum "$CADDYHOST" 2>/dev/null | awk '{print $1}')" ]];then
  echo "STAGE30_CADDYFILE_CHANGED=REVIEW_REQUIRED";rc=95;fi
 if [[ -n "$B_FIN" && "$B_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";rc=96;fi
 if ((ERRORS));then
  echo "STAGE30_HTTP_FAILURE_GROUPS=$ERRORS"
  if ((rc==0));then rc=35;fi
 fi
 if ((rc));then
  echo "STAGE30_SHARED_PATH_QA=FAIL step=$STEP exit=$rc"
 else
  echo "STAGE30_SHARED_PATH_QA=PASS_SHORT_WINDOW_DIAGNOSTIC"
 fi
 echo "STAGE30_OWNER_SCOPE_APPROVAL=RECEIVED_CONDITIONAL"
 echo "STAGE30_CADDY_ROUTE_CHANGE=NONE"
 echo "STAGE30_PRODUCTION_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_RELEASE_GATE=BLOCKED_PENDING_ROOT_CAUSE_AND_LONG_DURATION_STABILITY"
 echo "STAGE30_EVIDENCE_FILE=$OUT"
 exit "$rc"
}
trap finish EXIT

echo "=== A. EXISTING LIVE AND FINANCIAL DATA BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$SOURCE" "$CANARY" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
  { echo "STAGE30_REQUIRED_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
B_LIVE="$(identity "$LIVE")"
B_CANARY="$(identity "$CANARY")"
B_SOURCE="$(identity "$SOURCE")"
B_CADDY="$(identity "$CADDY")"
B_FIN="$(counts)"
B_CONF="$(sudo -n sha256sum "$CADDYHOST" | awk '{print $1}')"
[[ -f "$BACKUP" && "$B_CONF" == "$(sha256sum "$BACKUP" | awk '{print $1}')" ]] ||
  { echo "STAGE30_SAVED_CADDY_ROLLBACK_BASELINE_MISMATCH=BLOCKED";exit 12; }
[[ "$B_CONF" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.Image}}')" == "$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')" ]]
echo "STAGE30_PROTECTED_LIVE_CANARY_AND_DATABASE=PASS"

echo "=== B. DISCOVER DIRECT CONTAINER IP ADDRESSES ON EXISTING PRIVATE NETWORK ==="
STEP=NETWORK
CIP="$(sudo -n docker inspect "$CANARY" --format "{{with index .NetworkSettings.Networks \"$NET\"}}{{.IPAddress}}{{end}}")"
LIP="$(sudo -n docker inspect "$LIVE" --format "{{with index .NetworkSettings.Networks \"$NET\"}}{{.IPAddress}}{{end}}")"
[[ "$CIP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$LIP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
  { echo "STAGE30_DIRECT_BRIDGE_IP_DISCOVERY=BLOCKED";exit 13; }
echo "STAGE30_CANARY_BRIDGE_IP=$CIP"
echo "STAGE30_LIVE_BRIDGE_IP=$LIP"
echo "STAGE30_BOTH_CONTAINERS_NETWORK=$NET"
echo "STAGE30_NETWORK_MODIFICATIONS=NONE"

echo "=== C. AWS HOST DIRECT BRIDGE HTTP, NO DOCKER TEST-CONTAINER STARTUP ==="
STEP=HOST_HTTP
if python3 -B - "$CIP" "$LIP" <<'PY'
import sys,http.client,time,concurrent.futures
canary,live=sys.argv[1:]
cases=[
 ('CANARY_LOGIN',canary,'/login',{200}),
 ('CANARY_REPORT',canary,'/api/reporting/v2/postgresql-summary',{401,403}),
 ('CANARY_BULK',canary,'/api/bulk-report/status',{401,403}),
 ('LIVE_LOGIN',live,'/login',{200}),
]
def query(target):
 label,host,path,expected=target
 start=time.monotonic()
 code=None
 c=http.client.HTTPConnection(host,8080,timeout=6)
 try:
  c.request('GET',path,headers={'Connection':'close'})
  response=c.getresponse()
  code=response.status
  response.read(512)
 except (OSError,http.client.HTTPException) as exc:
  code=type(exc).__name__
 finally:c.close()
 dt=round(time.monotonic()-start,2)
 return label,code,dt,code in expected
errors=0
# A few bounded concurrent reads; do not stress production.
for round_n in range(1,5):
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  results=list(pool.map(query,cases))
 for label,code,elapsed,ok in results:
  print('STAGE30_DIRECT_BRIDGE_HTTP=round:'+str(round_n)+' route:'+label+
        ' status:'+str(code)+' seconds:'+str(elapsed),flush=True)
  if not ok:errors+=1
 if round_n<4:time.sleep(2)
print('STAGE30_DIRECT_BRIDGE_HTTP_FAILURES='+str(errors),flush=True)
sys.exit(0 if errors==0 else 31)
PY
then echo "STAGE30_AWS_HOST_DIRECT_BRIDGE_QA=PASS"
else
 echo "STAGE30_AWS_HOST_DIRECT_BRIDGE_QA=FAIL_OR_NETWORK_RESTRICTED"
 ERRORS=$((ERRORS+1))
fi

echo "=== D. IN-CANARY LOOPBACK HTTP, NO NEW CONTAINERS ==="
STEP=LOOPBACK
if sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
import http.client,time,sys
cases=[('LOGIN','/login',{200}),
       ('REPORT','/api/reporting/v2/postgresql-summary',{401,403}),
       ('BULK','/api/bulk-report/status',{401,403})]
errors=0
for round_n in range(1,5):
 for label,path,expected in cases:
  conn=http.client.HTTPConnection('127.0.0.1',8080,timeout=6)
  code=None
  start=time.monotonic()
  try:
   conn.request('GET',path,headers={'Connection':'close'})
   resp=conn.getresponse();code=resp.status;resp.read(512)
  except (OSError,http.client.HTTPException) as ex:code=type(ex).__name__
  finally:conn.close()
  print('STAGE30_CANARY_LOOPBACK_HTTP=round:'+str(round_n)+' route:'+label+
        ' status:'+str(code)+' seconds:'+str(round(time.monotonic()-start,2)),flush=True)
  if code not in expected:errors+=1
 if round_n<4:time.sleep(2)
print('STAGE30_CANARY_LOOPBACK_FAILURES='+str(errors),flush=True)
sys.exit(0 if errors==0 else 32)
PY
then echo "STAGE30_CANARY_LOOPBACK_QA=PASS"
else
 echo "STAGE30_CANARY_LOOPBACK_QA=FAIL"
 ERRORS=$((ERRORS+1))
fi

echo "=== E. DOCKER CLIENT STARTUP AND DNS QUERIES ONLY (NO HTTP) ==="
STEP=DNS
IMAGE="$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')"
if sudo -n docker run --rm -i --network "$NET" \
 --read-only --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" \
 --entrypoint python3 "$IMAGE" -B - "$CANARY" "$LIVE" <<'PY'
import socket,time,sys
for host in sys.argv[1:]:
 for n in range(1,4):
  start=time.monotonic()
  try:addr=socket.getaddrinfo(host,8080,type=socket.SOCK_STREAM);state='PASS' if addr else 'EMPTY'
  except OSError as exc:state=type(exc).__name__
  elapsed=round(time.monotonic()-start,3)
  label='CANARY' if 'canary' in host else 'LIVE'
  print('STAGE30_DOCKER_DNS='+label+' round:'+str(n)+' status:'+state+' seconds:'+str(elapsed),flush=True)
  if state!='PASS':sys.exit(34)
PY
then echo "STAGE30_DOCKER_DNS_QA=PASS"
else
 echo "STAGE30_DOCKER_DNS_QA=FAIL"
 ERRORS=$((ERRORS+1))
fi

echo "=== F. STABILITY: NO PRODUCTION, CADDY, DATABASE OR CANARY CHANGES ==="
STEP=STABILITY
[[ "$B_LIVE" == "$(identity "$LIVE")" ]]
[[ "$B_CANARY" == "$(identity "$CANARY")" ]]
[[ "$B_SOURCE" == "$(identity "$SOURCE")" ]]
[[ "$B_CADDY" == "$(identity "$CADDY")" ]]
[[ "$B_CONF" == "$(sudo -n sha256sum "$CADDYHOST" | awk '{print $1}')" ]]
[[ "$B_FIN" == "$(counts)" ]]
echo "STAGE30_PRODUCTION_CADDY_FINANCIAL_IMMUTABILITY=PASS"
STEP=COMPLETE
echo "STAGE30_NEXT=CORRELATE_DIRECT_BRIDGE_VS_LOOPBACK_VS_DNS_LATENCY"
