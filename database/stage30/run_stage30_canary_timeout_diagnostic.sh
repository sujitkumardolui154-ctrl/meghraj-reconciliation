#!/usr/bin/env bash
# Stage 30: diagnose intermittent canary HTTP timeouts WITHOUT changing live routing.
# Executes short local/network/stress probes; no financial writes, no container restart.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-modernui-stage26r2
CANARY=sbi-pr129-modern-release-canary
CADDY=aws_lightsail-caddy-1
DB=sbi_reconciliation_main
NET=sbi_pr129_preview_net
CADDYFILE=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
PREVIOUS=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
OUTPUT="$EVID/stage30_timeout_diagnostic_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$OUTPUT") 2>&1
BASE_LIVE=""
BASE_CADDY=""
BASE_CANARY=""
BASE_FIN=""
BASE_CONF=""
counts(){
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" \
 -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$BASE_LIVE" && "$BASE_LIVE" != "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_LIVE_PR129_CHANGED=REVIEW_REQUIRED";rc=90
 fi
 if [[ -n "$BASE_CADDY" && "$BASE_CADDY" != "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_CADDY_CONTAINER_CHANGED=REVIEW_REQUIRED";rc=91
 fi
 if [[ -n "$BASE_CANARY" && "$BASE_CANARY" != "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_CANARY_STATE_CHANGED=REVIEW_REQUIRED";rc=92
 fi
 if [[ -n "$BASE_FIN" && "$BASE_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";rc=93
 fi
 if [[ -n "$BASE_CONF" && "$BASE_CONF" != "$(sudo -n sha256sum "$CADDYFILE" 2>/dev/null | awk '{print $1}')" ]];then
  echo "STAGE30_CADDY_CONFIG_CHANGED=REVIEW_REQUIRED";rc=94
 fi
 if ((rc));then
  echo "STAGE30_CANARY_STABILITY_DIAGNOSTIC=FAIL step=$STEP exit=$rc"
 else
  echo "STAGE30_CANARY_STABILITY_DIAGNOSTIC=PASS_SHORT_WINDOW"
 fi
 echo "STAGE30_RELEASE_STATUS=BLOCKED_PENDING_VERIFIED_SUSTAINED_STABILITY_AND_EXECUTABLE_ROLLBACK"
 echo "STAGE30_CADDY_ROUTE_CHANGE=NONE"
 echo "STAGE30_LIVE_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_FINANCIAL_WRITES_BY_DIAGNOSTIC=NONE"
 echo "STAGE30_EVIDENCE_FILE=$OUTPUT"
 exit "$rc"
}
trap finish EXIT

echo "=== A. VERIFY CADDY AND FINANCIAL BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$STAGE" "$CANARY" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
BASE_LIVE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CADDY="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CANARY="$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_FIN="$(counts)"
BASE_CONF="$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')"
[[ "$BASE_CONF" == "$(sha256sum "$PREVIOUS" | awk '{print $1}')" ]] ||
 { echo "STAGE30_CADDY_SNAPSHOT_MISMATCH=BLOCKED";exit 12; }
[[ "$BASE_CONF" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.Image}}')" == "$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')" ]]
echo "STAGE30_LIVE_CONFIG_FINANCIAL_BASELINE=PASS"
echo "STAGE30_PRIVATE_CANARY_IDENTITY=PASS"

echo "=== B. CANARY RESOURCE AND PROCESS HEALTH (NO ENV OR LOG VALUES) ==="
STEP=RESOURCES
echo "STAGE30_CANARY_RESTARTS=$(sudo -n docker inspect "$CANARY" --format '{{.RestartCount}}')"
echo "STAGE30_CANARY_STARTED_AT=$(sudo -n docker inspect "$CANARY" --format '{{.State.StartedAt}}')"
echo "STAGE30_CANARY_HEALTH_STATUS=$(sudo -n docker inspect "$CANARY" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}NO_DOCKER_HEALTHCHECK{{end}}')"
sudo -n docker stats --no-stream --format 'STAGE30_CONTAINER_RESOURCES={{.Name}} CPU={{.CPUPerc}} MEMORY={{.MemUsage}} PIDS={{.PIDs}}' "$CANARY" "$LIVE"
sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
from pathlib import Path
p=Path("/proc/1/status")
if p.exists():
 entries={}
 for line in p.read_text().splitlines():
  if ":" in line:
   k,v=line.split(":",1)
   if k in ("Name","State","Threads","VmRSS","voluntary_ctxt_switches","nonvoluntary_ctxt_switches"):
    entries[k]=v.strip()
 for key in ("Name","State","Threads","VmRSS"):
  print("STAGE30_CANARY_PID1_"+key.upper()+"="+entries.get(key,"UNKNOWN"))
PY
echo "STAGE30_LOG_EXCEPTION_COUNTS_ONLY=BEGIN"
# Never echo raw logs; summarize exception class strings, not messages, URLs, cookies, or tokens.
sudo -n docker logs --since 30m "$CANARY" 2>&1 |
python3 -B -c 'import sys,re
s=sys.stdin.read()
terms=("TimeoutError","ConnectionError","OperationalError","DefaultCredentialsError","Traceback","Worker timeout","BrokenPipeError")
for x in terms:print("STAGE30_LOG_MARKER_"+re.sub("[^A-Z0-9]","_",x.upper())+"="+str(s.count(x)))
print("STAGE30_RAW_LOG_CONTENT=NOT_DISPLAYED")'

echo "=== C. CANARY LOCAL PROBE: 5 ROUNDS, EACH ENDPOINT <= 4 SECONDS ==="
STEP=LOCAL_PROBE
sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
import http.client, time, socket, sys
targets=[
 ('login','/login',{200}),
 ('postgresql-summary','/api/reporting/v2/postgresql-summary',{401,403}),
 ('bulk-status','/api/bulk-report/status',{401,403}),
]
fail=0
for i in range(1,6):
 for name,path,allowed in targets:
  started=time.monotonic()
  code=None
  error=""
  conn=http.client.HTTPConnection("127.0.0.1",8080,timeout=4)
  try:
   conn.request("GET",path,headers={"Connection":"close"})
   resp=conn.getresponse()
   code=resp.status
   resp.read(2048)
  except (OSError,http.client.HTTPException) as ex:
   error=type(ex).__name__
  finally:conn.close()
  elapsed=round(time.monotonic()-started,2)
  state=str(code) if code is not None else error
  print("STAGE30_LOCAL_PROBE=round:"+str(i)+" route:"+name+" status:"+state+" seconds:"+str(elapsed),flush=True)
  if code not in allowed:fail+=1
 if i<5:time.sleep(3)
print("STAGE30_LOCAL_PROBE_FAILURES="+str(fail))
if fail:sys.exit(31)
print("STAGE30_LOCAL_HTTP_STABILITY=PASS_5_ROUNDS")
PY

echo "=== D. SAME-NETWORK REMOTE PROBE FROM INDEPENDENT TEST CLIENT ==="
STEP=NETWORK_PROBE
IMAGE="$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')"
sudo -n docker run --rm -i \
 --network "$NET" \
 --read-only --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" \
 --entrypoint python3 "$IMAGE" -B - "$CANARY" "$LIVE" <<'PY'
import http.client,time,sys
canary,live=sys.argv[1:]
checks=[
 (canary,'/login',{200}),
 (canary,'/api/reporting/v2/postgresql-summary',{401,403}),
 (canary,'/api/bulk-report/status',{401,403}),
 (live,'/login',{200}),
]
errors=0
for i in range(1,5):
 for host,path,allowed in checks:
  conn=http.client.HTTPConnection(host,8080,timeout=4)
  status=None
  started=time.monotonic()
  try:
   conn.request('GET',path,headers={"Connection":"close"})
   response=conn.getresponse()
   status=response.status
   response.read(1024)
  except (OSError,http.client.HTTPException) as ex:
   status=type(ex).__name__
  finally:conn.close()
  name="LIVE" if host==live else "CANARY"
  print("STAGE30_NETWORK_PROBE=round:"+str(i)+" service:"+name+" route:"+path.rsplit('/',1)[-1]+" status:"+str(status)+" seconds:"+str(round(time.monotonic()-started,2)),flush=True)
  if status not in allowed:errors+=1
 if i<4:time.sleep(3)
print("STAGE30_NETWORK_PROBE_FAILURES="+str(errors))
if errors:sys.exit(32)
print("STAGE30_CADDY_NETWORK_HTTP_STABILITY=PASS_4_ROUNDS")
PY

echo "=== E. FINAL NO CHANGE TO LIVE, CADDY AND FINANCIAL DATABASE ==="
STEP=STABILITY
[[ "$BASE_LIVE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CADDY" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CANARY" == "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_FIN" == "$(counts)" ]]
[[ "$BASE_CONF" == "$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')" ]]
echo "STAGE30_LIVE_AND_CADDY_IMMUTABILITY=PASS"
echo "STAGE30_FINANCIAL_COUNTS_UNCHANGED=PASS"
STEP=COMPLETE
echo "=== FINAL CANARY HTTP STABILITY DIAGNOSTIC ==="
echo "STAGE30_LOCAL_STABILITY=PASS_5_ROUNDS"
echo "STAGE30_NETWORK_STABILITY=PASS_4_ROUNDS"
echo "STAGE30_ANONYMOUS_REPORT_ACCESS=DENIED"
echo "STAGE30_RESTART_ACTION=NOT_PERFORMED"
echo "STAGE30_CANARY_NETWORK=UNCHANGED"
echo "STAGE30_NEXT=REVIEW_TRANSIENT_CAUSE_AND_LONGER_DURATION_RELEASE_STABILITY"
