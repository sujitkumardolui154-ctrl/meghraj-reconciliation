#!/usr/bin/env bash
# SBI Stage 30.8 final limited-release handover QA.
# READ ONLY: no Caddy reload, restart, network reconfiguration, source import,
# financial writes, or reconciliation engine activation.
set -Eeuo pipefail
umask 077
STEP=INIT
SITE=pr129.13-232-241-221.sslip.io
LIVE=sbi-bulk-report-pr129-https-preview
TARGET=sbi-pr129-modern-release-final
STAGE=sbi-pr129-pg-modernui-stage26r2
CADDY=aws_lightsail-caddy-1
NET=sbi_pr129_preview_net
DB=sbi_reconciliation_main
HOST_CADDY=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
ORIGINAL=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
READY=/home/ubuntu/sbi-release-evidence/stage30_5_durable_Ft4fao2H
CUTOVER=/home/ubuntu/sbi-release-evidence/stage30_6_cutover_20261123T085458Z
STAGE7_LOG=/home/ubuntu/sbi-release-evidence/stage30_7_production_readonly_20261123T090210Z.log
ROLLBACK=/home/ubuntu/sbi_stage30_6_rollback.sh
NEW_SHA=61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID";chmod 700 "$EVID"
DIR="$(mktemp -d "$EVID/stage30_8_final_XXXXXXXX")";chmod 700 "$DIR"
exec > >(tee "$DIR/stage30_8.log") 2>&1

