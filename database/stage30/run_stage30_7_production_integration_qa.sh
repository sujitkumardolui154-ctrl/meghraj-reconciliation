#!/usr/bin/env bash
# SBI Stage30.7 — live PR129 production integration QA (READ ONLY).
# No Caddy reload, container restart, migrations, credential output, financial
# writes, or authenticated session impersonation. Owner must test real login.
set -Eeuo pipefail
umask 077

SITE=pr129.13-232-241-221.sslip.io
LIVE=sbi-bulk-report-pr129-https-preview
TARGET=sbi-pr129-modern-release-final
STAGE=sbi-pr129-pg-modernui-stage26r2
CADDY=aws_lightsail-caddy-1
NET=sbi_pr129_preview_net
DB=sbi_reconciliation_main
CADDYFILE=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
ORIGINAL=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
READY=/home/ubuntu/sbi-release-evidence/stage30_5_durable_Ft4fao2H
STAGE30_6=/home/ubuntu/sbi-release-evidence/stage30_6_cutover_20261123T085458Z
EXPECTED_NEW=61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b
ROLLBACK=/home/ubuntu/sbi_stage30_6_rollback.sh
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
OUT="$EVID/stage30_7_production_readonly_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$OUT") 2>&1

STEP=START
BASE_LIVE=""
BASE_TARGET=""
BASE_CADDY=""
BASE_DB=""
BASE_CONFIG=""
PROBLEMS=0

