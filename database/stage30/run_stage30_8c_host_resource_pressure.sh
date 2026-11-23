#!/usr/bin/env bash
# SBI Stage 30.8C — read-only host scheduling / CPU / IO contention triage.
# No Docker changes, database writes, service restarts, Caddy reloads,
# credential reads, or command-line process argument output.
set -Eeuo pipefail
umask 077
STEP=INIT
EVID=/home/ubuntu/sbi-release-evidence
DB=sbi_reconciliation_main
CADDYFILE=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
EXPECTED_SHA=61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b
LIVE=sbi-bulk-report-pr129-https-preview
FINAL=sbi-pr129-modern-release-final
CADDY=aws_lightsail-caddy-1
mkdir -p "$EVID";chmod 700 "$EVID"
OUT="$EVID/stage30_8c_host_pressure_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$OUT") 2>&1
B_LIVE=""
B_FINAL=""
B_CADDY=""
B_FILE=""
B_COUNTS=""
ident(){ sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'; }
counts(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$B_LIVE" && "$B_LIVE" != "$(ident "$LIVE" 2>/dev/null)" ]];then echo "STAGE30_8C_OLD_LIVE_CHANGED=REVIEW";rc=91;fi
 if [[ -n "$B_FINAL" && "$B_FINAL" != "$(ident "$FINAL" 2>/dev/null)" ]];then echo "STAGE30_8C_FINAL_CHANGED=REVIEW";rc=92;fi
 if [[ -n "$B_CADDY" && "$B_CADDY" != "$(ident "$CADDY" 2>/dev/null)" ]];then echo "STAGE30_8C_CADDY_CHANGED=REVIEW";rc=93;fi
 if [[ -n "$B_FILE" && "$B_FILE" != "$(sudo -n sha256sum "$CADDYFILE" 2>/dev/null | awk '{print $1}')" ]];then echo "STAGE30_8C_CADDYFILE_CHANGED=REVIEW";rc=94;fi
 if [[ -n "$B_COUNTS" && "$B_COUNTS" != "$(counts 2>/dev/null)" ]];then echo "STAGE30_8C_FINANCIAL_COUNTS_CHANGED=REVIEW";rc=95;fi
 if ((rc));then echo "STAGE30_8C_HOST_CONTENTION_QA=FAILED step=$STEP exit=$rc"
 else echo "STAGE30_8C_HOST_CONTENTION_QA=PASS_DIAGNOSTIC_ONLY";fi
 echo "STAGE30_8C_RELEASE_GATE=BLOCKED_PENDING_RESOURCE_ROOT_CAUSE_AND_FINAL_STABILITY"
 echo "STAGE30_8C_PRODUCTION_CADDY_CHANGE=NONE"
 echo "STAGE30_8C_CONTAINER_RESTARTS_BY_TEST=NONE"
 echo "STAGE30_8C_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_8C_EVIDENCE_FILE=$OUT"
 exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "=== A. PROTECT LIVE PR129, NEW RELEASE, CADDY, FINANCIAL STATE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$FINAL" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_8C_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
B_LIVE="$(ident "$LIVE")"
B_FINAL="$(ident "$FINAL")"
B_CADDY="$(ident "$CADDY")"
B_FILE="$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')"
B_COUNTS="$(counts)"
[[ "$B_FILE" == "$EXPECTED_SHA" ]] ||
 { echo "STAGE30_8C_RELEASE_CONFIG_NOT_EXPECTED=BLOCKED";exit 12; }
echo "STAGE30_8C_LIVE_AND_FINANCIAL_BASELINE=PASS"

echo "=== B. FIVE-SECOND HOST CPU, IO, MEMORY, CPU STEAL AND TOP PROCESS DELTAS ==="
STEP=HOST
sudo -n python3 -B - <<'PY'
import os,time
from pathlib import Path
CLK=os.sysconf('SC_CLK_TCK')
def cpu():
 vals=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
 return vals
def pressure():
 for k in ('cpu','io','memory'):
  p=Path('/proc/pressure')/k
  if p.exists():
   for line in p.read_text().splitlines():
    if line.startswith('some '):
     parts=dict(x.split('=',1) for x in line.split()[1:])
     print('STAGE30_8C_PSI_'+k.upper()+'_AVG10='+parts.get('avg10','NA'),flush=True)
     print('STAGE30_8C_PSI_'+k.upper()+'_AVG60='+parts.get('avg60','NA'),flush=True)
def mem():
 data={}
 for line in Path('/proc/meminfo').read_text().splitlines():
  if ':' in line:
   k,v=line.split(':',1);data[k]=v.strip().split()[0]
 for k in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):
  print('STAGE30_8C_'+k.upper()+'_KB='+data.get(k,'NA'),flush=True)
def proc():
 out={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   raw=(p/'stat').read_text()
   fields=raw[raw.rfind(')')+2:].split()
   ticks=int(fields[11])+int(fields[12])
   name=(p/'comm').read_text().strip()[:36]
   io_read=io_write=0
   try:
    for line in (p/'io').read_text().splitlines():
     if line.startswith('read_bytes:'):io_read=int(line.split(':')[1])
     if line.startswith('write_bytes:'):io_write=int(line.split(':')[1])
   except (OSError,PermissionError):pass
   out[p.name]=(name,ticks,io_read,io_write)
  except (OSError,ValueError,IndexError,PermissionError):continue
 return out
print('STAGE30_8C_LOGICAL_VCPUS='+str(os.cpu_count()),flush=True)
print('STAGE30_8C_LOADAVG_1_5_15='+','.join(str(round(x,2)) for x in os.getloadavg()),flush=True)
pressure();mem()
a=cpu();p1=proc();time.sleep(5);b=cpu();p2=proc()
d=[max(0,y-x) for x,y in zip(a,b)]
total=sum(d)
if total:
 busy=total-d[3]-(d[4] if len(d)>4 else 0)
 print('STAGE30_8C_CPU_BUSY_PERCENT='+str(round(100*busy/total,1)),flush=True)
 print('STAGE30_8C_IOWAIT_PERCENT='+str(round(100*d[4]/total,1) if len(d)>4 else 0),flush=True)
 print('STAGE30_8C_STEAL_PERCENT='+str(round(100*d[7]/total,1) if len(d)>7 else 0),flush=True)
rows=[]
for pid,after in p2.items():
 if pid not in p1 or p1[pid][0]!=after[0]:continue
 before=p1[pid]
 ticks=max(0,after[1]-before[1])
 read=max(0,after[2]-before[2])
 written=max(0,after[3]-before[3])
 rows.append((ticks,pid,after[0],read,written))
for rank,(ticks,pid,name,read,written) in enumerate(sorted(rows,reverse=True)[:15],start=1):
 print('STAGE30_8C_TOP_CPU_PROC='+str(rank)+
       ' pid:'+pid+' name:'+name+
       ' cpu_seconds:'+str(round(ticks/CLK,2))+
       ' disk_read_kb:'+str(read//1024)+
       ' disk_write_kb:'+str(written//1024),flush=True)
for rank,(ticks,pid,name,read,written) in enumerate(sorted(rows,key=lambda r:r[3]+r[4],reverse=True)[:8],start=1):
 print('STAGE30_8C_TOP_IO_PROC='+str(rank)+
       ' pid:'+pid+' name:'+name+
       ' io_kb:'+str((read+written)//1024),flush=True)
pressure()
print('STAGE30_8C_PROCESS_ARGV_AND_ENVIRON=NOT_ACCESSED',flush=True)
PY

echo "=== C. DOCKER RESOURCE USAGE AND NON-SECRET CONTAINER LIMITS ==="
STEP=DOCKER_RESOURCES
sudo -n docker stats --no-stream \
 --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.PIDs}}' |
 python3 -B -c 'import sys
entries=[]
for line in sys.stdin:
 fields=line.strip().split("|")
 if len(fields)!=5:continue
 try:cpu=float(fields[1].rstrip("%"))
 except ValueError:cpu=0.
 entries.append((cpu,fields))
print("STAGE30_8C_RUNNING_CONTAINER_COUNT="+str(len(entries)))
for _,row in sorted(entries,key=lambda x:x[0],reverse=True)[:18]:
 name,cpu,mem,memp,pids=row
 print("STAGE30_8C_DOCKER_USAGE="+name+" cpu:"+cpu+" mem:"+mem+" mem_pct:"+memp+" pids:"+pids)'
for c in "$LIVE" "$FINAL" "$CADDY";do
 sudo -n docker inspect "$c" --format 'STAGE30_8C_DOCKER_LIMIT={{.Name}} cpus={{.HostConfig.NanoCpus}} cpu_quota={{.HostConfig.CpuQuota}} memory_bytes={{.HostConfig.Memory}} restart_count={{.RestartCount}}'
done
echo "STAGE30_8C_CONTAINER_CONFIG_VALUES_ONLY=PASS"

echo "=== D. RESOURCE PRESSURE AND LIGHTSAIL BURST CAPACITY NEXT REVIEW ==="
STEP=FINAL
echo "STAGE30_8C_LIGHTSAIL_BURST_CAPACITY_PERCENT=CHECK_AWS_CONSOLE_METRICS_NOT_AVAILABLE_IN_GUEST"
echo "STAGE30_8C_NEXT=CORRELATE_PSI_CPU_STEAL_TOP_PROCESSES_WITH_LIGHTSAIL_CPU_AND_BURST_CAPACITY"
echo "STAGE30_8C_ROOT_CAUSE=NOT_YET_PROVEN"
[[ "$B_LIVE" == "$(ident "$LIVE")" ]]
[[ "$B_FINAL" == "$(ident "$FINAL")" ]]
[[ "$B_CADDY" == "$(ident "$CADDY")" ]]
[[ "$B_FILE" == "$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')" ]]
[[ "$B_COUNTS" == "$(counts)" ]]
echo "STAGE30_8C_RELEASE_AND_FINANCIAL_IMMUTABILITY=PASS"
STEP=COMPLETE
