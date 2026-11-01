#!/usr/bin/env bash
# SBI Consolidated Reporting Release Gate v1: one-shot, fail-closed, read-only.
# Stage evidence is reused; no deployment, financial action, or Cloud Run traffic mutation.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
import ast
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

PROJECT="meghraj-reconciliation"
REGION="asia-south1"
BUCKET="meghraj-sbi-reports-private-109590290120"
SNAPSHOT="credit-note/snapshot-20261101T110857Z"
output={
  "schema":"SBI_REPORTING_RELEASE_GATE_V1",
  "checked_utc":datetime.now(timezone.utc).isoformat(),
  "project":PROJECT,"release_track":"REPORTING_ONLY",
  "checks":{},
  "blocking_items":[],
  "financial_execution":"RESTRICTED",
  "deployment_performed":False,
  "production_traffic_changed":False,
  "main_dashboard_source_modified":False
}
checks=output["checks"]
def flag(name,ok,detail=None,blocks=True):
    checks[name]={"pass":bool(ok),"detail":detail}
    if blocks and not ok:output["blocking_items"].append(name)
def invoke(args,timeout=45):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return r.returncode,r.stdout.strip()
    except (OSError,subprocess.TimeoutExpired):
        return 98,""
code,pj=invoke(["gcloud","config","get-value","project"])
flag("correct_google_project",code==0 and pj==PROJECT,pj if code==0 else "UNKNOWN")
folder=Path("reports/credit_note")
manifests=sorted(folder.glob("SBI_CREDIT_NOTE_ALL_INVOICES_*.json"),key=lambda p:p.stat().st_mtime)
manifest={}
report=None
if manifests:
    mfile=manifests[-1]
    report=mfile.with_suffix(".csv")
    try:manifest=json.loads(mfile.read_text(encoding="utf-8"))
    except (ValueError,OSError):manifest={}
else:
    mfile=None
raw_hash=None
csv_valid=False
observed=set();by_invoice=defaultdict(set)
rows=0
if report and report.is_file() and manifest:
    try:
        raw_hash=hashlib.sha256(report.read_bytes()).hexdigest()
        if raw_hash == manifest.get("report_sha256"):
            with report.open("r",encoding="utf-8-sig",newline="") as f:
                reader=csv.reader(f)
                header=next(reader,None)
                if header and len(header)==18 and header[17]=="Credi note":
                    csv_valid=True
                    pattern=re.compile(r"(?<![A-Z0-9])CREDIT[\s._/:-]+NOR?TE(?![A-Z])",re.I)
                    for line in reader:
                        if len(line)!=18:
                            csv_valid=False;break
                        rows+=1
                        match=bool(pattern.search(line[16]))
                        if line[17] != ("CREDIT NOTE" if match else ""):
                            csv_valid=False;break
                        invoice=line[8].strip()
                        if invoice:
                            by_invoice[invoice].add(match)
                            if match:observed.add(invoice)
    except (ValueError,OSError,UnicodeError):
        csv_valid=False
conflicts=[invoice for invoice,values in by_invoice.items() if len(values)>1]
confirmed=len(observed.difference(conflicts))
expected={
 "all_invoice_rows":rows,
 "credit_note_unique_invoices":len(observed),
 "credit_note_confirmed_unique_invoices":confirmed,
 "conflicting_duplicate_invoice_numbers":len(conflicts)
}
counts_ok=csv_valid and all(manifest.get(k)==v for k,v in expected.items())
flag("report_integrity_and_updated_phrase_rule",
     counts_ok and raw_hash==manifest.get("report_sha256"),
     {"rows":rows,"observed":len(observed),"unambiguous":confirmed,
      "conflicts":len(conflicts),"sha256_pass":raw_hash==manifest.get("report_sha256")})
flag("report_accepted_snapshot",bool(manifest) and
     manifest.get("release_status")=="REVIEW_REQUIRED" and
     rows==14374 and len(observed)==1009 and confirmed==1004 and len(conflicts)==5,
     {"status":manifest.get("release_status","UNKNOWN"),"review_conflicts_preserved":len(conflicts)==5})
review_files=sorted(folder.glob("CREDIT_NOTE_CONFLICT_REVIEW_*.csv"),key=lambda p:p.stat().st_mtime)
flag("private_conflict_review_file_present",bool(review_files))
# Pending if receipt validation cannot prove all completed imports were included.
# 0 imported rows is NOT proof that there are no pending import receipts.
imports=manifest.get("completed_import_rows")
flag("completed_import_completeness_certified",False,
     {"rows_in_report":imports,"reason":"Receipt ledger and snapshot freshness not independently certified"})
# Private GCS configuration. No content or credentials are printed.
code,raw=invoke(["gcloud","storage","buckets","describe","gs://"+BUCKET,"--raw","--format=json"])
bucket_ok=False
if code==0:
    try:
        i=json.loads(raw).get("iamConfiguration",{})
        bucket_ok=(i.get("publicAccessPrevention")=="enforced" and
                   i.get("uniformBucketLevelAccess",{}).get("enabled") is True)
    except (ValueError,TypeError): pass
