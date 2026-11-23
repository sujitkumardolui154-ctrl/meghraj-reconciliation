#!/usr/bin/env bash
# SBI Stage30.3: targeted transient timeout isolation — read-only.
# No public routing edits, Gunicorn restart, credential contents, network writes,
# financial writes or production cutover. All probes anonymous and bounded.
set -Eeuo pipefail
umask 077

STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
SOURCE=sbi-pr129-pg-modernui-stage26r2
CANARY=sbi-pr129-modern-release-canary
CADDY=aws_lightsail-caddy-1
NET=sbi_pr129_preview_net
DB=sbi_reconciliation_main
CADDYFILE=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
SNAPSHOT=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID"
chmod 700 "$EVID"
OUTPUT="$EVID/stage30_concurrency_wsgi_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$OUTPUT") 2>&1

BASE_LIVE=""
BASE_CANARY=""
BASE_SOURCE=""
BASE_CADDY=""
BASE_FIN=""
BASE_CONF=""
ISSUES=0

counts(){
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" \
 -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
safe_container_id(){
 sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'
}
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$BASE_LIVE" && "$BASE_LIVE" != "$(safe_container_id "$LIVE" 2>/dev/null)" ]];then
  echo "STAGE30_LIVE_CONTAINER_CHANGED=BLOCKED";rc=91
 fi
 if [[ -n "$BASE_CANARY" && "$BASE_CANARY" != "$(safe_container_id "$CANARY" 2>/dev/null)" ]];then
  echo "STAGE30_CANARY_CONTAINER_CHANGED=BLOCKED";rc=92
 fi
 if [[ -n "$BASE_SOURCE" && "$BASE_SOURCE" != "$(safe_container_id "$SOURCE" 2>/dev/null)" ]];then
  echo "STAGE30_SOURCE_STAGE_CHANGED=BLOCKED";rc=93
 fi
 if [[ -n "$BASE_CADDY" && "$BASE_CADDY" != "$(safe_container_id "$CADDY" 2>/dev/null)" ]];then
  echo "STAGE30_CADDY_CONTAINER_CHANGED=BLOCKED";rc=94
 fi
 if [[ -n "$BASE_FIN" && "$BASE_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_COUNTS_CHANGED=BLOCKED";rc=95
 fi
 if [[ -n "$BASE_CONF" && "$BASE_CONF" != "$(sudo -n sha256sum "$CADDYFILE" 2>/dev/null | awk '{print $1}')" ]];then
  echo "STAGE30_CADDY_CONFIG_CHANGED=BLOCKED";rc=96
 fi
 if ((ISSUES>0));then
  echo "STAGE30_CONCURRENCY_FAILURE_GROUPS=$ISSUES"
  if ((rc==0));then rc=35;fi
 fi
 if ((rc));then echo "STAGE30_CONCURRENCY_WSGI_DIAGNOSTIC=FAIL step=$STEP exit=$rc"
 else echo "STAGE30_CONCURRENCY_WSGI_DIAGNOSTIC=PASS_LIMITED_OBSERVATION";fi
 echo "STAGE30_TIMEOUT_ROOT_CAUSE=NOT_YET_DETERMINED"
 echo "STAGE30_PRODUCTION_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_CADDY_CHANGE=NONE"
 echo "STAGE30_FINANCIAL_WRITES=NONE"
 echo "STAGE30_RELEASE_GATE=BLOCKED_PENDING_ROOT_CAUSE_SUSTAINED_STABILITY_AND_ROLLBACK"
 echo "STAGE30_EVIDENCE_FILE=$OUTPUT"
 exit "$rc"
}
trap finish EXIT

echo "=== A. STRICT FINANCIAL, CANARY, CADDY BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$SOURCE" "$CANARY" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_NOT_RUNNING=$c";exit 11; }
done
BASE_LIVE="$(safe_container_id "$LIVE")"
BASE_CANARY="$(safe_container_id "$CANARY")"
BASE_SOURCE="$(safe_container_id "$SOURCE")"
BASE_CADDY="$(safe_container_id "$CADDY")"
BASE_CONF="$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')"
BASE_FIN="$(counts)"
[[ -s "$SNAPSHOT" && "$BASE_CONF" == "$(sha256sum "$SNAPSHOT" | awk '{print $1}')" ]] ||
 { echo "STAGE30_CADDY_ORIGINAL_SNAPSHOT_CHANGED=BLOCKED";exit 12; }
[[ "$BASE_CONF" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.Image}}')" == "$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')" ]]
echo "STAGE30_SOURCE_AND_RELEASE_SECURITY_BASELINE=PASS"

echo "=== B. HOST RESOURCE PRESSURE — NUMERIC VALUES ONLY ==="
STEP=RESOURCE
python3 -B - <<'PY'
from pathlib import Path
lines=Path('/proc/meminfo').read_text().splitlines()
values={}
for line in lines:
 if ':' not in line:continue
 k,v=line.split(':',1)
 if k in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):
  values[k]=int(v.strip().split()[0])
for k in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):
 print('STAGE30_HOST_'+k.upper()+'_KIB='+str(values.get(k,-1)))