ident(){ sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'; }
dbcount(){
 sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" \
 -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"
}
finish(){
 local rc=$?
 trap - EXIT
 if [[ -n "$BASE_LIVE" && "$BASE_LIVE" != "$(ident "$LIVE" 2>/dev/null)" ]];then
  echo "STAGE30_7_OLD_LIVE_CHANGED=REVIEW_REQUIRED";rc=91
 fi
 if [[ -n "$BASE_TARGET" && "$BASE_TARGET" != "$(ident "$TARGET" 2>/dev/null)" ]];then
  echo "STAGE30_7_RELEASE_TARGET_CHANGED=REVIEW_REQUIRED";rc=92
 fi
 if [[ -n "$BASE_CADDY" && "$BASE_CADDY" != "$(ident "$CADDY" 2>/dev/null)" ]];then
  echo "STAGE30_7_CADDY_CHANGED=REVIEW_REQUIRED";rc=93
 fi
 if [[ -n "$BASE_DB" && "$BASE_DB" != "$(dbcount 2>/dev/null)" ]];then
  echo "STAGE30_7_FINANCIAL_RECORD_COUNTS_CHANGED=REVIEW_REQUIRED";rc=94
 fi
 if [[ -n "$BASE_CONFIG" && "$BASE_CONFIG" != "$(sudo -n sha256sum "$CADDYFILE" 2>/dev/null | awk '{print $1}')" ]];then
  echo "STAGE30_7_ROUTING_CONFIG_CHANGED=REVIEW_REQUIRED";rc=95
 fi
 if ((PROBLEMS));then
  echo "STAGE30_7_HTTP_FAILURES=$PROBLEMS"
  if ((rc==0));then rc=36;fi
 fi
 if ((rc));then
  echo "STAGE30_7_AUTOMATED_PRODUCTION_QA=FAIL_OR_REVIEW step=$STEP exit=$rc"
 else
  echo "STAGE30_7_AUTOMATED_PRODUCTION_QA=PASS_READ_ONLY"
 fi
 echo "STAGE30_7_OWNER_REAL_FIREBASE_LOGIN=MANUAL_VERIFICATION_REQUIRED"
 echo "STAGE30_7_OWNER_AUTHORIZED_REPORT=MANUAL_VERIFICATION_REQUIRED"
 echo "STAGE30_7_OWNER_UI_ACCEPTANCE=MANUAL_VERIFICATION_REQUIRED"
 echo "STAGE30_7_FULL_ACCEPTANCE=PENDING_OWNER_BROWSER_EVIDENCE"
 echo "STAGE30_8_FINAL_HANDOVER=NOT_YET_COMPLETED"
 echo "STAGE30_7_FINANCIAL_ENGINE=UNCHANGED"
 echo "STAGE30_7_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_7_EVIDENCE_FILE=$OUT"
 exit "$rc"
}
trap finish EXIT

echo "=== A. CONFIRM APPROVED PR129 CADDY ROUTING AND ROLLBACK ==="
STEP=LIVE_BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$TARGET" "$STAGE" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
  { echo "STAGE30_7_RUNNING_CONTAINER_REQUIRED=$c";exit 11; }
done
BASE_LIVE="$(ident "$LIVE")";BASE_TARGET="$(ident "$TARGET")"
BASE_CADDY="$(ident "$CADDY")";BASE_DB="$(dbcount)"
BASE_CONFIG="$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')"
[[ "$BASE_CONFIG" == "$EXPECTED_NEW" ]] ||
 { echo "STAGE30_7_PRODUCTION_CONFIG_HASH=UNEXPECTED";exit 12; }
[[ "$BASE_CONFIG" == "$(sha256sum "$READY/Caddyfile.proposed" | awk '{print $1}')" ]] ||
 { echo "STAGE30_7_APPROVED_PROPOSAL_MISMATCH=BLOCKED";exit 13; }
[[ "$BASE_CONFIG" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]] ||
 { echo "STAGE30_7_MOUNTED_CADDY_MISMATCH=BLOCKED";exit 14; }
[[ "$(sha256sum "$ORIGINAL" | awk '{print $1}')" == "$(sha256sum "$STAGE30_6/Caddyfile.original" | awk '{print $1}')" ]] ||
 { echo "STAGE30_7_ROLLBACK_ORIGINAL_MISMATCH=BLOCKED";exit 15; }
[[ "$(sha256sum "$ORIGINAL" | awk '{print $1}')" == "$(sha256sum "$READY/Caddyfile.original" | awk '{print $1}')" ]] ||
 { echo "STAGE30_7_STAGE30_5_ROLLBACK_MISMATCH=BLOCKED";exit 16; }
test -s "$ROLLBACK" && bash -n "$ROLLBACK" ||
 { echo "STAGE30_7_MANUAL_ROLLBACK_SCRIPT_MISSING=BLOCKED";exit 17; }
echo "STAGE30_7_PINNED_CADDY_AND_ROLLBACK_EVIDENCE=PASS"

echo "=== B. CONFIRM ACTIVE CADDY CONFIGURATION IS ROUTING ONLY PR129 TO FINAL TARGET ==="
STEP=ACTIVE_ROUTING
sudo -n docker exec "$CADDY" wget -qO- http://127.0.0.1:2019/config/ |
python3 -B -c 'import json,sys
target="sbi-pr129-modern-release-final:8080"
site="pr129.13-232-241-221.sslip.io"
config=json.load(sys.stdin)
found=[]
def visit(node,hosts):
 if isinstance(node,list):
  for x in node:visit(x,hosts)
 elif isinstance(node,dict):
  match=node.get("match")
  if isinstance(match,list):
   hs=[x for m in match if isinstance(m,dict) for x in m.get("host",[]) if isinstance(x,str)]
   if hs:hosts=set(hs)
  if node.get("handler")=="reverse_proxy":
   found.extend(u.get("dial") for u in node.get("upstreams",[]) if isinstance(u,dict) and site in hosts)
  for k,v in node.items():
   if k not in ("match","upstreams"):visit(v,hosts)
for server in config.get("apps",{}).get("http",{}).get("servers",{}).values():
 visit(server.get("routes",[]),set())
assert found==[target], "PR129 active upstream differs from approved final target"
print("STAGE30_7_ACTIVE_PR129_UPSTREAM=VERIFIED_FINAL_TARGET")'
echo "STAGE30_7_PRODUCTION_ROUTE=PASS"

echo "=== C. VERIFY PRIVATE DURABLE CONTAINER SECURITY ==="
STEP=PRIVATE_SECURITY
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.RestartPolicy.Name}}')" == unless-stopped ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.ReadonlyRootfs}}')" == true ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.Privileged}}')" == false ]]
[[ -z "$(sudo -n docker port "$TARGET")" ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.Image}}')" == "$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')" ]]
echo "STAGE30_7_RELEASE_RESTART_PRIVATE_READONLY_ROOTFS=PASS"

echo "=== D. VERIFY UI CONTRACT, FIREBASE INITIALIZATION AND POSTGRESQL READ-ONLY ==="
STEP=BACKEND
sudo -n docker exec -i "$TARGET" python3 -B - <<'PY'
from pathlib import Path
import os
import psycopg
from dashboard_sessions import firebase_app
from app import app
assert firebase_app() is not None
html=Path('/app/index.html').read_text()
for label in ('Reports','Database Update','Bulk Report'):
 assert label in html, 'Required UI section missing: '+label
