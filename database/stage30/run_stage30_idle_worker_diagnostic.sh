#!/usr/bin/env bash
# SBI Stage 30.1 - idle-period timeout root-cause diagnostic (NO CUTOVER)
# Distinguish first-request-after-idle stalls from repeated/active HTTP failures.
# No live routing/network/container changes, financial DB writes, credential output,
# or Gunicorn worker restarts. Bounded request volume and timeouts.
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
OUTPUT="$EVID/stage30_idle_probe_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$OUTPUT") 2>&1
BASE_LIVE=""
BASE_CADDY=""
BASE_CANARY=""
BASE_FIN=""
BASE_CONF=""
FAILURES=0
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$BASE_LIVE" && "$BASE_LIVE" != "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_LIVE_CONTAINER_CHANGED=REVIEW_REQUIRED";rc=91
 fi
 if [[ -n "$BASE_CADDY" && "$BASE_CADDY" != "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_CADDY_CONTAINER_CHANGED=REVIEW_REQUIRED";rc=92
 fi
 if [[ -n "$BASE_CANARY" && "$BASE_CANARY" != "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_CANARY_CONTAINER_CHANGED=REVIEW_REQUIRED";rc=93
 fi
 if [[ -n "$BASE_FIN" && "$BASE_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";rc=94
 fi
 if [[ -n "$BASE_CONF" && "$BASE_CONF" != "$(sudo -n sha256sum "$CADDYFILE" 2>/dev/null | awk '{print $1}')" ]];then
  echo "STAGE30_CADDY_CONFIG_CHANGED=REVIEW_REQUIRED";rc=95
 fi
 if ((FAILURES));then
  echo "STAGE30_HTTP_REQUEST_FAILURES_RECORDED=$FAILURES"
  [[ "$rc" -ne 0 ]] || rc=30
 fi
 if ((rc));then
  echo "STAGE30_IDLE_STABILITY_QA=FAIL step=$STEP exit=$rc"
 else
  echo "STAGE30_IDLE_STABILITY_QA=PASS_LIMITED_OBSERVATION"
 fi
 echo "STAGE30_RELEASE_GATE=BLOCKED_PENDING_ROOT_CAUSE_AND_LONG_DURATION_STABILITY"
 echo "STAGE30_LIVE_PR129_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_CADDY_CHANGE=NONE"
 echo "STAGE30_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_EVIDENCE_FILE=$OUTPUT"
 exit "$rc"
}
trap finish EXIT

echo "=== A. PROTECT PRODUCTION/PRIVATE CANDIDATE FINANCIAL BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$STAGE" "$CANARY" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
  { echo "REQUIRED_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
BASE_LIVE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CADDY="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CANARY="$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_FIN="$(counts)"
BASE_CONF="$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')"
[[ -s "$PREVIOUS" && "$BASE_CONF" == "$(sha256sum "$PREVIOUS" | awk '{print $1}')" ]] ||
 { echo "STAGE30_HISTORICAL_CADDY_SNAPSHOT_MISMATCH=BLOCKED";exit 12; }
[[ "$BASE_CONF" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.Image}}')" == "$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')" ]]
echo "STAGE30_PREVIOUS_RELEASE_GATES=UNCHANGED_PASS"

echo "=== B. SAFE PROCESS/WORKER INVENTORY; NO ENV, LOG CONTENT OR ARGS ==="
STEP=WORKERS
sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
from pathlib import Path
from collections import Counter
states=Counter()
names=Counter()
for p in Path('/proc').iterdir():
 if not p.name.isdecimal():
  continue
 try:
  lines=(p/'status').read_text().splitlines()
 except (OSError,PermissionError):
  continue
 fields={k:v.strip() for k,v in (line.split(':',1) for line in lines if ':' in line)}
 name=fields.get('Name','UNKNOWN')
 if name.startswith(('gunicorn','python')):
  names[name]+=1
  states[fields.get('State','UNKNOWN')]+=1
for k,v in sorted(names.items()):
 print('STAGE30_PROCESS_NAME_'+k.replace(' ','_')+'='+str(v))
for k,v in sorted(states.items()):
 print('STAGE30_PROCESS_STATE_'+k.replace(' ','_')+'='+str(v))
print('STAGE30_PROCESS_DETAILS=SANITIZED')
PY
echo "STAGE30_CANARY_RESTARTS=$(sudo -n docker inspect "$CANARY" --format '{{.RestartCount}}')"
sudo -n docker stats --no-stream --format 'STAGE30_RESOURCE={{.Name}} CPU={{.CPUPerc}} MEMORY={{.MemUsage}} PIDS={{.PIDs}}' "$CANARY" "$LIVE"
echo "STAGE30_RESOURCE_SNAPSHOT=RECORDED"

echo "=== C. BASELINE ACTIVE CANARY AND LIVE HTTP RESPONSES ==="
STEP=ACTIVE
IMAGE="$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')"
# Only standard-library Python; no app imports and no credential mounts.
# Each request is bounded to 6 seconds and reads at most 512 response bytes.
probe_py=$(cat <<'PY'
import http.client,sys,time
mode,round_name,canary,live=sys.argv[1:]
targets=[
 (canary,'/login',{200}),
 (canary,'/api/reporting/v2/postgresql-summary',{401,403}),
 (canary,'/api/bulk-report/status',{401,403}),
 (live,'/login',{200}),
]
fail=0
for host,path,expected in targets:
 started=time.monotonic()
 code=None
 error=''
 c=http.client.HTTPConnection(host,8080,timeout=6)
 try:
  c.request('GET',path,headers={'Connection':'close'})
  response=c.getresponse()
  code=response.status
  response.read(512)
 except (OSError,http.client.HTTPException) as exc:
  error=type(exc).__name__
 finally:
  c.close()
 elapsed=round(time.monotonic()-started,2)
 state=str(code) if code is not None else error
 name='LIVE' if host==live else 'CANARY'
 endpoint=path.rsplit('/',1)[-1] or 'root'
 print('STAGE30_HTTP_PROBE='+mode+' round:'+round_name+' service:'+name+' route:'+endpoint+' status:'+state+' seconds:'+str(elapsed),flush=True)
 if code not in expected:fail+=1
print('STAGE30_HTTP_PROBE_FAILURES='+mode+' round:'+round_name+' count:'+str(fail),flush=True)
if fail:sys.exit(31)
PY
)
probe(){
 local label="$1"
 local round="$2"
 if printf '%s\n' "$probe_py" | sudo -n docker run --rm -i \
  --network "$NET" --read-only --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user "$(id -u):$(id -g)" --entrypoint python3 "$IMAGE" \
  -B - "$label" "$round" "$CANARY" "$LIVE";then
   echo "STAGE30_HTTP_ROUND=$label/$round PASS"
 else
   FAILURES=$((FAILURES+1))
   echo "STAGE30_HTTP_ROUND=$label/$round FAILED"
 fi
}
probe ACTIVE 1
probe ACTIVE 2

echo "=== D. WAIT WITHOUT REQUESTS TO CANARY, THEN FIRST-REQUEST PROBE ==="
STEP=IDLE
echo "STAGE30_IDLE_QUIET_PERIOD_SECONDS=45"
sleep 45
probe AFTER_IDLE_45S 1
probe FOLLOWUP 1
echo "STAGE30_SECOND_IDLE_QUIET_PERIOD_SECONDS=75"
sleep 75
probe AFTER_IDLE_75S 1
probe FOLLOWUP 2

echo "=== E. CHECK FOR CANARY AND LIVE RESTARTS, WITHOUT PRINTING LOGS ==="
STEP=REST
echo "STAGE30_CANARY_RESTARTS_AFTER=$(sudo -n docker inspect "$CANARY" --format '{{.RestartCount}}')"
echo "STAGE30_LIVE_RESTARTS_AFTER=$(sudo -n docker inspect "$LIVE" --format '{{.RestartCount}}')"
sudo -n docker stats --no-stream --format 'STAGE30_RESOURCE_AFTER={{.Name}} CPU={{.CPUPerc}} MEMORY={{.MemUsage}} PIDS={{.PIDs}}' "$CANARY" "$LIVE"

echo "=== F. PROTECT LIVE AND SOURCE FINANCIAL STATE ==="
STEP=STABILITY
[[ "$BASE_LIVE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CADDY" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CANARY" == "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_FIN" == "$(counts)" ]]
[[ "$BASE_CONF" == "$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')" ]]
echo "STAGE30_LIVE_CADDY_AND_FINANCIAL_COUNTS_UNCHANGED=PASS"
STEP=COMPLETE
echo "STAGE30_IDLE_OBSERVATION=COMPLETE"
echo "STAGE30_INTERMITTENT_ROOT_CAUSE=REQUIRES_REVIEW"
echo "NEXT=COMPARE_AFTER_IDLE_RESPONSE_WITH_ACTIVE_AND_LIVE_BASELINES"
