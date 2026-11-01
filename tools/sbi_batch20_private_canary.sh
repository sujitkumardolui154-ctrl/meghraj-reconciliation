#!/usr/bin/env bash
# SBI Batch 20: private zero-traffic reporting canary rehearsal.
# Never modifies the active main dashboard service, Firestore, or financial engine.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
ROOT="$PWD"
RECEIPT="reports/credit_note/batch20_private_canary.json"
PREREQ="reports/credit_note/batch19_release_candidate.json"
if [ ! -s "$PREREQ" ]; then
  echo "BATCH19: Running prerequisite once"
  TEMP="$(mktemp)"
  trap 'rm -f "$TEMP"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/89d3098e2ecc0cd21a0c6c961e6973dfc4975679/tools/sbi_batch19_fast_track_candidate.sh" -o "$TEMP"
  bash "$TEMP"
fi
python3 - <<'PY'
from pathlib import Path
import ast, json, re, subprocess
from datetime import datetime, timezone

root=Path("dashboard_source")
out=Path("reports/credit_note/batch20_private_canary.json")
prior=Path("reports/credit_note/batch19_release_candidate.json")
candidate=Path("staging_candidates/sbi_credit_report_batch19")
project="meghraj-reconciliation"
region="asia-south1"
bucket="meghraj-sbi-reports-private-109590290120"
service="sbi-credit-auth-canary"
snapshot="gs://"+bucket+"/credit-note/snapshot-20261101T110857Z"
result={"batch":"20","utc":datetime.now(timezone.utc).isoformat(),
 "project":project,"private_canary":service,
 "prior_release_check":"UNKNOWN","cookie_name":"UNVERIFIED",
 "build_source":"NOT_VERIFIED","bucket_security":"NOT_VERIFIED",
 "cloud_run_preflight":"NOT_VERIFIED","service_account":"UNVERIFIED",
 "main_dashboard_modified":False,"financial_execution":"RESTRICTED",
 "can_deploy":False,"blockers":[]}
def block(name):
    if name not in result["blockers"]:result["blockers"].append(name)
def command(args,timeout=50):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout
    except (OSError,subprocess.TimeoutExpired):
        return 99,""
def varval(expr,known):
    if isinstance(expr,ast.Constant) and isinstance(expr.value,str):
        return expr.value
    if isinstance(expr,ast.Name):return known.get(expr.id)
    if isinstance(expr,ast.Call) and isinstance(expr.func,ast.Attribute):
        if expr.func.attr in ("getenv","get"):
            for arg in expr.args[1:2]:
                if isinstance(arg,ast.Constant) and isinstance(arg.value,str):
                    return arg.value
    return None
try:
    p=json.loads(prior.read_text(encoding="utf-8"))
    result["prior_release_check"]=p.get("reporting_release","UNKNOWN")
    result["import_completeness"]=p.get("import_completeness","NOT_CERTIFIED")
    result["auth_synthetic"]=p.get("auth_synthetic","NOT_VERIFIED")
    if p.get("isolated_app_candidate")!="PREPARED_AUTH_ROUTE_MOUNTED_OFFLINE":
        block("BATCH19_ISOLATED_CANDIDATE_NOT_READY")
    if p.get("auth_synthetic")!="PASS_SYNTHETIC":
        block("SYNTHETIC_AUTH_CHECK_NOT_PASSED")
except (ValueError,OSError):
    block("BATCH19_RESULT_MISSING_OR_INVALID")