BASE_LIVE=""
BASE_TARGET=""
BASE_CADDY=""
BASE_STAGE=""
BASE_CONFIG=""
BASE_DB=""
ERRORS=0
ident(){ sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'; }
counts(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
finish(){
 local rc=$?
 trap - EXIT
 [[ -z "$BASE_LIVE" || "$BASE_LIVE" == "$(ident "$LIVE" 2>/dev/null)" ]] || { echo "STAGE30_8_OLD_RELEASE_ID_CHANGED=REVIEW_REQUIRED";rc=91; }
 [[ -z "$BASE_TARGET" || "$BASE_TARGET" == "$(ident "$TARGET" 2>/dev/null)" ]] || { echo "STAGE30_8_CURRENT_RELEASE_ID_CHANGED=REVIEW_REQUIRED";rc=92; }
 [[ -z "$BASE_CADDY" || "$BASE_CADDY" == "$(ident "$CADDY" 2>/dev/null)" ]] || { echo "STAGE30_8_CADDY_CONTAINER_ID_CHANGED=REVIEW_REQUIRED";rc=93; }
 [[ -z "$BASE_STAGE" || "$BASE_STAGE" == "$(ident "$STAGE" 2>/dev/null)" ]] || { echo "STAGE30_8_STAGE_ID_CHANGED=REVIEW_REQUIRED";rc=94; }
 [[ -z "$BASE_CONFIG" || "$BASE_CONFIG" == "$(sudo -n sha256sum "$HOST_CADDY" 2>/dev/null | awk '{print $1}')" ]] || { echo "STAGE30_8_PRODUCTION_CADDY_CHANGED=REVIEW_REQUIRED";rc=95; }
 [[ -z "$BASE_DB" || "$BASE_DB" == "$(counts 2>/dev/null)" ]] || { echo "STAGE30_8_FINANCIAL_COUNTS_CHANGED=REVIEW_REQUIRED";rc=96; }
 if ((ERRORS));then
  echo "STAGE30_8_HEALTH_FAILURES=$ERRORS"
  if ((rc==0));then rc=36;fi
 fi
 if ((rc));then echo "STAGE30_8_FINAL_TECHNICAL_HANDOVER=BLOCKED step=$STEP exit=$rc"
 else echo "STAGE30_8_FINAL_TECHNICAL_HANDOVER=PASS_LIMITED_READ_ONLY_RELEASE";fi
 echo "STAGE30_8_FINANCIAL_ENGINE=NOT_ACTIVATED"
 echo "STAGE30_8_FINANCIAL_WRITES=NONE_BY_THIS_TEST"
 echo "STAGE30_8_SELECTED_INVOICE_LOOKUP=DISABLED"
 echo "STAGE30_8_SOURCE_CSV_REPORTS=NOT_CONNECTED_REQUIRE_SEPARATE_SOURCE_APPROVAL"
 echo "STAGE30_8_PAYMENT_RECONCILIATION=NOT_ACTIVATED"
 echo "STAGE30_8_OWNER_UI_EVIDENCE=SCREENSHOTS_REVIEWED_IN_CHAT_NOT_AUTOMATED"
 echo "STAGE30_8_EVIDENCE_DIRECTORY=$DIR"
 exit "$rc"
}
trap finish EXIT
echo "=== A. CROSS-STAGE QA EVIDENCE AND ROLLBACK INVENTORY ==="
STEP=EVIDENCE
sudo -n docker info >/dev/null
for container in "$LIVE" "$TARGET" "$STAGE" "$CADDY";do
 [[ "$(sudo -n docker inspect "$container" --format '{{.State.Running}}')" == true ]] ||
 { echo "STAGE30_8_REQUIRED_CONTAINER_NOT_RUNNING=$container";exit 11; }
done
BASE_LIVE="$(ident "$LIVE")"
BASE_TARGET="$(ident "$TARGET")"
BASE_STAGE="$(ident "$STAGE")"
BASE_CADDY="$(ident "$CADDY")"
BASE_DB="$(counts)"
BASE_CONFIG="$(sudo -n sha256sum "$HOST_CADDY" | awk '{print $1}')"
test -s "$READY/Caddyfile.original" && test -s "$READY/Caddyfile.proposed" &&
 test -s "$CUTOVER/Caddyfile.original" && test -s "$ORIGINAL" &&
 test -s "$STAGE7_LOG" && test -s "$ROLLBACK" ||
 { echo "STAGE30_8_MISSING_EVIDENCE_OR_ROLLBACK=BLOCKED";exit 12; }
bash -n "$ROLLBACK"
grep -q '^STAGE30_7_AUTOMATED_PRODUCTION_QA=PASS_READ_ONLY$' "$STAGE7_LOG" ||
 { echo "STAGE30_8_STAGE7_LOG_NOT_PASS=BLOCKED";exit 13; }
grep -q '^STAGE30_CONTROLLED_CUTOVER=PASS_LIMITED_PR129$' "$CUTOVER/combined.log" ||
 { echo "STAGE30_8_STAGE6_LOG_NOT_PASS=BLOCKED";exit 14; }
[[ "$BASE_CONFIG" == "$NEW_SHA" ]] &&
[[ "$BASE_CONFIG" == "$(sha256sum "$READY/Caddyfile.proposed" | awk '{print $1}')" ]] &&
[[ "$BASE_CONFIG" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]] ||
 { echo "STAGE30_8_ACTIVE_CADDY_DIFFERS_FROM_APPROVED_PROPOSAL=BLOCKED";exit 15; }
ORIG_SHA="$(sha256sum "$ORIGINAL" | awk '{print $1}')"
for f in "$READY/Caddyfile.original" "$CUTOVER/Caddyfile.original";do
 [[ "$(sha256sum "$f" | awk '{print $1}')" == "$ORIG_SHA" ]] ||
 { echo "STAGE30_8_ROLLBACK_HASH_CONFLICT=BLOCKED";exit 16; }
done
echo "STAGE30_8_PREVIOUS_SUCCESS_AND_IDENTICAL_ROLLBACK_EVIDENCE=PASS"

echo "=== B. LIVE ACTIVE ROUTE, PRIVATE TARGET, IMMUTABLE ORIGINAL ==="
STEP=ACTIVE_ROUTE
sudo -n docker exec "$CADDY" wget -qO- http://127.0.0.1:2019/config/ |
 python3 -B -c 'import json,sys
site="pr129.13-232-241-221.sslip.io"
expected="sbi-pr129-modern-release-final:8080"
config=json.load(sys.stdin)
matched=[]
def walk(node,hosts):
 if isinstance(node,list):
  for x in node:walk(x,hosts)
 elif isinstance(node,dict):
  items=node.get("match")
  if isinstance(items,list):
   h=[x for m in items if isinstance(m,dict) for x in m.get("host",[]) if isinstance(x,str)]
   if h:hosts=set(h)
  if node.get("handler")=="reverse_proxy":
   matched.extend(x.get("dial") for x in node.get("upstreams",[]) if isinstance(x,dict) and site in hosts)
  for key,val in node.items():
   if key not in ("match","upstreams"):walk(val,hosts)
for server in config.get("apps",{}).get("http",{}).get("servers",{}).values():
 walk(server.get("routes",[]),set())
assert matched==[expected], "Live site upstream unexpectedly changed"
print("STAGE30_8_PR129_ACTIVE_UPSTREAM=VERIFIED_FINAL_RELEASE")'
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.RestartPolicy.Name}}')" == unless-stopped ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.ReadonlyRootfs}}')" == true ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.Privileged}}')" == false ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.Image}}')" == "$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')" ]]
[[ -z "$(sudo -n docker port "$TARGET")" ]]
echo "STAGE30_8_DURABLE_PRIVATE_RUNTIME=PASS"