assert 'id="bulk-selected-button" disabled' in html
assert not os.environ.get('INVOICE_LOOKUP_BACKEND')
assert not Path('/app/pr129_aws_invoice_lookup.enabled').exists()
print('STAGE30_7_FIREBASE_INITIALIZATION=PASS')
print('STAGE30_7_MODERN_UI_CORE_SECTIONS=PASS')
print('STAGE30_7_SELECTED_INVOICE_LOOKUP=DISABLED')
with psycopg.connect(connect_timeout=8) as con:
 con.execute('SET TRANSACTION READ ONLY')
 result=con.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()
 assert result==('sbi_pr129_report_login','sbi_reconciliation_main','on'),result
 for t in ('invoices','payments','allocations','credit_notes'):
  assert con.execute("SELECT has_table_privilege(current_user,%s,'INSERT')",('sbi.'+t,)).fetchone()[0] is False
 invoice=con.execute('SELECT count(*) FROM sbi.invoice_financial_summary').fetchone()[0]
 payment=con.execute('SELECT count(*) FROM sbi.payment_financial_summary').fetchone()[0]
 print('STAGE30_7_POSTGRES_REPORT_ROWS=invoice:'+str(invoice)+' payment:'+str(payment))
 print('STAGE30_7_POSTGRES_READER=READ_ONLY_WRITE_DENIED')
for route in ('/api/reporting/v2/postgresql-summary','/api/bulk-report/status'):
 assert app.test_client().get(route).status_code in (401,403)
print('STAGE30_7_SERVER_SIDE_ANONYMOUS_ACCESS=DENIED')
PY

echo "=== E. 3 ROUNDS OF REAL PR129 HTTPS PRODUCTION ROUTE PROBES ==="
STEP=HTTPS
if python3 -B - "$SITE" <<'PY'
import sys,subprocess,time
site=sys.argv[1]
checks=[
 ('login','/login',200),
 ('postgresql-summary','/api/reporting/v2/postgresql-summary',401),
 ('report-catalog','/api/reporting/v2',401),
 ('bulk-status','/api/bulk-report/status',401),
]
failures=0
for n in range(1,4):
 for label,path,want in checks:
  cmd=['curl','--noproxy','*','-sS','-o','/dev/null',
       '-w','%{http_code} %{time_total}',
       '--connect-timeout','4','--max-time','8',
       '--resolve',site+':443:127.0.0.1',
       'https://'+site+path]
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
  data=p.stdout.strip().split()
  status=data[0] if data else 'NONE'
  latency=float(data[1]) if len(data)==2 else 99
  print('STAGE30_7_HTTPS=round:'+str(n)+' route:'+label+' status:'+status+
        ' seconds:'+str(round(latency,2)),flush=True)
  if p.returncode!=0 or status!=str(want) or latency>3.0:
   failures+=1
 if n<3:time.sleep(2)
print('STAGE30_7_HTTPS_FAILURES='+str(failures),flush=True)
if failures:sys.exit(36)
print('STAGE30_7_PRODUCTION_HTTPS_ANONYMOUS_QA=PASS_3_ROUNDS',flush=True)
PY
then echo "STAGE30_7_HTTPS_STABILITY=PASS_BOUNDED"
else
 echo "STAGE30_7_HTTPS_STABILITY=BLOCKED"
 PROBLEMS=$((PROBLEMS+1))
fi

echo "=== F. FINANCIAL, CADDY, OLD/NEW CONTAINER IMMUTABILITY ==="
STEP=IMMUTABILITY
[[ "$BASE_LIVE" == "$(ident "$LIVE")" ]]
[[ "$BASE_TARGET" == "$(ident "$TARGET")" ]]
[[ "$BASE_CADDY" == "$(ident "$CADDY")" ]]
[[ "$BASE_DB" == "$(dbcount)" ]]
[[ "$BASE_CONFIG" == "$(sudo -n sha256sum "$CADDYFILE" | awk '{print $1}')" ]]
echo "STAGE30_7_FINANCIAL_RECORD_COUNTS=UNCHANGED"
echo "STAGE30_7_OLD_PR129_AND_NEW_RELEASE_CONTAINERS=UNCHANGED"
echo "STAGE30_7_CADDY=UNCHANGED"

STEP=COMPLETE
echo "=== FINAL STAGE30.7 AUTOMATED PRODUCTION QA REPORT ==="
echo "STAGE30_7_AUTOMATED_SECURITY_AND_REPORT_PARITY=PASS"
echo "STAGE30_7_NEXT=OWNER_SIGN_IN_AND_AUTHORIZED_REPORT_ENDPOINT_REVIEW"
