#!/usr/bin/env bash
# Stage 30.8B — attribution of intermittent PR129 /login response stalls.
# Read-only. Does not alter Caddy, containers, network, database or credentials.
set -Eeuo pipefail
umask 077
STEP=START
SITE=pr129.13-232-241-221.sslip.io
TARGET=sbi-pr129-modern-release-final
LIVE=sbi-bulk-report-pr129-https-preview
CADDY=aws_lightsail-caddy-1
DB=sbi_reconciliation_main
NET=sbi_pr129_preview_net
HOST_CADDY=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
EXPECTED_SHA=61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
OUT="$EVID/stage30_8b_edge_vs_backend_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$OUT") 2>&1
B_LIVE=""
B_TARGET=""
B_CADDY=""
B_CONFIG=""
B_FIN=""
PROBE_EXIT=0

ident(){ sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'; }
counts(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
finish(){
 local rc=$?
 trap - EXIT
 [[ -z "$B_LIVE" || "$B_LIVE" == "$(ident "$LIVE" 2>/dev/null)" ]] ||
 { echo "STAGE30_8B_OLD_PR129_CHANGED=REVIEW_REQUIRED";rc=91; }
 [[ -z "$B_TARGET" || "$B_TARGET" == "$(ident "$TARGET" 2>/dev/null)" ]] ||
 { echo "STAGE30_8B_FINAL_RELEASE_CHANGED=REVIEW_REQUIRED";rc=92; }
 [[ -z "$B_CADDY" || "$B_CADDY" == "$(ident "$CADDY" 2>/dev/null)" ]] ||
 { echo "STAGE30_8B_CADDY_CHANGED=REVIEW_REQUIRED";rc=93; }
 [[ -z "$B_CONFIG" || "$B_CONFIG" == "$(sudo -n sha256sum "$HOST_CADDY" 2>/dev/null | awk '{print $1}')" ]] ||
 { echo "STAGE30_8B_CADDY_CONFIG_CHANGED=REVIEW_REQUIRED";rc=94; }
 [[ -z "$B_FIN" || "$B_FIN" == "$(counts 2>/dev/null)" ]] ||
 { echo "STAGE30_8B_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";rc=95; }
 if ((rc));then
  echo "STAGE30_8B_COMPARATIVE_DIAGNOSTIC=FAIL step=$STEP exit=$rc"
 else
  echo "STAGE30_8B_COMPARATIVE_DIAGNOSTIC=COMPLETE"
 fi
 echo "STAGE30_8B_RELEASE_ACCEPTANCE=BLOCKED_PENDING_ROOT_CAUSE_AND_RELIABLE_STABILITY"
 echo "STAGE30_8B_CADDY_CHANGE=NONE"
 echo "STAGE30_8B_DOCKER_RESTART=NONE"
 echo "STAGE30_8B_FINANCIAL_WRITES=NONE"
 echo "STAGE30_8B_EVIDENCE_FILE=$OUT"
 exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=== A. VERIFY UNCHANGED APPROVED PRODUCTION RELEASE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$TARGET" "$LIVE" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_8B_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
B_TARGET="$(ident "$TARGET")"
B_LIVE="$(ident "$LIVE")"
B_CADDY="$(ident "$CADDY")"
B_FIN="$(counts)"
B_CONFIG="$(sudo -n sha256sum "$HOST_CADDY" | awk '{print $1}')"
[[ "$B_CONFIG" == "$EXPECTED_SHA" ]] ||
 { echo "STAGE30_8B_CADDY_HASH_UNEXPECTED=BLOCKED";exit 12; }
[[ "$B_CONFIG" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]] ||
 { echo "STAGE30_8B_CADDY_BIND_MOUNT_MISMATCH=BLOCKED";exit 13; }
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]] ||
 { echo "STAGE30_8B_TARGET_NETWORK_UNEXPECTED=BLOCKED";exit 14; }
[[ "$(sudo -n docker inspect "$LIVE" --format '{{json .NetworkSettings.Networks}}')" == *"$NET"* ]] ||
 { echo "STAGE30_8B_LIVE_NETWORK_UNEXPECTED=BLOCKED";exit 15; }
TARGET_IP="$(sudo -n docker inspect "$TARGET" --format "{{with index .NetworkSettings.Networks \"$NET\"}}{{.IPAddress}}{{end}}")"
LIVE_IP="$(sudo -n docker inspect "$LIVE" --format "{{with index .NetworkSettings.Networks \"$NET\"}}{{.IPAddress}}{{end}}")"
[[ "$TARGET_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
 { echo "STAGE30_8B_TARGET_IP_MISSING=BLOCKED";exit 16; }
[[ "$LIVE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
 { echo "STAGE30_8B_LIVE_IP_MISSING=BLOCKED";exit 17; }
echo "STAGE30_8B_VERIFIED_RELEASE_AND_DATABASE_BASELINE=PASS"
echo "STAGE30_8B_PRIVATE_BRIDGE_NETWORK=$NET"

echo "=== B. SAFE HOST SCHEDULING INDICATORS (NO CONTAINER LOGS OR SECRETS) ==="
STEP=HOST_PRESSURE
python3 -B - <<'PY'
from pathlib import Path
for name in ('cpu','io','memory'):
 p=Path('/proc/pressure')/name
 if not p.exists():continue
 for line in p.read_text().splitlines():
  tokens=line.split()
  if tokens and tokens[0]=='some':
   values={k:v for k,v in (t.split('=',1) for t in tokens[1:])}
   print('STAGE30_8B_HOST_PSI_'+name.upper()+'_AVG10='+values.get('avg10','NA'))
p=Path('/proc/loadavg')
if p.exists():
 fields=p.read_text().split()
 print('STAGE30_8B_HOST_LOAD1='+fields[0])
PY

echo "=== C. COMPARE SAME TIME WINDOW: HTTPS CADDY VS DIRECT RELEASE VS OLD PR129 ==="
STEP=COMPARATIVE_PROBE
# 32 rounds, moderate cadence, ≤3 concurrent GET requests/round.
# This is a diagnostic, not final acceptance. A completed test can still
# leave handover blocked even when no slow event was captured.
python3 -B - "$SITE" "$TARGET_IP" "$LIVE_IP" <<'PY'
import sys,subprocess,http.client,time,concurrent.futures,statistics
site,target_ip,live_ip=sys.argv[1:]
PATH='/login'
ROUNDS=32
THRESHOLD=3.0
def edge():
 cmd=[
  'curl','--noproxy','*','-sS','-o','/dev/null',
  '-w','%{http_code} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total}',
  '--connect-timeout','4','--max-time','9',
  '--resolve',site+':443:127.0.0.1',
  'https://'+site+PATH
 ]
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=11)
  values=p.stdout.strip().split()
  status=values[0] if values else 'NONE'
  timings=list(map(float,values[1:])) if len(values)==5 else None
  return dict(status=status,seconds=timings[-1] if timings else 99.,
              tcp=timings[0] if timings else None,
              tls=timings[1] if timings else None,
              ttfb=timings[2] if timings else None,ok=p.returncode==0 and status=='200')
 except subprocess.TimeoutExpired:
  return dict(status='ProcessTimeout',seconds=99.,tcp=None,tls=None,ttfb=None,ok=False)
def direct(ip):
 start=time.monotonic()
 conn=http.client.HTTPConnection(ip,8080,timeout=9)
 status='NONE';ttfb=None
 try:
  conn.request('GET',PATH,headers={'Connection':'close'})
  response=conn.getresponse()
  ttfb=time.monotonic()-start
  status=str(response.status)
  response.read(512)
 except (OSError,http.client.HTTPException) as exc:
  status=type(exc).__name__
 finally:
  conn.close()
 return dict(status=status,seconds=time.monotonic()-start,ttfb=ttfb,ok=status=='200')
labels=('EDGE_HTTPS','NEW_GUNICORN_DIRECT','OLD_PR129_DIRECT')
def printable(r):
 def fmt(value):
  return 'NA' if value is None else str(round(value,3))
 return 'status:'+r['status']+' total:'+fmt(r['seconds'])+' ttfb:'+fmt(r['ttfb'])+' tls:'+fmt(r.get('tls'))
all_results=[]
print('STAGE30_8B_PREWARM=BEGIN',flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 pre=list(pool.map(lambda f:f(),(edge,lambda:direct(target_ip),lambda:direct(live_ip))))
for label,r in zip(labels,pre):
 print('STAGE30_8B_PREWARM='+label+' '+printable(r),flush=True)
 if not r['ok']:
  print('STAGE30_8B_PREWARM_STATUS=FAIL',flush=True)
  sys.exit(31)
print('STAGE30_8B_PREWARM_STATUS=PASS',flush=True)

wrong=0
slow={label:0 for label in labels}
edge_only=0
all_paths_slow=0
for n in range(1,ROUNDS+1):
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  samples=list(pool.map(lambda f:f(),(edge,lambda:direct(target_ip),lambda:direct(live_ip))))
 row=dict(zip(labels,samples))
 for label,result in row.items():
  print('STAGE30_8B_COMPARISON=round:'+str(n)+' path:'+label+' '+printable(result),flush=True)
  if not result['ok']:wrong+=1
  if result['seconds']>THRESHOLD:slow[label]+=1
 if row['EDGE_HTTPS']['seconds']>THRESHOLD and row['NEW_GUNICORN_DIRECT']['seconds']<=1.5:
  edge_only+=1
 if all(x['seconds']>THRESHOLD for x in row.values()):
  all_paths_slow+=1
 if n<ROUNDS:time.sleep(3)
print('STAGE30_8B_TOTAL_PROBES='+str(ROUNDS*len(labels)),flush=True)
print('STAGE30_8B_HTTP_WRONG_STATUS_OR_ERRORS='+str(wrong),flush=True)
for label in labels:
 print('STAGE30_8B_SLOW_OVER_3S_'+label+'='+str(slow[label]),flush=True)
print('STAGE30_8B_EDGE_ONLY_SLOW_OBSERVATIONS='+str(edge_only),flush=True)
print('STAGE30_8B_SIMULTANEOUS_ALL_PATHS_SLOW='+str(all_paths_slow),flush=True)
if slow['EDGE_HTTPS'] and not slow['NEW_GUNICORN_DIRECT']:
 conclusion='EDGE_OR_PROXY_PATH_SUSPECTED_NOT_PROVEN'
elif slow['NEW_GUNICORN_DIRECT'] and slow['EDGE_HTTPS']:
 conclusion='BACKEND_OR_SHARED_HOST_SUSPECTED_NOT_PROVEN'
elif slow['OLD_PR129_DIRECT'] and slow['NEW_GUNICORN_DIRECT']:
 conclusion='SHARED_HOST_OR_WORKER_SCHEDULING_SUSPECTED_NOT_PROVEN'
else:
 conclusion='INSUFFICIENT_SLOW_SAMPLES_FOR_ROOT_CAUSE'
print('STAGE30_8B_PATH_CORRELATION='+conclusion,flush=True)
print('STAGE30_8B_ROOT_CAUSE=NOT_CONCLUSIVELY_PROVEN',flush=True)
if wrong:
 sys.exit(32)
PY
echo "STAGE30_8B_COMPARE_HTTP=FINISHED_NO_STATUS_ERRORS"
echo "STAGE30_8B_NEXT=REVIEW_EDGE_VS_BACKEND_CORRELATION_AND_DECIDE_TARGETED_REMEDIATION"

echo "=== D. REVERIFY NO CADDY, CONTAINER OR FINANCIAL CHANGES ==="
STEP=FINAL_IMMUTABILITY
[[ "$B_LIVE" == "$(ident "$LIVE")" ]]
[[ "$B_TARGET" == "$(ident "$TARGET")" ]]
[[ "$B_CADDY" == "$(ident "$CADDY")" ]]
[[ "$B_CONFIG" == "$(sudo -n sha256sum "$HOST_CADDY" | awk '{print $1}')" ]]
[[ "$B_FIN" == "$(counts)" ]]
echo "STAGE30_8B_PRODUCTION_CADDY_AND_FINANCIAL_IMMUTABILITY=PASS"
STEP=COMPLETE
