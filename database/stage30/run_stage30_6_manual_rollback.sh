#!/usr/bin/env bash
# SBI Stage30.6 emergency OWNER-OPERATED limited-release routing rollback.
# Use ONLY if the approved PR129 cutover has completed and must be undone.
# Does not change any financial data, Docker images, or other Caddy routes.
set -Eeuo pipefail
umask 077
LIVE=sbi-bulk-report-pr129-https-preview
TARGET=sbi-pr129-modern-release-final
CADDY=aws_lightsail-caddy-1
SITE=pr129.13-232-241-221.sslip.io
HOSTCONF=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
ORIGINAL=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
PROPOSED=/home/ubuntu/sbi-release-evidence/stage30_5_durable_Ft4fao2H/Caddyfile.proposed
PIN_NEW=61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
REPORT="$EVID/stage30_6_owner_rollback_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$REPORT") 2>&1
STEP=PRECHECK
SUCCESS=NO
finish(){
 local rc=$?
 trap - EXIT
 if ((rc));then echo "STAGE30_OWNER_ROLLBACK=FAIL step=$STEP exit=$rc"
 else echo "STAGE30_OWNER_ROLLBACK=PASS_OLD_PR129_RESTORED";fi
 echo "STAGE30_FINANCIAL_WRITES_BY_ROLLBACK=NONE"
 echo "STAGE30_EVIDENCE_FILE=$REPORT"
 exit "$rc"
}
trap finish EXIT
echo "=== A. HASH-VERIFY CURRENT CONFIGURATION, ORIGINAL BACKUP AND CADDY MOUNT ==="
sudo -n docker info >/dev/null
[[ -f "$ORIGINAL" && -f "$PROPOSED" && -f "$HOSTCONF" ]] ||
 { echo "STAGE30_ROLLBACK_REQUIRED_FILE_MISSING=STOP";exit 11; }
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_ORIGINAL_LIVE_NOT_RUNNING=STOP";exit 12; }
[[ "$(sudo -n docker inspect "$CADDY" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_CADDY_NOT_RUNNING=STOP";exit 13; }
HASH_ORIG="$(sha256sum "$ORIGINAL" | awk '{print $1}')"
HASH_CUR="$(sudo -n sha256sum "$HOSTCONF" | awk '{print $1}')"
[[ "$(sha256sum "$PROPOSED" | awk '{print $1}')" == "$PIN_NEW" ]] ||
 { echo "STAGE30_PROPOSED_HASH_UNKNOWN=STOP";exit 14; }
[[ "$HASH_CUR" == "$PIN_NEW" || "$HASH_CUR" == "$HASH_ORIG" ]] ||
 { echo "STAGE30_CONFIG_NOT_RECOGNIZED_MANUAL_REVIEW=STOP";exit 15; }
[[ "$HASH_CUR" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]] ||
 { echo "STAGE30_CONFIG_MOUNT_NOT_MATCHING=STOP";exit 16; }
if [[ "$HASH_CUR" == "$HASH_ORIG" ]];then
 echo "STAGE30_CADDY_CONFIG_ALREADY_ORIGINAL=PASS"
else
 echo "=== B. RESTORE ORIGINAL CADDYFILE THROUGH EXISTING BIND-MOUNT INODE ==="
 STEP=RESTORE
 sudo -n python3 -B - "$ORIGINAL" "$HOSTCONF" <<'PY'
import os,sys,stat
from pathlib import Path
data=Path(sys.argv[1]).read_bytes()
fd=os.open(sys.argv[2],os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 assert stat.S_ISREG(os.fstat(fd).st_mode)
 os.lseek(fd,0,os.SEEK_SET)
 view=memoryview(data)
 while view:
  n=os.write(fd,view)
  assert n>0
  view=view[n:]
 os.ftruncate(fd,len(data))
 os.fsync(fd)
finally:
 os.close(fd)
PY
 [[ "$(sudo -n sha256sum "$HOSTCONF" | awk '{print $1}')" == "$HASH_ORIG" ]]
 STEP=RELOAD
 timeout 20s sudo -n docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
 echo "STAGE30_ORIGINAL_CADDYFILE_RELOAD=PASS"
fi
echo "=== C. HTTPS SMOKE CHECK OF ORIGINAL PR129 ==="
STEP=SMOKE
python3 -B - "$SITE" <<'PY'
import subprocess,sys
site=sys.argv[1]
for path,expect in (('/login',200),('/api/reporting/v2/postgresql-summary',401),('/api/bulk-report/status',401)):
 p=subprocess.run(['curl','--noproxy','*','-sS','-o','/dev/null','-w','%{http_code}',
 '--resolve',site+':443:127.0.0.1','--max-time','8','https://'+site+path],
 capture_output=True,text=True,timeout=10)
 code=p.stdout.strip()
 print('STAGE30_ROLLBACK_HTTPS='+path+' status:'+code)
 assert p.returncode==0 and code==str(expect)
print('STAGE30_ROLLBACK_HTTPS_SMOKE=PASS')
PY
echo "STAGE30_ROLLBACK_CONFIG_SHA256=$HASH_ORIG"
echo "STAGE30_OLD_PR129_CONTAINER=UNCHANGED"
STEP=COMPLETE
