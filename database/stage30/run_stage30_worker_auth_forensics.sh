#!/usr/bin/env bash
# Stage30.2: safely inspect Gunicorn worker topology, Flask auth hooks and
# first-response latency. No restart, service reload, deployment or financial write.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
SOURCE=sbi-pr129-pg-modernui-stage26r2
CANARY=sbi-pr129-modern-release-canary
CADDY=aws_lightsail-caddy-1
DB=sbi_reconciliation_main
CADDYFILE=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
REPORT="$EVID/stage30_worker_auth_forensics_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$REPORT") 2>&1
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
  echo "STAGE30_LIVE_CHANGED=REVIEW_REQUIRED";rc=91;fi
 if [[ -n "$BASE_CADDY" && "$BASE_CADDY" != "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_CADDY_CHANGED=REVIEW_REQUIRED";rc=92;fi
 if [[ -n "$BASE_CANARY" && "$BASE_CANARY" != "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}' 2>/dev/null)" ]];then
  echo "STAGE30_CANARY_CHANGED=REVIEW_REQUIRED";rc=93;fi
 if [[ -n "$BASE_FIN" && "$BASE_FIN" != "$(counts 2>/dev/null)" ]];then
  echo "STAGE30_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";rc=94;fi
 if [[ -n "$BASE_CONF" && "$BASE_CONF" != "$(sudo -n sha256sum "$CADDYFILE" 2>/dev/null | awk '{print $1}')" ]];then
  echo "STAGE30_CADDY_CONFIG_CHANGED=REVIEW_REQUIRED";rc=95;fi
 if ((FAILURES));then
  echo "STAGE30_NEW_HTTP_FAILURES=$FAILURES"
  if ((rc==0));then rc=34;fi
 fi
 if ((rc));then echo "STAGE30_WORKER_AUTH_FORENSICS=FAIL_OR_REVIEW step=$STEP exit=$rc"
 else echo "STAGE30_WORKER_AUTH_FORENSICS=PASS_INSPECTION_ONLY";fi
 echo "STAGE30_INTERMITTENT_TIMEOUT_CAUSE=NOT_YET_PROVEN"
 echo "STAGE30_RELEASE_GATE=BLOCKED_PENDING_TIMEOUT_ROOT_CAUSE_AND_EXECUTABLE_ROLLBACK"
 echo "STAGE30_LIVE_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_CADDY_CHANGE=NONE"
 echo "STAGE30_FINANCIAL_WRITES=NONE"
 echo "STAGE30_EVIDENCE_FILE=$REPORT"
 exit "$rc"
}
trap finish EXIT

echo "=== A. SNAPSHOT BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$SOURCE" "$CANARY" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_MISSING_RUNNING_SERVICE=$c";exit 11; }
done
BASE_LIVE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CADDY="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_CANARY="$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BASE_FIN="$(counts)"
BASE_CONF="$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')"
[[ "$BASE_CONF" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.HostConfig.NetworkMode}}')" == sbi_pr129_preview_net ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.Image}}')" == "$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')" ]]
echo "STAGE30_PROTECTED_BASELINES=PASS"

echo "=== B. COMPARE SANITIZED GUNICORN RUNTIME IN CANARY AND LIVE ==="
STEP=WORKER
for container in "$CANARY" "$LIVE";do
 echo "STAGE30_RUNTIME_CONTAINER=$container"
 sudo -n docker exec -i "$container" python3 -B - <<'PY'
from pathlib import Path
import os,collections
items=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  fields={}
  for line in (proc/'status').read_text().splitlines():
   if ':' not in line:continue
   k,v=line.split(':',1)
   if k in ('Name','PPid','Threads','State','VmRSS'):
    fields[k]=v.strip()
  name=fields.get('Name','')
  if not any(x in name.lower() for x in ('gunicorn','python')):
   continue
  items.append((int(proc.name),fields))
 except (OSError,PermissionError):continue
print('STAGE30_RUNTIME_GUNICORN_PYTHON_PROCESS_COUNT='+str(len(items)))
print('STAGE30_RUNTIME_PID1_CHILD_COUNT='+str(sum(x.get('PPid')=='1' for _,x in items)))
for pid,x in sorted(items):
 safe_state=x.get('State','?').split(' ')[0]
 print('STAGE30_RUNTIME_PROCESS=PID:'+str(pid)+' PPID:'+x.get('PPid','?')+
 ' STATE:'+safe_state+' THREADS:'+x.get('Threads','?'))
try:
 argv=Path('/proc/1/cmdline').read_bytes().split(b'\0')
 argv=[v.decode('utf-8','replace') for v in argv if v]
 options={}
 for i,token in enumerate(argv):
  for key in ('--workers','--threads','--worker-class','--timeout','--graceful-timeout','--keep-alive','--preload'):
   if token==key:
    value=argv[i+1] if i+1<len(argv) else 'MISSING'
    if key=='--preload':value='ENABLED'
    options[key]=value if value.replace('.','').isdigit() or value in ('sync','gthread','gevent','eventlet','ENABLED') else 'REDACTED'
   elif token.startswith(key+'='):
    value=token.split('=',1)[-1]
    options[key]=value if value.replace('.','').isdigit() or value in ('sync','gthread','gevent','eventlet') else 'REDACTED'
 for key in ('--workers','--threads','--worker-class','--timeout','--graceful-timeout','--keep-alive','--preload'):
  print('STAGE30_GUNICORN_OPT_'+key.lstrip('-').replace('-','_').upper()+'='+options.get(key,'NOT_EXPLICITLY_SET'))
