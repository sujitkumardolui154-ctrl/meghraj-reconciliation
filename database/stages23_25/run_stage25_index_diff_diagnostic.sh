#!/usr/bin/env bash
# Compare the sole changed index.html without printing code or credentials.
# Does not touch live, new staging, Firebase keys or financial data.
set -Eeuo pipefail
umask 077
STEP=PRECHECK
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-stage25-firebase-adc
DB=sbi_reconciliation_main
TEMP=""
finish() {
 rc=$?
 trap - EXIT
 if [[ -n "$TEMP" && "$TEMP" == /tmp/sbi_index_compare_* ]]; then
   sudo -n rm -rf -- "$TEMP" || rc=98
 fi
 if (( rc )); then echo "STAGE25_INDEX_DIFF_QA=FAIL step=$STEP exit=$rc"
 else echo "STAGE25_INDEX_DIFF_QA=PASS";fi
 echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
 exit "$rc"
}
trap finish EXIT
counts() { sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== 1. BASELINE ==="
sudo -n docker info >/dev/null
BEFORE_LIVE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
BEFORE_STAGE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ "$(sudo -n docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]]
[[ "$(sudo -n docker inspect "$STAGE" --format '{{.State.Running}}')" == true ]]
[[ -z "$(sudo -n docker port "$STAGE")" ]]
BEFORE_COUNTS="$(counts)"
echo "PRIVATE_STAGE_UNPUBLISHED=PASS"

echo "=== 2. COPY INDEX FILES INTO SECURE TEMP DIR, OUTPUT METADATA ONLY ==="
STEP=COPY
TEMP="$(mktemp -d /tmp/sbi_index_compare_XXXXXXXX)"
chmod 700 "$TEMP"
sudo -n docker cp "$LIVE:/app/index.html" "$TEMP/live_index.html"
sudo -n docker cp "$STAGE:/app/index.html" "$TEMP/stage_index.html"
sudo -n chown "$(id -u):$(id -g)" "$TEMP/"*.html
chmod 600 "$TEMP/"*.html
[[ -s "$TEMP/live_index.html" && -s "$TEMP/stage_index.html" ]]
echo "HTML_SOURCE_COPIED_LOCALLY=YES"
echo "HTML_SOURCE_PRINTED=NO"

echo "=== 3. COMPARE DOCUMENT STRUCTURE AND UI FEATURES ==="
STEP=DIFF
python3 -B - "$TEMP/live_index.html" "$TEMP/stage_index.html" <<'PY'
from pathlib import Path
from html.parser import HTMLParser
import sys,hashlib,difflib,collections
class Nodes(HTMLParser):
 def __init__(self):
  super().__init__()
  self.tags=collections.Counter()
  self.ids=0
 def handle_starttag(self,tag,attrs):
  self.tags[tag]+=1
  self.ids+=sum(1 for k,v in attrs if k=="id")
def inspect(path,side):
 raw=Path(path).read_bytes()
 text=raw.decode("utf-8",errors="replace")
 parser=Nodes();parser.feed(text)
 print("INDEX_"+side+"_SHA256="+hashlib.sha256(raw).hexdigest())
 print("INDEX_"+side+"_BYTES="+str(len(raw)))
 print("INDEX_"+side+"_LINES="+str(len(text.splitlines())))
 print("INDEX_"+side+"_DOM_IDS="+str(parser.ids))
 for tag in ("div","section","nav","button","script","style","canvas","svg"):
  print("INDEX_"+side+"_TAG_"+tag.upper()+"="+str(parser.tags[tag]))
 for name,needle in [
  ("BULK_REPORT","bulk report"),
  ("PAYMENT_RECONCILIATION","payment reconciliation"),
  ("INVOICE","invoice"),
  ("CHART","chart"),
  ("DASHBOARD","dashboard"),
  ("DATABASE_UPDATE","database update"),
  ("EXCEL_UPLOAD","excel upload"),
  ("CONTROL_CENTER","reconciliation control center"),
  ("POSTGRES_SUMMARY","postgresql-summary"),
 ]:
  print("INDEX_"+side+"_MARKER_"+name+"="+str(needle in text.lower()))
 return text.splitlines(keepends=True)
a=inspect(sys.argv[1],"LIVE")
b=inspect(sys.argv[2],"STAGE25")
changes=[(kind,i+1,j,k+1,l) for kind,i,j,k,l in
         difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes()
         if kind!="equal"]
print("HTML_DIFFERENCE_REGION_COUNT="+str(len(changes)))
print("HTML_CHANGED_LIVE_LINES="+str(sum(j-i+1 for _,i,j,_,l in changes)))
print("HTML_CHANGED_STAGE_LINES="+str(sum(l-k+1 for _,i,j,k,l in changes)))
for index,item in enumerate(changes[:12],1):
 print("HTML_CHANGE_REGION_"+str(index)+"="+",".join(map(str,item)))
print("WHITESPACE_ONLY_CHANGE="+str("".join(a).split()=="".join(b).split()))
print("HTML_PARITY="+("MATCH" if a==b else "DIFFERENT"))
print("HTML_SAFE_COMPARISON=COMPLETE")
PY

echo "=== 4. DASHBOARD HTML SOURCE ROUTE ==="
STEP=ROUTE
for container in "$LIVE" "$STAGE";do
 echo "ROUTE_SOURCE_CONTAINER=$container"
 sudo -n docker exec -i "$container" python3 -B - <<'PY'
from pathlib import Path
import ast
tree=ast.parse(Path("/app/app.py").read_text())
for node in ast.walk(tree):
 if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name=="dashboard":
  names=sorted({ast.unparse(n.func) for n in ast.walk(node) if isinstance(n,ast.Call)})
  print("DASHBOARD_HANDLER_LINE="+str(node.lineno))
  print("DASHBOARD_HANDLER_CALL_NAMES="+",".join(names[:24]))
  refs=sorted({n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value in ("index.html","dashboard.html","/app/index.html")})
  print("DASHBOARD_HTML_FILE_REFS="+(",".join(refs) or "NONE"))
print("DASHBOARD_HANDLER_INSPECTION=COMPLETE")
PY
done

echo "=== 5. PROTECT LIVE AND STAGE 25 ==="
STEP=SAFETY
[[ "$BEFORE_LIVE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BEFORE_STAGE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BEFORE_COUNTS" == "$(counts)" ]]
echo "LIVE_PR129_UNCHANGED=PASS"
echo "STAGE25_UNCHANGED=PASS"
echo "FINANCIAL_RECORD_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL INDEX SOURCE DIAGNOSTIC ==="
echo "INDEX_DIFFERENCE_DIAGNOSIS=PASS"
echo "UI_REPLACEMENT=NOT_PERFORMED"
echo "AUTHORIZED_POSTGRES_REPORT_HTTP=NOT_YET_VERIFIED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=SELECT_APPROVED_MODERN_UI_SOURCE_AND_BUILD_SEPARATE_STAGE25_CANDIDATE"
