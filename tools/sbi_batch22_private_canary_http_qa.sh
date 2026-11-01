#!/usr/bin/env bash
# Batch22: single-step Batch21 follow-through + private canary negative HTTP QA.
# Cloud Run canary deployment may occur only through the existing gated Batch21/20.
# No main-dashboard deployment, traffic switch, IAM grant, or Firestore write.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
PROJECT="meghraj-reconciliation"
REGION="asia-south1"
CANARY="sbi-credit-auth-canary"
REPAIR_RECEIPT="reports/credit_note/batch21_two_blocker_fix.json"
mkdir -p reports/credit_note
chmod 700 reports/credit_note
if [[ "$(gcloud config get-value project 2>/dev/null)" != "$PROJECT" ]]; then
  echo 'BATCH22_RESULT={"decision":"BLOCKED_PROJECT_MISMATCH","main_dashboard_unchanged":true}'
  exit 0
fi
if [[ ! -s "$REPAIR_RECEIPT" ]]; then
  echo "BATCH22 PREREQUISITE: RUNNING BATCH21 ONCE"
  TMP="$(mktemp)"
  trap 'rm -f "$TMP"' EXIT
  curl -fsSL \
    "https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/10e2ce315769e53a37659ab00c83337b19e8473e/tools/sbi_batch21_cookie_requirements_fix.sh" \
    -o "$TMP"
  bash "$TMP"
fi

python3 - <<'PY'
from __future__ import annotations
import datetime
import http.client
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT="meghraj-reconciliation"
REGION="asia-south1"
CANARY="sbi-credit-auth-canary"
ROOT=Path("reports/credit_note")
result={
  "stage":"BATCH22_PRIVATE_CANARY_ACCESS_QA",
  "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "repair":"UNVERIFIED",
  "cookie_static_proof":"UNVERIFIED",
  "candidate_dependencies":"UNVERIFIED",
  "import_completeness":"NOT_CERTIFIED",
  "canary":"NOT_VERIFIED",
  "iam_private":"UNVERIFIED",
  "zero_traffic":"UNVERIFIED",
  "cloud_run_invocation":"NOT_TESTED",
  "unauthenticated_http":"NOT_TESTED",
  "authenticated_iam_login_page":"NOT_TESTED",
  "no_firebase_session_report_denial":"NOT_TESTED",
  "real_signed_in_report_e2e":"PENDING",
  "main_dashboard":"UNCHANGED_BY_THIS_BATCH",
  "reporting_release":"BLOCKED",
  "financial_release":"RESTRICTED",
  "blockers":[],
}
def add(s):
  if s not in result["blockers"]:result["blockers"].append(s)
def cli(args,seconds=35):
  try:
    p=subprocess.run(args,capture_output=True,text=True,timeout=seconds)
    return p.returncode,p.stdout
  except (OSError,subprocess.TimeoutExpired):
    return 99,""
def http(url,token=None):
  # Return status only: never print access tokens, cookies, body, or response URLs.
  request=urllib.request.Request(url,headers={
    "Accept":"text/html,application/json;q=0.8",
    "User-Agent":"SBI-Reporting-Private-QA/1.0",
    **({"Authorization":"Bearer "+token} if token else {}),
  })
  try:
    with urllib.request.urlopen(request,timeout=15) as response:
      response.read(512)
      return response.status
  except urllib.error.HTTPError as e:
    return e.code
  except Exception:
    return "NETWORK_ERROR"

try:
  p=json.loads((ROOT/"batch21_two_blocker_fix.json").read_text(encoding="utf-8"))
  result["repair"]="RECEIPT_PRESENT"
  result["cookie_static_proof"]=p.get("cookie_contract","UNVERIFIED")
  result["candidate_dependencies"]=p.get("package_preflight","UNVERIFIED")
  result["import_completeness"]=p.get("import_completeness","NOT_CERTIFIED")
  result["preflight_resume"]=bool(p.get("canary_resume_allowed",False))
except (OSError,ValueError,TypeError):
  add("BATCH21_RECEIPT_MISSING_OR_INVALID")
if result["cookie_static_proof"]!="ISSUER_READER_STATIC_MATCH":
  add("COOKIE_PROOF_STILL_NOT_VERIFIED")
if result["candidate_dependencies"]!="CANDIDATE_REQUIREMENTS_REPAIRED":
  add("CANARY_DEPENDENCIES_STILL_UNVERIFIED")
if result["import_completeness"]!="V140_NO_APPLIED_IMPORTS_EVIDENCE_PASS":
  add("IMPORT_COMPLETENESS_NOT_CERTIFIED")

# Read only: detect whether the guard from Batch21 actually created a separate canary.
rc,stdout=cli(["gcloud","run","services","describe",CANARY,
               "--project",PROJECT,"--region",REGION,"--format=json"],seconds=45)