print('STAGE30_HOST_MEMORY_PRESSURE=RECORDED_NOT_PROVEN')
PY
echo "STAGE30_CANARY_RESTART_COUNT=$(sudo -n docker inspect "$CANARY" --format '{{.RestartCount}}')"
sudo -n docker stats --no-stream --format 'STAGE30_CONTAINER_RESOURCE={{.Name}} CPU={{.CPUPerc}} MEM={{.MemUsage}} PIDS={{.PIDs}}' "$CANARY" "$LIVE"

echo "=== C. IN-PROCESS FLASK TEST CLIENT VS GUNICORN NETWORK ==="
STEP=WSGI
if sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
import time,sys
start=time.monotonic()
from app import app
print("STAGE30_WSGI_IMPORT_SECONDS="+str(round(time.monotonic()-start,3)),flush=True)
client=app.test_client()
targets=[
 ('login','/login',{200}),
 ('postgresql-summary','/api/reporting/v2/postgresql-summary',{401,403}),
 ('bulk-status','/api/bulk-report/status',{401,403}),
]
bad=0
for round_no in range(1,4):
 for name,path,allowed in targets:
  start=time.monotonic()
  try:
   status=client.get(path).status_code
  except Exception as exc:
   status=type(exc).__name__
  elapsed=round(time.monotonic()-start,3)
  print("STAGE30_WSGI_RESULT=round:"+str(round_no)+" route:"+name+" status:"+str(status)+" seconds:"+str(elapsed),flush=True)
  if status not in allowed:bad+=1
print('STAGE30_WSGI_FAILURES='+str(bad),flush=True)
sys.exit(0 if bad==0 else 32)
PY
then
 echo "STAGE30_WSGI_ANONYMOUS_CONTRACT=PASS"
else
 echo "STAGE30_WSGI_ANONYMOUS_CONTRACT=FAIL"
 ISSUES=$((ISSUES+1))
fi

echo "=== D. 4-CONCURRENT-REQUEST PROBE FROM PRIVATE CADDY NETWORK ==="
STEP=NETWORK_PROBE
IMAGE="$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')"
if sudo -n docker run --rm -i --network "$NET" \
 --read-only --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" --entrypoint python3 "$IMAGE" \
 -B - "$CANARY" "$LIVE" <<'PY'
import sys,time,http.client,concurrent.futures
canary,live=sys.argv[1:]
cases=[
 ('login','/login',{200}),
 ('postgresql-summary','/api/reporting/v2/postgresql-summary',{401,403}),
 ('bulk-status','/api/bulk-report/status',{401,403}),
 ('login-second','/login',{200})
]
def call(host,item):
 name,path,expected=item
 code=None
 started=time.monotonic()
 conn=http.client.HTTPConnection(host,8080,timeout=6)
 try:
  conn.request('GET',path,headers={'Connection':'close'})
  res=conn.getresponse()
  code=res.status
  res.read(512)
 except (OSError,http.client.HTTPException) as exc:
  code=type(exc).__name__
 finally:
  conn.close()
 return name,code,round(time.monotonic()-started,2),code in expected
bad=0
for round_no in range(1,5):
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  futures=[pool.submit(call,canary,item) for item in cases]
  results=[future.result() for future in futures]
 for name,code,elapsed,valid in results:
  print('STAGE30_CONCURRENT_CANARY=round:'+str(round_no)+' route:'+name+
        ' status:'+str(code)+' seconds:'+str(elapsed),flush=True)
  if not valid:bad+=1
 # Do not load-test production; only one sequential baseline per round.
 name,code,elapsed,valid=call(live,('login','/login',{200}))
 print('STAGE30_LIVE_BASELINE=round:'+str(round_no)+' route:login status:'+str(code)+' seconds:'+str(elapsed),flush=True)
 if not valid:bad+=1
 if round_no<4:time.sleep(2)
print('STAGE30_CONCURRENT_HTTP_FAILURES='+str(bad),flush=True)
sys.exit(0 if bad==0 else 33)
PY
then
 echo "STAGE30_PRIVATE_NETWORK_4_CONCURRENT_READS=PASS_4_ROUNDS"
else
 echo "STAGE30_PRIVATE_NETWORK_4_CONCURRENT_READS=FAIL"
 ISSUES=$((ISSUES+1))
fi

echo "=== E. POST-TEST SOURCE/FINANCIAL/CADDY IMMUTABILITY ==="
STEP=STABILITY
[[ "$BASE_LIVE" == "$(safe_container_id "$LIVE")" ]]
[[ "$BASE_CANARY" == "$(safe_container_id "$CANARY")" ]]
[[ "$BASE_SOURCE" == "$(safe_container_id "$SOURCE")" ]]
[[ "$BASE_CADDY" == "$(safe_container_id "$CADDY")" ]]
[[ "$BASE_FIN" == "$(counts)" ]]
[[ "$BASE_CONF" == "$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')" ]]
echo "STAGE30_CADDY_LIVE_FINANCIAL_IMMUTABILITY=PASS"
STEP=COMPLETE
echo "STAGE30_WSGI_AND_NETWORK_COMPARISON=COMPLETE"
echo "STAGE30_NEXT=ISOLATE_REQUEST_LATENCY_OR_WORKER_SCHEDULING_WITH_INSTRUMENTED_PRIVATE_CANDIDATE"
