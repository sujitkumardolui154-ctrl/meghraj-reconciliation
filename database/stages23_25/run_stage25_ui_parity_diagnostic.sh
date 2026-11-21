#!/usr/bin/env bash
# Read-only combined UI parity diagnosis for PR129 live vs Stage25 authenticated staging.
# Does NOT deploy, run Docker images, modify routes, touch credentials, access sessions,
# change any Firebase policies, or write financial data.
set -Eeuo pipefail
umask 077
STEP=PRECHECK
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-stage25-firebase-adc
OUT=/home/ubuntu/sbi-ui-parity-diagnostic
DB=sbi_reconciliation_main
trap 'rc=$?; if ((rc));then echo "STAGE25_UI_PARITY_DIAGNOSTIC=FAIL step=$STEP exit=$rc";fi;echo "LIVE_PR129_CUTOVER=NOT_PERFORMED";exit "$rc"' EXIT
sql(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
counts(){ sql "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== 1. BASELINE: VERIFY RUNNING CONTAINERS ==="
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$STAGE" --format '{{.State.Running}}')" == true ]]
[[ -z "$(sudo -n docker port "$STAGE")" ]]
FIN_BEFORE="$(counts)"
echo "STAGE25_PRIVATE_ONLY=PASS"
echo "LIVE_CONTAINER_BASELINE=RECORDED"
mkdir -p "$OUT";chmod 700 "$OUT"; cd "$OUT"

echo "=== 2. HTML/JS/CSS AND DASHBOARD ROUTE INVENTORY ==="
STEP=INVENTORY
for item in "$LIVE" "$STAGE"; do
  case "$item" in
    "$LIVE") short=live ;;
    "$STAGE") short=stage25 ;;
  esac
  echo "--- $short: $item ---"
  sudo -n docker exec -i "$item" python3 -B - <<'PY' | tee "$short.ui.txt"
from pathlib import Path
import hashlib
from collections import Counter
root=Path("/app")
excluded={"node_modules",".git",".venv","__pycache__","site-packages","private","secrets"}
print("UI_AUDIT_VERSION=1")
for name in ("app.py","dashboard_sessions.py","cloud_auth.py",
             "sbi_report_access.py","bulk_reports.py","readonly_reports_gateway.py",
             "pg_reporting_blueprint.py","sbi_pg_reporting.py","index.html"):
    p=root/name
    if p.is_file():
        print("BACKEND_FILE="+name+" SHA256="+hashlib.sha256(p.read_bytes()).hexdigest())
    else:
        print("BACKEND_FILE="+name+" STATUS=ABSENT")
assets=[]
searched=0
for p in root.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in (".html",".js",".mjs",".css"):
        continue
    if any(part in excluded for part in p.parts):
        continue
    searched+=1
    if searched>2000: break
    try:
        if p.stat().st_size>10000000: continue
        name=p.relative_to(root).as_posix()
        if any(token in name.lower() for token in ("credential","secret","private-key","password",".min.map")):
            continue
        data=p.read_bytes()
    except (OSError,UnicodeError):continue
    assets.append((name,hashlib.sha256(data).hexdigest(),len(data)))
print("UI_ASSET_COUNT="+str(len(assets)))
for name,sha,size in sorted(assets)[:120]:
    print("UI_FILE="+name+" SHA256="+sha+" BYTES="+str(size))
if len(assets)>120:print("UI_FILE_LIST_TRUNCATED=YES")
try:
    from app import app
    paths=("/","/login","/dashboard","/reports","/api/reporting/v2",
           "/api/reporting/v2/postgresql-summary")
    route_map={x:[] for x in paths}
    for rule in app.url_map.iter_rules():
        if rule.rule in route_map:
            h=app.view_functions.get(rule.endpoint)
            route_map[rule.rule].append((h.__module__,h.__name__) if h else ("NONE","NONE"))
    for route in paths:
        handlers=route_map[route]
        print("ROUTE_PATH="+route+" HANDLERS="+(",".join(".".join(item) for item in handlers) if handlers else "NONE"))