service={}
if rc==0:
  try:
    service=json.loads(stdout)
    ready=service.get("status",{}).get("latestReadyRevisionName","")
    result["canary"]="READY" if ready else "NOT_READY"
    result["canary_revision"]=ready or "UNKNOWN"
  except ValueError:
    result["canary"]="UNREADABLE"
if result["canary"]!="READY":
  add("PRIVATE_CANARY_NOT_DEPLOYED_OR_NOT_READY")
else:
  # Public invoker is never allowed.
  rc,policy=cli(["gcloud","run","services","get-iam-policy",CANARY,
                 "--project",PROJECT,"--region",REGION,"--format=json"])
  try:
    iam=json.loads(policy) if rc==0 else {}
    if rc:
      result["iam_private"]="UNVERIFIED"
    else:
      public=any(
        member in ("allUsers","allAuthenticatedUsers")
        for binding in iam.get("bindings",[])
        for member in binding.get("members",[])
      )
      result["iam_private"]="NO_PUBLIC_MEMBERS" if not public else "PUBLIC_MEMBER_FOUND"
  except ValueError:
    result["iam_private"]="UNVERIFIED"
  if result["iam_private"]!="NO_PUBLIC_MEMBERS":
    add("PRIVATE_CANARY_IAM_NOT_VERIFIED")
  traffic=service.get("status",{}).get("traffic",[])
  # Cloud Run may list tagged 0%-traffic canary as tag-only entries.
  active=[t for t in traffic if (t.get("percent",0) or 0)>0]
  result["zero_traffic"]="YES" if not active else "NO"
  if active:
    add("CANARY_TRAFFIC_IS_NOT_ZERO")
  tagged=[t.get("url","") for t in traffic if t.get("tag")=="b20" and t.get("url")]
  # Some Cloud Run services are created with an initial 100%-traffic service
  # even with --no-traffic; preserve safety and fail rather than assert zero.
  if len(tagged)!=1:
    add("UNIQUE_CANARY_TAG_URL_NOT_VERIFIED")
  elif result["iam_private"]=="NO_PUBLIC_MEMBERS" and result["zero_traffic"]=="YES":
    url=tagged[0].rstrip("/")
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or not (
        parsed.hostname.endswith(".run.app") or parsed.hostname.endswith(".a.run.app")):
      add("UNEXPECTED_CANARY_URL")
    else:
      unauthorized=http(url+"/login")
      result["unauthenticated_http"]=unauthorized
      if unauthorized not in (401,403):
        add("IAM_ANONYMOUS_DENIAL_NOT_VERIFIED")
      rc,tok=cli(["gcloud","auth","print-identity-token"],seconds=20)
      token=tok.strip() if rc==0 else ""
      if not token or len(token)<50 or "." not in token:
        add("CLOUD_RUN_CALLER_TOKEN_UNAVAILABLE")
      else:
        login_status=http(url+"/login",token=token)
        result["authenticated_iam_login_page"]=login_status
        if login_status!=200:
          add("CALLER_IAM_INVOCATION_NOT_CONFIRMED")
        else:
          # With a valid Cloud Run IAM token, a request without the browser's
          # Firebase session cookie must fail at the APPLICATION layer.
          denial=http(url+"/reports/credit-note/summary",token=token)
          result["no_firebase_session_report_denial"]=denial
          if denial!=403:
            add("APPLICATION_SESSION_DENIAL_NOT_CONFIRMED")
          else:
            result["cloud_run_invocation"]="IAM_GRANTED_APP_DENIED_ANONYMOUS_SESSION"
      # All token material is kept in memory and never saved to the report.
  elif result["zero_traffic"]=="NO":
    add("CANARY_NOT_ZERO_TRAFFIC")
# Never allow a pass without actual role-allowed and role-denied signed-in tests.
add("REAL_FIREBASE_ROLE_ALLOWED_AND_DENIED_HTTP_TEST_PENDING")
result["reporting_release"]="BLOCKED_REAL_SIGNED_IN_AND_IMPORT_GATES"
out=ROOT/"batch22_private_http_qa.json"
out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
out.chmod(0o600)
fields=("cookie_static_proof","candidate_dependencies","import_completeness",
        "canary","iam_private","zero_traffic","unauthenticated_http",
        "authenticated_iam_login_page","no_firebase_session_report_denial",
        "cloud_run_invocation","real_signed_in_report_e2e","reporting_release",
        "blockers","main_dashboard","financial_release")
print("BATCH22_RESULT="+json.dumps({k:result[k] for k in fields},
                                 separators=(",",":"),ensure_ascii=False))
print("QA RECEIPT:",out)
print("NO MAIN DASHBOARD DEPLOYMENT OR TRAFFIC CHANGE BY BATCH22")
print("BATCH 22 COMPLETE")
PY