# Determine cookie name from the actual session issuer's call tree. Never invent it.
session=root/"dashboard_sessions.py"
cookie=None
if session.is_file():
    try:
        tree=ast.parse(session.read_text(encoding="utf-8"),filename=str(session))
        known={}
        for n in tree.body:
            if isinstance(n,(ast.Assign,ast.AnnAssign)):
                targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t,ast.Name) and "COOKIE" in t.id.upper():
                        v=varval(n.value,known)
                        if v and re.fullmatch(r"[A-Za-z0-9_-]{2,60}",v):
                            known[t.id]=v
        issuer=set();reader=set()
        for n in ast.walk(tree):
            if not isinstance(n,ast.Call) or not isinstance(n.func,ast.Attribute):
                continue
            if not n.args:continue
            name=n.func.attr
            value=varval(n.args[0],known)
            if not value or not re.fullmatch(r"[A-Za-z0-9_-]{2,60}",value):continue
            if name=="set_cookie":issuer.add(value)
            if name=="get" and isinstance(n.func.value,ast.Attribute) and n.func.value.attr=="cookies":
                reader.add(value)
        matches=issuer&reader
        if len(matches)==1:
            cookie=matches.pop()
            result["cookie_name"]=cookie
            result["cookie_mapping"]="SAME_COOKIE_ISSUED_AND_READ"
        else:
            result["cookie_mapping"]="UNIQUE_ISSUER_READER_PAIR_NOT_PROVEN"
            result["cookie_issuer_candidates"]=len(issuer)
            result["cookie_reader_candidates"]=len(reader)
            block("EXACT_FIREBASE_SESSION_COOKIE_NAME_NOT_PROVEN")
    except (OSError,SyntaxError,UnicodeError):
        block("SESSION_SOURCE_UNREADABLE")
else:
    block("SESSION_SOURCE_MISSING")
# Require the prepared role-specific gateway, source and dependencies.
req=candidate/"requirements.txt"
proc=candidate/"Procfile"
required=("flask","gunicorn","firebase-admin","google-cloud-storage")
if candidate.is_dir():
    py=[candidate/name for name in ("production_gateway.py","sbi_credit_report_auth.py","sbi_credit_report_auth_bridge.py")]
    try:
        if any(not f.is_file() for f in py) or not req.is_file():
            block("CANDIDATE_SOURCE_OR_REQUIREMENTS_MISSING")
        else:
            for f in py:ast.parse(f.read_text(encoding="utf-8"),filename=str(f))
            contents=req.read_text(encoding="utf-8").lower()
            missing=[name for name in required if not re.search(r"(?m)^\s*"+re.escape(name)+r"\b",contents)]
            if missing:
                result["missing_packages"]=missing
                block("CANDIDATE_REQUIREMENTS_INCOMPLETE")
            else:
                bridge=py[-1].read_text(encoding="utf-8")
                app=py[0].read_text(encoding="utf-8")
                if ('claims.get("sbi_credit_report_viewer") is True' not in bridge
                    or 'claims.get("admin") is True' in bridge
                    or 'verify_session_cookie(cookie,check_revoked=True)' not in bridge
                    or 'app.register_blueprint(create_credit_note_blueprint(may_view_credit_note))' not in app):
                    block("REPORT_ROLE_GUARD_MISSING_OR_CHANGED")
                else:
                    result["build_source"]="SOURCE_AND_ROLE_GUARD_PRECHECK_PASS"
        # Don't ship private invoices or credential files from the source directory.
        forbidden=[]
        for item in candidate.rglob("*"):
            if item.is_symlink():forbidden.append(str(item.relative_to(candidate)))
            if item.is_file() and item.suffix.lower() in (".csv",".xlsx",".xls",".db",".sqlite",".pem",".p12",".pfx",".key",".zip",".tar"):
                forbidden.append(str(item.relative_to(candidate)))
        if forbidden:
            result["excluded_file_count"]=len(forbidden)
            block("CANDIDATE_HAS_DATA_OR_KEY_FILES")
    except (OSError,UnicodeError,SyntaxError):
        block("CANDIDATE_SOURCE_PARSE_FAILURE")
else:
    block("CANDIDATE_FOLDER_MISSING")
# Verify exact target Cloud project.
rc,current=command(["gcloud","config","get-value","project"])
if rc or current.strip()!=project:
    block("CLOUD_PROJECT_MISMATCH")