except (OSError,PermissionError):
 print('STAGE30_GUNICORN_CONFIG=UNREADABLE')
print('STAGE30_RUNTIME_ARGUMENTS_AND_ENV_VALUES=NOT_DISCLOSED')
PY
done

echo "=== C. MASKED AST AUDIT OF BEFORE_REQUEST / AUTH / REPORT CODE ==="
STEP=AST
sudo -n docker exec -i "$CANARY" python3 -B - <<'PY'
import ast,hashlib
from pathlib import Path
paths=['/app/app.py','/app/dashboard_sessions.py','/app/cloud_auth.py',
       '/app/sbi_report_access.py','/app/pg_reporting_blueprint.py',
       '/app/readonly_reports_gateway.py']
def short(f):
 if isinstance(f,ast.Name):return f.id
 if isinstance(f,ast.Attribute):
  return (short(f.value)+'.'+f.attr)[:110]
 if isinstance(f,ast.Call):return short(f.func)
 return type(f).__name__
for filename in paths:
 p=Path(filename)
 if not p.is_file():
  print('STAGE30_SOURCE_FILE='+p.name+' STATUS=MISSING')
  continue
 raw=p.read_bytes()
 tree=ast.parse(raw,filename=p.name)
 print('STAGE30_SOURCE_FILE='+p.name+' SHA256='+hashlib.sha256(raw).hexdigest())
 for node in ast.walk(tree):
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in (
   'install_sessions','protect_dashboard','firebase_app','session_login',
   'dil_login_page','postgres_summary','report_catalog','source_report_csv',
   'is_master','csrf_valid'
  ):
   calls=sorted(set(short(k.func) for k in ast.walk(node) if isinstance(k,ast.Call)))
   print('STAGE30_CALLGRAPH='+p.name+':'+node.name+' CALLS='+','.join(calls[:35]))
   print('STAGE30_CALLGRAPH_TOTAL='+p.name+':'+node.name+' COUNT='+str(len(calls)))
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
   hooks=[short(d) for d in node.decorator_list]
   if any('before_request' in h for h in hooks):
    print('STAGE30_BEFORE_REQUEST='+p.name+':'+node.name)
print('STAGE30_SOURCE_CONTENT_AND_SECRET_VALUES=NOT_DISPLAYED')
PY

echo "=== D. SMALL COMPARATIVE HTTP SNAPSHOT (CANARY VS LIVE) ==="
STEP=HTTP
IMAGE="$(sudo -n docker inspect "$SOURCE" --format '{{.Image}}')"
if sudo -n docker run --rm -i --network sbi_pr129_preview_net \
 --read-only --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" --entrypoint python3 "$IMAGE" -B - "$CANARY" "$LIVE" <<'PY'
import sys,http.client,time
canary,live=sys.argv[1:]
cases=[(canary,'/login',{200}),(canary,'/api/reporting/v2/postgresql-summary',{401,403}),
       (canary,'/api/bulk-report/status',{401,403}),(live,'/login',{200})]
errors=0
for host,path,expected in cases:
 conn=http.client.HTTPConnection(host,8080,timeout=6)
 code=None;reason='';started=time.monotonic()
 try:
  conn.request('GET',path,headers={'Connection':'close'})
  r=conn.getresponse();code=r.status;r.read(512)
 except (OSError,http.client.HTTPException) as exc:reason=type(exc).__name__
 finally:conn.close()
 label='LIVE' if host==live else 'CANARY'
 label2=path.rsplit('/',1)[-1]
 print('STAGE30_HTTP_'+label+'_'+label2+'=STATUS:'+str(code if code is not None else reason)+
       ' SECONDS:'+str(round(time.monotonic()-started,2)),flush=True)
 if code not in expected:errors+=1
print('STAGE30_HTTP_SNAPSHOT_ERRORS='+str(errors))
sys.exit(0 if errors==0 else 35)
PY
then
 echo "STAGE30_COMPARATIVE_HTTP_SNAPSHOT=PASS"
else
 FAILURES=$((FAILURES+1))
 echo "STAGE30_COMPARATIVE_HTTP_SNAPSHOT=FAILED_REVIEW_REQUIRED"
fi

echo "=== E. LIVE ROUTING/FINANCIAL IMMUTABILITY ==="
STEP=IMMUTABLE
[[ "$BASE_LIVE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CADDY" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_CANARY" == "$(sudo -n docker inspect "$CANARY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_FIN" == "$(counts)" ]]
[[ "$BASE_CONF" == "$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')" ]]
echo "STAGE30_LIVE_CADDY_AND_FINANCIAL_COUNTS=UNCHANGED_PASS"
STEP=COMPLETE
echo "STAGE30_NEXT=REVIEW_GUNICORN_WORKER_CONCURRENCY_AND_BEFORE_REQUEST_CALLS"