echo "=== C. CHECK PG VIEW-ONLY REPORTING, NO FINANCIAL INSERT RIGHTS ==="
STEP=READ_ONLY
sudo -n docker exec -i "$TARGET" python3 -B - <<'PY'
import psycopg
from dashboard_sessions import firebase_app
from app import app
from pathlib import Path
import os
assert firebase_app() is not None
assert 'Reports' in Path('/app/index.html').read_text()
assert 'Database Update' in Path('/app/index.html').read_text()
assert 'id="bulk-selected-button" disabled' in Path('/app/index.html').read_text()
assert not os.environ.get('INVOICE_LOOKUP_BACKEND')
with psycopg.connect(connect_timeout=8) as con:
 con.execute('SET TRANSACTION READ ONLY')
 assert con.execute("SELECT current_user,current_database(),current_setting('transaction_read_only')").fetchone()==('sbi_pr129_report_login','sbi_reconciliation_main','on')
 for table in ('invoices','payments','allocations','credit_notes'):
  assert con.execute("SELECT has_table_privilege(current_user,%s,'INSERT')",('sbi.'+table,)).fetchone()[0] is False
 invoice=con.execute('SELECT count(*) FROM sbi.invoice_financial_summary').fetchone()[0]
 payment=con.execute('SELECT count(*) FROM sbi.payment_financial_summary').fetchone()[0]
 print('STAGE30_8_FINANCIAL_VIEW_ROW_COUNTS=invoice:'+str(invoice)+' payment:'+str(payment))
for path in ('/api/reporting/v2/postgresql-summary','/api/bulk-report/status'):
 assert app.test_client().get(path).status_code in (401,403)
print('STAGE30_8_FIREBASE_AND_POSTGRES_READONLY=PASS')
print('STAGE30_8_ANONYMOUS_AUTH_GUARDS=PASS')
print('STAGE30_8_SELECTED_INVOICE_LOOKUP_DISABLING=PASS')
PY