else:
    rc,text=command(["gcloud","storage","buckets","describe","gs://"+bucket,"--raw","--format=json"])
    try:
        iam=json.loads(text).get("iamConfiguration",{})
        if rc or iam.get("publicAccessPrevention")!="enforced" or not iam.get("uniformBucketLevelAccess",{}).get("enabled"):
            block("REPORT_BUCKET_NOT_PRIVATE")
        else:result["bucket_security"]="PASS"
    except ValueError:block("REPORT_BUCKET_SECURITY_UNVERIFIED")
    # New canary only; refuse to overwrite an existing Cloud Run service.
    rc,_=command(["gcloud","run","services","describe",service,
                  "--project",project,"--region",region,"--format=json"])
    if rc==0:block("CANARY_SERVICE_ALREADY_EXISTS_STOP_FOR_REVIEW")
    # Reuse already-reviewed private report staging identity; don't grant new IAM permissions.
    rc,text=command(["gcloud","run","services","describe","sbi-chat-report-stage-v1",
                     "--project",project,"--region",region,"--format=json"])
    if rc:
        block("PRIVATE_STAGING_SERVICE_UNAVAILABLE")
    else:
        try:
            stage=json.loads(text)
            sa=stage.get("spec",{}).get("template",{}).get("spec",{}).get("serviceAccountName")
            if not sa or not re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+",sa):
                block("STAGING_SERVICE_ACCOUNT_NOT_EXPLICIT")
            else:result["service_account"]=sa
        except ValueError:block("PRIVATE_STAGING_RUNTIME_UNVERIFIED")
    rc,text=command(["gcloud","run","services","describe","sbi-dashboard",
                     "--project",project,"--region",region,"--format=json"])
    try:
        if rc:raise ValueError()
        main=json.loads(text)
        result["main_ready_revision_before"]=main.get("status",{}).get("latestReadyRevisionName","UNKNOWN")
        result["main_traffic_before"]=[
            {k:x.get(k) for k in ("revisionName","percent","tag") if k in x}
            for x in main.get("status",{}).get("traffic",[])]
    except ValueError:block("MAIN_DASHBOARD_REVISION_BASELINE_UNVERIFIED")
# Cloud Run deployment is only a rehearsal into a separate private service.
# Import certification and real signed-in HTTP remain independent requirements.
result["can_deploy"]=not result["blockers"]
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
out.chmod(0o600)
print("BATCH20_PREFLIGHT="+json.dumps({
 "can_deploy":result["can_deploy"],"cookie_name_mapping":result.get("cookie_mapping","NOT_VERIFIED"),
 "bucket":result["bucket_security"],"candidate":result["build_source"],
 "import_completeness":result.get("import_completeness","NOT_CERTIFIED"),
 "blockers":result["blockers"]},separators=(",",":")))
PY

READY="$(python3 -c 'import json;print("yes" if json.load(open("reports/credit_note/batch20_private_canary.json"))["can_deploy"] else "no")')"
if [ "$READY" != "yes" ]; then
  echo 'BATCH20_RESULT={"canary":"NOT_DEPLOYED","main_dashboard":"UNCHANGED","financial":"RESTRICTED","action":"FIX_REPORTED_PREFLIGHT_BLOCKERS"}'
  echo "BATCH 20 COMPLETE"
  exit 0
fi

# A clear startup command only in the private candidate directory.
CANDIDATE="staging_candidates/sbi_credit_report_batch19"
if [ -e "$CANDIDATE/Procfile" ]; then
  if [ "$(cat "$CANDIDATE/Procfile")" != 'web: gunicorn --bind :$PORT production_gateway:app' ]; then
    echo 'BATCH20_RESULT={"canary":"NOT_DEPLOYED","reason":"UNEXPECTED_STARTUP_PROCFILE"}'
    exit 0
  fi
else
  printf '%s\n' 'web: gunicorn --bind :$PORT production_gateway:app' > "$CANDIDATE/Procfile"
  chmod 600 "$CANDIDATE/Procfile"
