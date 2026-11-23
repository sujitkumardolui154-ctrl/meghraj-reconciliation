#!/usr/bin/env bash
# SBI Stage30.5 - durable release target, bounded stability QA, exact Caddy/rollback dry run.
# Under owner's CONDITIONAL approval. Does NOT change live Caddy routing or financial records.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-modernui-stage26r2
CANARY=sbi-pr129-modern-release-canary
TARGET=sbi-pr129-modern-release-final
CADDY=aws_lightsail-caddy-1
NET=sbi_pr129_preview_net
DB=sbi_reconciliation_main
HOSTCONF=/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile
OLD_BACKUP=/home/ubuntu/sbi-release-evidence/stage30_final_gate_7q4NypdV/Caddyfile.original
PGPASS=/home/ubuntu/sbi-pr129-pg-private-stage/pgpass
AUTHENV=/home/ubuntu/sbi-pr129-pg-private-stage/staging_web_auth.env
FIREBASE=/home/ubuntu/sbi-private-credentials/firebase-stage.json
EVID=/home/ubuntu/sbi-release-evidence
mkdir -p "$EVID"; chmod 700 "$EVID"
DIR="$(mktemp -d "$EVID/stage30_5_durable_XXXXXXXX")";chmod 700 "$DIR"
exec > >(tee "$DIR/combined.log") 2>&1
CREATED=NO
BASELIVE=""
BASECADDY=""
BASESTAGE=""
BASECANARY=""
BASEFIN=""
BASECONF=""
FAILURES=0
OLD_DIAL="$LIVE:8080"
NEW_DIAL="$TARGET:8080"
SITE=pr129.13-232-241-221.sslip.io
counts(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
ident(){ sudo -n docker inspect "$1" --format '{{.Id}}|{{.Image}}|{{.State.Running}}'; }
finish(){
 local rc=$?
 trap - EXIT
 if ((rc)) && [[ "$CREATED" == YES ]];then
   if sudo -n docker rm -f "$TARGET" >/dev/null 2>&1;then
     echo "STAGE30_FAILED_DURABLE_TARGET_REMOVED=PASS"
   else
     echo "STAGE30_FAILED_DURABLE_TARGET_REMOVED=FAIL";rc=98
   fi
 fi
 if [[ -n "$BASELIVE" && "$BASELIVE" != "$(ident "$LIVE" 2>/dev/null)" ]];then echo "STAGE30_LIVE_CHANGED=REVIEW";rc=91;fi
 if [[ -n "$BASESTAGE" && "$BASESTAGE" != "$(ident "$STAGE" 2>/dev/null)" ]];then echo "STAGE30_STAGE_CHANGED=REVIEW";rc=92;fi
 if [[ -n "$BASECANARY" && "$BASECANARY" != "$(ident "$CANARY" 2>/dev/null)" ]];then echo "STAGE30_CANARY_CHANGED=REVIEW";rc=93;fi
 if [[ -n "$BASECADDY" && "$BASECADDY" != "$(ident "$CADDY" 2>/dev/null)" ]];then echo "STAGE30_CADDY_CONTAINER_CHANGED=REVIEW";rc=94;fi
 if [[ -n "$BASECONF" && "$BASECONF" != "$(sudo -n sha256sum "$HOSTCONF" 2>/dev/null | awk '{print $1}')" ]];then echo "STAGE30_LIVE_CADDYFILE_CHANGED=REVIEW";rc=95;fi
 if [[ -n "$BASEFIN" && "$BASEFIN" != "$(counts 2>/dev/null)" ]];then echo "STAGE30_FINANCIAL_COUNTS_CHANGED=REVIEW";rc=96;fi
 if ((FAILURES));then
   echo "STAGE30_STABILITY_FAILURES=$FAILURES"
   if ((rc==0));then rc=33;fi
 fi
 if ((rc));then echo "STAGE30_DURABLE_CANDIDATE_COMBINED_QA=FAIL step=$STEP exit=$rc"
 else echo "STAGE30_DURABLE_CANDIDATE_COMBINED_QA=PASS_GATED";fi
 echo "STAGE30_OWNER_APPROVAL=LIMITED_SCOPE_CONDITIONAL"
 echo "STAGE30_CADDY_ROUTE_CHANGE=NONE"
 echo "STAGE30_PRODUCTION_CUTOVER=NOT_PERFORMED"
 echo "STAGE30_FINANCIAL_WRITES_BY_TEST=NONE"
 echo "STAGE30_EVIDENCE_DIRECTORY=$DIR"
 exit "$rc"
}
trap finish EXIT

echo "=== A. FINAL LIVE/CADDY/DB BASELINES AND CANARY SECURITY ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for container in "$LIVE" "$STAGE" "$CANARY" "$CADDY";do
 [[ "$(sudo -n docker inspect "$container" --format '{{.State.Running}}')" == true ]] ||
  { echo "STAGE30_RUNNING_CONTAINER_REQUIRED=$container";exit 11; }
done
BASELIVE="$(ident "$LIVE")";BASESTAGE="$(ident "$STAGE")"
BASECANARY="$(ident "$CANARY")";BASECADDY="$(ident "$CADDY")"
BASEFIN="$(counts)";BASECONF="$(sudo -n sha256sum "$HOSTCONF" | awk '{print $1}')"
[[ -s "$OLD_BACKUP" && "$BASECONF" == "$(sha256sum "$OLD_BACKUP" | awk '{print $1}')" ]] ||
 { echo "STAGE30_CADDY_BACKUP_MISMATCH=BLOCKED";exit 12; }
[[ "$BASECONF" == "$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
[[ -z "$(sudo -n docker port "$CANARY")" ]]
[[ "$(sudo -n docker inspect "$CANARY" --format '{{.Image}}')" == "$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')" ]]
echo "STAGE30_CADDY_BACKUP_FINANCIAL_BASELINE=PASS"

echo "=== B. DEPLOY DURABLE INTERNAL RELEASE TARGET WITHOUT PUBLISHING PORTS ==="
STEP=DURABLE_TARGET
for f in "$PGPASS" "$AUTHENV" "$FIREBASE";do
 [[ -f "$f" && ! -L "$f" && "$(stat -c '%a' "$f")" == 600 ]] ||
 { echo "STAGE30_RESTRICTED_CREDENTIAL_FILE=REVIEW_REQUIRED";exit 13; }
done
IMAGE="$(sudo -n docker inspect "$STAGE" --format '{{.Image}}')"
sudo -n docker image inspect "$IMAGE" >/dev/null
if sudo -n docker inspect "$TARGET" >/dev/null 2>&1;then
 echo "STAGE30_DURABLE_TARGET_EXISTING=VERIFYING_WITHOUT_RESTART"
 [[ "$(sudo -n docker inspect "$TARGET" --format '{{.State.Running}}')" == true ]]
 [[ "$(sudo -n docker inspect "$TARGET" --format '{{.Image}}')" == "$IMAGE" ]]
 [[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.NetworkMode}}')" == "$NET" ]]
 [[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.RestartPolicy.Name}}')" == unless-stopped ]]
 [[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.ReadonlyRootfs}}')" == true ]]
 [[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.Privileged}}')" == false ]]
 [[ -z "$(sudo -n docker port "$TARGET")" ]]
 echo "STAGE30_DURABLE_TARGET_EXISTING_SECURITY=PASS"
else
 sudo -n docker run -d --name "$TARGET" \
 --network "$NET" --restart unless-stopped --read-only \
 --tmpfs /tmp:rw,nosuid,nodev,size=64m \
 --cap-drop ALL --security-opt no-new-privileges:true \
 --user "$(id -u):$(id -g)" \
 --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
 --mount "type=bind,source=$PGPASS,target=/run/secrets/sbi_pgpass,readonly" \
 --mount "type=bind,source=$FIREBASE,target=/run/secrets/firebase-stage.json,readonly" \
 --env-file "$AUTHENV" \
 -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-stage.json \
 -e PGHOST=/var/run/postgresql -e PGPORT=5432 \
 -e PGDATABASE="$DB" -e PGUSER=sbi_pr129_report_login \
 -e PGPASSFILE=/run/secrets/sbi_pgpass -e PYTHONDONTWRITEBYTECODE=1 \
 "$IMAGE" >/dev/null
 CREATED=YES
 echo "STAGE30_DURABLE_TARGET_CREATED=PRIVATE_ONLY"
fi
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$TARGET" --format '{{.HostConfig.RestartPolicy.Name}}')" == unless-stopped ]]
[[ -z "$(sudo -n docker port "$TARGET")" ]]
echo "STAGE30_DURABLE_TARGET_POLICY=PASS_RESTART_UNLESS_STOPPED"
echo "STAGE30_DURABLE_TARGET_IMAGE_ID=$IMAGE"

echo "=== C. VERIFY FIREBASE, NO-INVOICE-LOOKUP, PG READ-ONLY AND ANONYMOUS ACCESS ==="
STEP=SECURITY
sudo -n docker exec -i "$TARGET" python3 -B - <<'PY'
from pathlib import Path
import os,google.auth,psycopg
import dashboard_sessions
from app import app
assert google.auth.default()[1]=='meghraj-reconciliation'
assert 'https://pr129.13-232-241-221.sslip.io' in dashboard_sessions.ORIGINS
html=Path('/app/index.html').read_text()
assert 'id="bulk-selected-button" disabled' in html
assert not Path('/app/pr129_aws_invoice_lookup.enabled').exists()
assert not os.getenv('INVOICE_LOOKUP_BACKEND')
c=app.test_client()
for path in ('/api/reporting/v2/postgresql-summary','/api/bulk-report/status'):
 assert c.get(path).status_code in (401,403)
with psycopg.connect(connect_timeout=8) as db:
 db.execute('SET TRANSACTION READ ONLY')
 assert db.execute('SELECT current_user,current_database(),current_setting(%s)',('transaction_read_only',)).fetchone()==('sbi_pr129_report_login','sbi_reconciliation_main','on')
 for table in ('invoices','payments','allocations','credit_notes'):
  assert db.execute('SELECT has_table_privilege(current_user,%s,%s)',('sbi.'+table,'INSERT')).fetchone()[0] is False
 db.execute('SELECT count(*) FROM sbi.invoice_financial_summary').fetchone()
 db.execute('SELECT count(*) FROM sbi.payment_financial_summary').fetchone()
print('STAGE30_RELEASE_FIREBASE_PRODUCTION_ORIGIN=PASS')
print('STAGE30_SELECTED_INVOICE_LOOKUP=DISABLED')
print('STAGE30_POSTGRES_READ_ONLY_VIEWS=PASS')
print('STAGE30_FINANCIAL_INSERT_PRIVILEGES=DENIED')
print('STAGE30_ANONYMOUS_REPORTING=DENIED')
PY

echo "=== D. LONG-WINDOW DIRECT BRIDGE STABILITY WITHOUT NEW HTTP TEST CONTAINERS ==="
STEP=SOAK
TARGET_IP="$(sudo -n docker inspect "$TARGET" --format "{{with index .NetworkSettings.Networks \"$NET\"}}{{.IPAddress}}{{end}}")"
LIVE_IP="$(sudo -n docker inspect "$LIVE" --format "{{with index .NetworkSettings.Networks \"$NET\"}}{{.IPAddress}}{{end}}")"
[[ "$TARGET_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$LIVE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
if python3 -B - "$TARGET_IP" "$LIVE_IP" <<'PY'
import sys,http.client,time,concurrent.futures
target,live=sys.argv[1:]
tests=[('release-login',target,'/login',{200}),
 ('release-report-guard',target,'/api/reporting/v2/postgresql-summary',{401,403}),
 ('release-bulk-guard',target,'/api/bulk-report/status',{401,403}),
 ('live-login',live,'/login',{200})]
def req(t):
 name,host,path,want=t
 start=time.monotonic();status=None
 c=http.client.HTTPConnection(host,8080,timeout=6)
 try:
  c.request('GET',path,headers={'Connection':'close'})
  r=c.getresponse();status=r.status;r.read(256)
 except (OSError,http.client.HTTPException) as e:status=type(e).__name__
 finally:c.close()
 return name,status,round(time.monotonic()-start,2),status in want
errors=0
high_latency=0
for i in range(1,17):
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as p:
  res=list(p.map(req,tests))
 for name,status,seconds,ok in res:
  print('STAGE30_DURABLE_SOAK=round:'+str(i)+' route:'+name+
   ' status:'+str(status)+' seconds:'+str(seconds),flush=True)
  if not ok:errors+=1
  if seconds>3:high_latency+=1
 if i<16:time.sleep(20)
print('STAGE30_DURABLE_SOAK_ROUNDS=16',flush=True)
print('STAGE30_DURABLE_SOAK_HTTP_FAILURES='+str(errors),flush=True)
print('STAGE30_DURABLE_SOAK_SLOW_OVER_3_SECONDS='+str(high_latency),flush=True)
if errors or high_latency:sys.exit(34)
print('STAGE30_DURABLE_SOAK=PASS_16_ROUNDS_WITHOUT_SLOW_RESPONSES')
PY
then echo "STAGE30_SUSTAINED_STABILITY_GATE=PASS_BOUNDED"
else
 echo "STAGE30_SUSTAINED_STABILITY_GATE=BLOCKED"
 FAILURES=$((FAILURES+1))
fi

echo "=== E. PREPARE EXACT CADDY SWITCH AND BYTE-IDENTICAL ROLLBACK ==="
STEP=CADDY_DRYRUN
cp "$OLD_BACKUP" "$DIR/Caddyfile.original"
python3 -B - "$DIR/Caddyfile.original" "$DIR/Caddyfile.proposed" "$OLD_DIAL" "$NEW_DIAL" <<'PY'
from pathlib import Path
import sys
old,new,fromdial,todial=sys.argv[1:]
raw=Path(old).read_bytes()
assert raw.count(fromdial.encode())==1,'Existing PR129 upstream is not unique'
proposed=raw.replace(fromdial.encode(),todial.encode(),1)
assert proposed.replace(todial.encode(),fromdial.encode(),1)==raw,'Rollback parity failed'
Path(new).write_bytes(proposed)
print('STAGE30_EXACT_ONE_ROUTE_REPLACEMENT=PASS')
print('STAGE30_ROLLBACK_BYTE_IDENTICAL=PASS')
PY
chmod 600 "$DIR/Caddyfile.original" "$DIR/Caddyfile.proposed"
sudo -n docker exec -i "$CADDY" caddy adapt --config - --adapter caddyfile \
 < "$DIR/Caddyfile.original" > "$DIR/old.json" 2> "$DIR/old_adapt.log"
sudo -n docker exec -i "$CADDY" caddy adapt --config - --adapter caddyfile \
 < "$DIR/Caddyfile.proposed" > "$DIR/new.json" 2> "$DIR/new_adapt.log"
python3 -B - "$DIR/old.json" "$DIR/new.json" "$OLD_DIAL" "$NEW_DIAL" "$SITE" <<'PY'
import json,sys
old_file,new_file,old_dial,new_dial,site=sys.argv[1:]
before=json.load(open(old_file))
after=json.load(open(new_file))
found=[0]
def replace(o):
 if isinstance(o,list):return [replace(i) for i in o]
 if isinstance(o,dict):
  d={}
  for k,v in o.items():
   if k=='dial' and v==old_dial:
    found[0]+=1;d[k]=new_dial
   else:d[k]=replace(v)
  return d
 return o
assert replace(before)==after and found[0]==1, 'Unexpected Caddy route changes'
matches=[]
def walk(n,hosts):
 if isinstance(n,list):
  for x in n:walk(x,hosts)
 if isinstance(n,dict):
  match=n.get('match')
  if isinstance(match,list):
   h=[x for m in match if isinstance(m,dict) for x in m.get('host',[]) if isinstance(x,str)]
   if h:hosts=set(h)
  if n.get('handler')=='reverse_proxy':
   matches.extend(u.get('dial','') for u in n.get('upstreams',[]) if isinstance(u,dict) and site in hosts)
  for k,v in n.items():
   if k not in ('match','upstreams'):walk(v,hosts)
for server in after.get('apps',{}).get('http',{}).get('servers',{}).values():
 walk(server.get('routes',[]),set())
assert matches==[new_dial], 'Site-specific upstream is not exactly the release target'
print('STAGE30_PROPOSED_CADDY_ROUTE_PARITY=PASS')
PY
sudo -n docker exec -i "$CADDY" caddy validate --config - --adapter caddyfile \
 < "$DIR/Caddyfile.proposed" > "$DIR/validate.log" 2>&1 ||
 { echo "STAGE30_PROPOSED_CADDY_VALIDATE=FAIL";exit 45; }
chmod 600 "$DIR/"*
echo "STAGE30_PROPOSED_CADDY_VALIDATE=PASS"
echo "STAGE30_ROLLBACK_SHA256=$(sha256sum "$DIR/Caddyfile.original" | awk '{print $1}')"
echo "STAGE30_PROPOSED_SHA256=$(sha256sum "$DIR/Caddyfile.proposed" | awk '{print $1}')"

echo "=== F. ENSURE IMMUTABILITY OF LIVE PR129, CADDY AND FINANCIAL DATA ==="
STEP=IMMUTABILITY
[[ "$BASELIVE" == "$(ident "$LIVE")" ]]
[[ "$BASESTAGE" == "$(ident "$STAGE")" ]]
[[ "$BASECANARY" == "$(ident "$CANARY")" ]]
[[ "$BASECADDY" == "$(ident "$CADDY")" ]]
[[ "$BASECONF" == "$(sudo -n sha256sum "$HOSTCONF" | awk '{print $1}')" ]]
[[ "$BASEFIN" == "$(counts)" ]]
echo "STAGE30_LIVE_CADDY_AND_FINANCIAL_IMMUTABILITY=PASS"
STEP=COMPLETE
echo "=== FINAL STAGE30.5 DURABLE RELEASE CANDIDATE READINESS ==="
echo "STAGE30_TARGET_RESTART_DURABILITY=PASS"
echo "STAGE30_SELECTED_LOOKUP_DISABLED=PASS"
echo "STAGE30_POSTGRES_READER_WRITE_DENIAL=PASS"
echo "STAGE30_CADDY_ROUTE_ROLLBACK_DRYRUN=PASS"
echo "STAGE30_AUTHENTICATED_PRODUCTION_E2E=NOT_RETESTED_DURING_THIS_GATE"
echo "STAGE30_NEXT=CONDITIONAL_CONTROLLED_CADDY_SWITCH_WITH_AUTOMATIC_ROLLBACK"