echo "=== D. BOUNDED PRODUCTION HTTPS HEALTH AND ANONYMOUS DENIAL ==="
STEP=HTTPS
if python3 -B - "$SITE" <<'PY'
import sys,subprocess,time
site=sys.argv[1]
targets=[
 ('login','/login',200),
 ('postgresql-summary','/api/reporting/v2/postgresql-summary',401),
 ('catalog','/api/reporting/v2',401),
 ('bulk-status','/api/bulk-report/status',401)
]
errors=0
max_latency=0.
for n in range(1,7):
 for name,path,expected in targets:
  cmd=['curl','--noproxy','*','-sS','-o','/dev/null','-w','%{http_code} %{time_total}',
       '--connect-timeout','4','--max-time','8',
       '--resolve',site+':443:127.0.0.1','https://'+site+path]
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
  parts=p.stdout.strip().split()
  status=parts[0] if parts else 'NONE'
  seconds=float(parts[1]) if len(parts)==2 else 99.
  max_latency=max(max_latency,seconds)
  print('STAGE30_8_HTTPS=round:'+str(n)+' route:'+name+' status:'+status+
        ' seconds:'+str(round(seconds,2)),flush=True)
  if p.returncode or status!=str(expected) or seconds>3.0:errors+=1
 if n<6:time.sleep(5)
print('STAGE30_8_HTTPS_FAILURES='+str(errors),flush=True)
print('STAGE30_8_HTTPS_MAX_LATENCY='+str(round(max_latency,2)),flush=True)
if errors:sys.exit(35)
print('STAGE30_8_HTTPS_SECURITY_AND_LATENCY=PASS_6_ROUNDS',flush=True)
PY
then
 echo "STAGE30_8_PRODUCTION_STABILITY=PASS_BOUNDED"
else
 echo "STAGE30_8_PRODUCTION_STABILITY=BLOCKED"
 ERRORS=$((ERRORS+1))
fi

echo "=== E. VERIFY ENCRYPTED BACKUP INVENTORY WITHOUT READING KEYS ==="
STEP=BACKUP
python3 -B - "$EVID" <<'PY'
import sys
from pathlib import Path
root=Path(sys.argv[1])
candidates=list(root.glob('stage28*'))
print('STAGE30_8_STAGE28_EVIDENCE_ENTRIES='+str(len(candidates)))
print('STAGE30_8_OFFHOST_BACKUP=HISTORICALLY_REPORTED_VERIFIED_NOT_RETRANSMITTED')
print('STAGE30_8_BACKUP_DECRYPTION_SECRET=NOT_ACCESSED')
PY
echo "STAGE30_8_ROLLBACK_COPY_SHA256=$ORIG_SHA"
echo "STAGE30_8_PINNED_PROPOSED_SHA256=$NEW_SHA"
echo "STAGE30_8_ROLLBACK_SCRIPT=AVAILABLE_NOT_EXECUTED"

echo "=== F. FINAL LIVE AND DATABASE IMMUTABILITY ==="
STEP=FINAL_IMMUTABILITY
[[ "$BASE_LIVE" == "$(ident "$LIVE")" ]]
[[ "$BASE_TARGET" == "$(ident "$TARGET")" ]]
[[ "$BASE_STAGE" == "$(ident "$STAGE")" ]]
[[ "$BASE_CADDY" == "$(ident "$CADDY")" ]]
[[ "$BASE_DB" == "$(counts)" ]]
[[ "$BASE_CONFIG" == "$(sudo -n sha256sum "$HOST_CADDY" | awk '{print $1}')" ]]
echo "STAGE30_8_PREVIOUS_LIVE_AND_NEW_RELEASE=UNCHANGED"
echo "STAGE30_8_FINANCIAL_COUNTS=UNCHANGED"
echo "STAGE30_8_CADDY=UNCHANGED"
STEP=COMPLETE
echo "=== STAGE 30.8 FINAL LIMITED RELEASE HANDOVER ==="
echo "STAGE30_8_RELEASE_SCOPE=MODERN_UI_FIREBASE_READONLY_POSTGRESQL"
echo "STAGE30_8_DEPLOYED_PR129_URL=https://$SITE/"
echo "STAGE30_8_PREVIOUS_RELEASE=RETAINED_FOR_ROLLBACK"
echo "STAGE30_8_REPORT_DATA_DISCONNECTED=KNOWN_LIMITATION_NOT_PRODUCTION_FAILURE_FOR_APPROVED_SCOPE"
echo "STAGE30_8_PRODUCTION_OPERATIONS=LIMITED_SCOPE_ONLY"