except Exception as exc:
    print("ROUTE_INSPECTION=ERROR_"+type(exc).__name__)
print("UI_INVENTORY=COMPLETE")
PY
  grep -qx "UI_INVENTORY=COMPLETE" "$short.ui.txt"
done

echo "=== 3. COMPARE FRONTEND DIGESTS (NO SOURCE CONTENT OR SECRET VALUES) ==="
STEP=COMPARE
awk '/^UI_FILE=/{print}' live.ui.txt | sort > live.assets.txt
awk '/^UI_FILE=/{print}' stage25.ui.txt | sort > stage25.assets.txt
python3 -B - <<'PY'
from pathlib import Path
def parse(path):
    files={}
    for line in Path(path).read_text().splitlines():
        if not line.startswith("UI_FILE="):continue
        body=line[len("UI_FILE="):]
        if " SHA256=" not in body:continue
        name,rest=body.split(" SHA256=",1)
        files[name]=rest.split(" ",1)[0]
    return files
live=parse("live.assets.txt")
stage=parse("stage25.assets.txt")
shared=set(live)&set(stage)
different=[p for p in shared if live[p]!=stage[p]]
live_only=sorted(set(live)-set(stage))
stage_only=sorted(set(stage)-set(live))
print("UI_FILES_SHARED="+str(len(shared)))
print("UI_FILES_DIFFERENT="+str(len(different)))
print("UI_FILES_ONLY_LIVE="+str(len(live_only)))
print("UI_FILES_ONLY_STAGE25="+str(len(stage_only)))
for kind,values in (("UI_DIFFERENT",different),("UI_ONLY_LIVE",live_only),("UI_ONLY_STAGE25",stage_only)):
    for name in sorted(values)[:25]:
        print(kind+"="+name)
    if len(values)>25:print(kind+"_TRUNCATED=YES")
backend={}
for side in ("live","stage25"):
    backend[side]={}
    for line in Path(side+".ui.txt").read_text().splitlines():
        if line.startswith("BACKEND_FILE="):
            body=line[len("BACKEND_FILE="):]
            name,rest=body.split(" ",1)
            backend[side][name]=rest
for name in sorted(set(backend["live"])|set(backend["stage25"])):
    a=backend["live"].get(name,"MISSING")
    b=backend["stage25"].get(name,"MISSING")
    print("BACKEND_PARITY="+name+" STATUS="+("MATCH" if a==b else "DIFF_OR_MISSING"))
if different or live_only or stage_only:
    print("FRONTEND_PARITY=DIFFERENT_OR_MISSING")
elif not live and not stage:
    print("FRONTEND_PARITY=NO_ASSETS_FOUND")
else:
    print("FRONTEND_PARITY=MATCH_FOR_LISTED_ASSETS")
PY

echo "=== 4. CHECK DEPLOYMENT AND DB UNCHANGED ==="
STEP=SAFETY
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$FIN_BEFORE" == "$(counts)" ]]
[[ -z "$(sudo -n docker port "$STAGE")" ]]
echo "LIVE_PR129_CONTAINER_UNCHANGED=PASS"
echo "STAGE25_CONTAINER_UNCHANGED=PASS"
echo "FINANCIAL_COUNTS_UNCHANGED=PASS"
STEP=COMPLETE
echo "=== FINAL STAGE25 UI PARITY SUMMARY ==="
echo "STAGE25_UI_PARITY_DIAGNOSTIC=PASS"
echo "AUTHENTICATED_USER_SCREEN=OBSERVED_BY_OWNER_NOT_PROGRAMMATICALLY_VERIFIED"
echo "POSTGRES_AUTHORIZED_REPORT_ENDPOINT=NOT_YET_VERIFIED"
echo "FRONTEND_REPAIR=NOT_PERFORMED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "NEXT=IDENTIFY_LATEST_APPROVED_UI_BUILD_AND_PORT_TO_ISOLATED_STAGE25_WITHOUT_REPLACING_AUTH_OR_POSTGRES"