fi
COOKIE="$(python3 -c 'import json;print(json.load(open("reports/credit_note/batch20_private_canary.json"))["cookie_name"])')"
SA="$(python3 -c 'import json;print(json.load(open("reports/credit_note/batch20_private_canary.json"))["service_account"])')"
SNAPSHOT="gs://meghraj-sbi-reports-private-109590290120/credit-note/snapshot-20261101T110857Z"
LOG="reports/credit_note/batch20_deploy_$(date -u +%Y%m%dT%H%M%SZ).log"
set +e
gcloud run deploy sbi-credit-auth-canary \
  --source "$CANDIDATE" \
  --project meghraj-reconciliation \
  --region asia-south1 \
  --service-account "$SA" \
  --set-env-vars "SBI_CREDIT_SESSION_COOKIE_NAME=$COOKIE,SBI_CREDIT_GCS_PREFIX=$SNAPSHOT" \
  --no-allow-unauthenticated \
  --ingress all \
  --no-traffic \
  --tag b20 \
  --quiet >"$LOG" 2>&1
DEPLOY_RC=$?
set -e
chmod 600 "$LOG"
if [ "$DEPLOY_RC" -ne 0 ]; then
  echo 'BATCH20_RESULT={"canary":"DEPLOY_FAILED","main_dashboard":"UNCHANGED","financial":"RESTRICTED"}'
  echo "PRIVATE DEPLOY LOG: $LOG"
  tail -12 "$LOG"
  echo "BATCH 20 COMPLETE"
  exit 0
fi
python3 - <<'PY'
import json,subprocess
from pathlib import Path
path=Path("reports/credit_note/batch20_private_canary.json")
r=json.loads(path.read_text())
def desc(name):
    p=subprocess.run(["gcloud","run","services","describe",name,
        "--project","meghraj-reconciliation","--region","asia-south1",
        "--format=json"],capture_output=True,text=True,timeout=40)
    return json.loads(p.stdout) if p.returncode==0 else {}
canary=desc("sbi-credit-auth-canary")
main=desc("sbi-dashboard")
rev=canary.get("status",{}).get("latestReadyRevisionName")
traffic=canary.get("status",{}).get("traffic",[])
zero=bool(rev) and all(x.get("percent",0)==0 for x in traffic if x.get("revisionName")==rev)
current_main=[
    {k:x.get(k) for k in ("revisionName","percent","tag") if k in x}
    for x in main.get("status",{}).get("traffic",[])]
main_unchanged=current_main==r.get("main_traffic_before") and bool(main)
policy=subprocess.run(["gcloud","run","services","get-iam-policy",
    "sbi-credit-auth-canary","--project","meghraj-reconciliation","--region",
    "asia-south1","--format=json"],capture_output=True,text=True,timeout=40)
try:
    iam=json.loads(policy.stdout) if policy.returncode==0 else {}
    public=any(member in ("allUsers","allAuthenticatedUsers") for b in iam.get("bindings",[]) for member in b.get("members",[]))
    private=(policy.returncode==0 and not public)
except ValueError:
    private=False
r.update({"canary_ready_revision":rev or "UNVERIFIED",
          "canary_zero_traffic":zero,"canary_iam_private":private,
          "main_dashboard_traffic_unchanged":main_unchanged,
          "real_user_signed_in_e2e":"PENDING",
          "reporting_production":"BLOCKED_UNTIL_REAL_AUTH_E2E_AND_IMPORT_CERTIFICATION"})
path.write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8")
path.chmod(0o600)
status="PRIVATE_CANARY_READY" if (zero and private and main_unchanged) else "CANARY_SECURITY_REVIEW_REQUIRED"
print("BATCH20_RESULT="+json.dumps({
    "status":status,"ready_revision":rev,"private_iam":private,
    "zero_canary_traffic":zero,"main_dashboard_unchanged":main_unchanged,
    "real_signed_in_http_e2e":"PENDING","import_completeness":r.get("import_completeness"),
    "financial":"RESTRICTED"},separators=(",",":")))
print("BATCH 20 COMPLETE")
PY