flag("private_bucket_security",bucket_ok)
objects=[]
for basename in ("report.csv","manifest.json","conflicts.csv"):
    path=f"gs://{BUCKET}/{SNAPSHOT}/{basename}"
    rc,_=invoke(["gcloud","storage","ls",path],timeout=45)
    objects.append(rc==0)
flag("private_snapshot_objects",all(objects),
     {"report_csv":objects[0],"manifest":objects[1],"conflict_review":objects[2]})
# Cloud Run staging is private and existing revision ready; previous HTTP PASS is reused,
# not falsely represented as a fresh signed-in real-user test.
def service(name):
    rc,stdout=invoke(["gcloud","run","services","describe",name,
        "--region="+REGION,"--project="+PROJECT,"--format=json"],timeout=50)
    if rc!=0:return {}
    try:return json.loads(stdout)
    except ValueError:return {}
stage=service("sbi-chat-report-stage-v1")
main=service("sbi-dashboard")
stage_ready=bool(stage.get("status",{}).get("latestReadyRevisionName"))
flag("private_staging_revision_ready",stage_ready,
     {"ready_revision":stage.get("status",{}).get("latestReadyRevisionName","UNVERIFIED"),
      "earlier_real_credit_note_http_qa":"USER_REPORTED_PASS"})
flag("main_dashboard_revision_discoverable",
     bool(main.get("status",{}).get("latestReadyRevisionName")),
     {"ready_revision":main.get("status",{}).get("latestReadyRevisionName","UNVERIFIED")})
# Source contract review of real production app; do NOT infer report authorization from
# session-cookie existence alone. No code executes from production_gateway.py.
source=Path("dashboard_source/production_gateway.py")
sessions=Path("dashboard_source/dashboard_sessions.py")
feature=Path("dashboard_source/sbi_credit_report_auth.py")
source_ok=all(p.is_file() for p in (source,sessions,feature))
has_session_install=False
route_attached=False
has_cookie_validation=False
if source_ok:
    try:
        pro=ast.parse(source.read_text(encoding="utf-8"),filename=str(source))
        st=ast.parse(sessions.read_text(encoding="utf-8"),filename=str(sessions))
        calls={n.func.id for n in ast.walk(pro) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        has_session_install="install_sessions" in calls
        route_attached=bool(calls.intersection({"install_credit_note_main","create_credit_note_blueprint"}))
        has_cookie_validation=any(
            isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and n.func.attr=="verify_session_cookie" for n in ast.walk(st))
    except (SyntaxError,OSError,UnicodeError):
        source_ok=False
flag("production_session_cookie_verification_source",source_ok and
     has_session_install and has_cookie_validation,
     {"production_separate_app":True,
      "install_sessions_called":has_session_install,
      "firebase_cookie_verification_present":has_cookie_validation})
flag("main_report_routes_attached_with_permission",route_attached,
     {"route_registration_found":route_attached,
      "role_policy_real_session_verified":False})
# Per-user role, login/logout, expiration and real HTTP access must be tested on a zero-traffic
# candidate revision before a production designation.
flag("authenticated_real_user_and_anonymous_http_e2e",False,
     {"reason":"No verified real-session, revoked-cookie, role-denial and logout HTTP evidence"})
# The 5 conflicting invoice numbers may be shown in a review-only report, never silently settled.
output["report_review_status"]="REVIEW_REQUIRED"
output["report_financial_status"]="NON_SETTLEMENT_READ_ONLY"
output["reporting_release_decision"]=("REPORTING_ONLY_GATE_PASS" if not output["blocking_items"]
                                      else "REPORTING_ONLY_BLOCKED")
output["financial_release_decision"]="BLOCKED_SEPARATE_FINANCIAL_QA"
outdir=Path("reports")
outdir.mkdir(exist_ok=True)
out=outdir/"consolidated_reporting_release_gate.json"
out.write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
out.chmod(0o600)
summary={
 "report_integrity_pass":checks["report_integrity_and_updated_phrase_rule"]["pass"],
 "credit_note_rows":rows,"credit_note_unique":len(observed),
 "unambiguous_credit_note":confirmed,"conflicts":len(conflicts),
 "private_bucket_pass":checks["private_bucket_security"]["pass"],
 "snapshot_objects_pass":checks["private_snapshot_objects"]["pass"],
 "staging_revision_ready":stage_ready,
 "main_report_routes_attached":route_attached,
 "production_session_source_verified":checks["production_session_cookie_verification_source"]["pass"],
 "blockers":output["blocking_items"],
 "reporting_release":output["reporting_release_decision"],
 "financial_release":output["financial_release_decision"],
 "report_json":str(out)
}
print("===== CONSOLIDATED SBI RELEASE GATE =====")
print("COMBINED_RELEASE_RESULT="+json.dumps(summary,separators=(",",":"),ensure_ascii=False))
print("DATABASE WRITES / CLOUD DEPLOYMENT: NONE")
print("MAIN DASHBOARD TRAFFIC: UNCHANGED")
print("FINANCIAL EXECUTION: RESTRICTED")
print("COMBINED GATE COMPLETE")
PY
