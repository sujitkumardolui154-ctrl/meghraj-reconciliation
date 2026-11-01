#!/usr/bin/env bash
# Batch 18: advance the three-blocker correction to an auth-gated staging candidate.
# Reuses previous completed QA. No Cloud Run deployment or financial/database writes.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
import ast, importlib.util, json, os, re, shutil, sys, types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from flask import Flask

correction_path=Path("reports/consolidated_reporting_correction.json")
out_path=Path("reports/consolidated_reporting_next_gate.json")
candidate=Path("reports/credit_note/batch17_candidate")
feature_file=Path("dashboard_source/sbi_credit_report_auth.py")
sessions_file=Path("dashboard_source/dashboard_sessions.py")

result={
  "gate":"SBI_BATCH18_REPORTING_AUTH_CANDIDATE",
  "utc":datetime.now(timezone.utc).isoformat(),
  "prior_9_of_12_checks":"REUSED_NOT_RERUN",
  "import_completeness":"NOT_CERTIFIED",
  "private_auth_candidate":"NOT_VERIFIED",
  "cookie_name_source":"NOT_IDENTIFIED",
  "local_http_auth_tests":"NOT_RUN",
  "main_dashboard_routes_attached":False,
  "real_signed_in_http_e2e":"PENDING",
  "reporting_production":"BLOCKED",
  "financial_production":"BLOCKED_SEPARATE_FINANCIAL_QA",
  "no_deployment":True,
  "no_firestore_writes":True,
  "issues":[]
}
def issue(s):
    if s not in result["issues"]:result["issues"].append(s)

if not correction_path.is_file():
    issue("COMBINED_CORRECTION_RECEIPT_MISSING")
else:
    try:
        prior=json.loads(correction_path.read_text(encoding="utf-8"))
        result["import_completeness"]=prior.get("import_completeness","NOT_CERTIFIED")
        result["import_evidence"]=prior.get("import_evidence",{})
        result["prior_candidate_status"]=prior.get("role_protected_candidate","UNKNOWN")
        result["prior_issues"]=prior.get("issues",[])
        if result["import_completeness"]!="V140_NO_APPLIED_IMPORTS_EVIDENCE_PASS":
            issue("IMPORT_LEDGER_COMPLETENESS_NOT_PROVEN")
    except (OSError,ValueError,TypeError):
        issue("COMBINED_CORRECTION_RECEIPT_INVALID")

bridge=candidate/"sbi_credit_report_auth_bridge.py"
app_candidate=candidate/"production_gateway_candidate.py"
if not all(p.is_file() for p in (bridge,app_candidate,feature_file,sessions_file)):
    issue("AUTH_CANDIDATE_OR_SOURCE_MISSING")
else:
    try:
        original_bridge=bridge.read_text(encoding="utf-8")
        original_app=app_candidate.read_text(encoding="utf-8")
        if "SBI_CREDIT_FIREBASE_ROLE_BRIDGE_V1" not in original_bridge:
            raise ValueError("unrecognized role bridge")
        if "SBI_CREDIT_AUTH_ONLY_ZERO_TRAFFIC_CANDIDATE_V1" not in original_app:
            raise ValueError("unrecognized isolated app candidate")
        if "SBI_AUTHORIZED_CREDIT_REPORT_V1" not in feature_file.read_text(encoding="utf-8"):
            raise ValueError("unrecognized approved report module")
        # Scope roles to an explicit report permission only: never infer access
        # from generic admin or login status.
        old='return claims.get("sbi_credit_report_viewer") is True or claims.get("admin") is True'
        new='return claims.get("sbi_credit_report_viewer") is True'
        if old in original_bridge:
            hardened=original_bridge.replace(old,new,1)
        elif new in original_bridge and old not in original_bridge:
            hardened=original_bridge
        else:
            raise ValueError("unknown role permission condition")
        ast.parse(hardened,filename="sbi_credit_report_auth_bridge.py")
        ast.parse(original_app,filename="production_gateway_candidate.py")
        reviewed=candidate/"sbi_credit_report_auth_bridge_strict.py"
        reviewed.write_text(hardened,encoding="utf-8")
        reviewed.chmod(0o600)
        result["private_auth_candidate"]="STRICT_ROLE_CANDIDATE_READY"
        # Assess login cookie contract via AST only; never output cookie values.
        t=ast.parse(sessions_file.read_text(encoding="utf-8"))
        constants={}
        for node in t.body:
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                for tgt in node.targets:
                    if isinstance(tgt,ast.Name) and "COOKIE" in tgt.id.upper():
                        constants[tgt.id]=node.value.value
        cookie_names=set()
        for node in ast.walk(t):
            if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                and node.func.attr in ("set_cookie","get")
                and node.args):
                expr=node.args[0]
                val=expr.value if isinstance(expr,ast.Constant) and isinstance(expr.value,str) else (
                    constants.get(expr.id) if isinstance(expr,ast.Name) else None)
                if val and len(val)<60 and re.fullmatch(r"[-_A-Za-z0-9]+",val):
                    if node.func.attr=="set_cookie" or (isinstance(node.func.value,ast.Attribute)
                       and node.func.value.attr=="cookies"):
                        cookie_names.add(val)
        if len(cookie_names)==1:
            result["cookie_name_source"]="STATIC_ONE_COOKIE_CANDIDATE"
            result["cookie_name"]=next(iter(cookie_names))
        else:
            result["cookie_name_source"]="MANUAL_CONFIRMATION_REQUIRED"
            issue("COOKIE_NAME_MAPPING_NOT_UNIQUE")
        # Isolated HTTP route security tests against a synthetic verified
        # report; no production data, no credential, and no network requests.
        spec=importlib.util.spec_from_file_location("batch18_bridge",reviewed)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        spec=importlib.util.spec_from_file_location("batch18_feature",feature_file)
        feature=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(feature)
        app=Flask(__name__)
        app.register_blueprint(feature.create_credit_note_blueprint(mod.may_view_credit_note))
        sample={"all_invoice_rows":14374,"credit_note_unique_invoices":1009,
                "credit_note_confirmed_unique_invoices":1004,
                "conflicting_duplicate_invoice_numbers":5,
                "completed_import_rows":0,
                "report_sha256":"SYNTHETIC_ONLY"}
        fake=types.ModuleType("firebase_admin")
        fake.auth=types.SimpleNamespace()
        paths=("/reports/credit-note/summary",
               "/reports/credit-note.csv",
               "/reports/credit-note/conflicts.csv",
               "/reports/credit-note/ui")
        existing=os.environ.get("SBI_CREDIT_SESSION_COOKIE_NAME")
        os.environ["SBI_CREDIT_SESSION_COOKIE_NAME"]="sbi_session"
        try:
            with patch.dict(sys.modules,{"firebase_admin":fake}):
                with patch.object(feature,"_read_snapshot",return_value=(
                    sample,b"SYNTHETIC_REPORT,DO_NOT_DEPLOY\r\n",b"SYNTHETIC_CONFLICT\r\n")):
                    client=app.test_client()
                    assert all(client.get(p).status_code==403 for p in paths), "anonymous accepted"
                    try:
                        client.set_cookie("sbi_session","synthetic-token")
                    except TypeError:
                        client.set_cookie("localhost","sbi_session","synthetic-token")
                    def refused(*a,**kw): raise ValueError("revoked")
                    fake.auth.verify_session_cookie=refused
                    assert all(client.get(p).status_code==403 for p in paths), "revoked accepted"
                    fake.auth.verify_session_cookie=lambda *a,**kw:{
                        "uid":"synthetic","admin":True,
                        "sbi_credit_report_viewer":False}
                    assert all(client.get(p).status_code==403 for p in paths), "non-report admin accepted"
                    calls=[]
                    def approved(cookie,check_revoked=False):
                        calls.append(check_revoked)
                        return {"uid":"synthetic","sbi_credit_report_viewer":True}
                    fake.auth.verify_session_cookie=approved
                    responses=[client.get(p) for p in paths]
                    assert all(r.status_code==200 for r in responses), "authorized test failed"
                    assert all("no-store" in r.headers.get("Cache-Control","")
                               for r in responses), "missing cache prevention"
                    assert calls and all(calls), "revocation checks missing"
            result["local_http_auth_tests"]="PASS_SYNTHETIC"
        finally:
            if existing is None:os.environ.pop("SBI_CREDIT_SESSION_COOKIE_NAME",None)
            else:os.environ["SBI_CREDIT_SESSION_COOKIE_NAME"]=existing
    except Exception as exc:
        issue("LOCAL_AUTH_CANDIDATE_"+type(exc).__name__)
        result["local_http_auth_tests"]="FAILED_OR_NOT_RUN"

if result["local_http_auth_tests"]!="PASS_SYNTHETIC":
    issue("AUTH_LOCAL_HTTP_GATE_PENDING")
# Genuine user sessions and Cloud Run network calls cannot be replaced by mocks.
issue("LIVE_SIGNED_IN_AND_ANONYMOUS_HTTP_REQUIRED")
issue("PRODUCTION_ROLE_ROUTE_ATTACHMENT_NOT_VERIFIED")
if result["import_completeness"]!="V140_NO_APPLIED_IMPORTS_EVIDENCE_PASS":
    result["reporting_production"]="BLOCKED_IMPORT_AND_AUTH"
else:
    result["reporting_production"]="BLOCKED_REAL_AUTH_HTTP"
out_path.parent.mkdir(parents=True,exist_ok=True)
out_path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
out_path.chmod(0o600)
print("===== BATCH 18 COMBINED CANDIDATE GATE =====")
print("IMPORT_COMPLETENESS:",result["import_completeness"])
print("PRIVATE_ROLE_CANDIDATE:",result["private_auth_candidate"])
print("COOKIE_NAME_MAPPING:",result["cookie_name_source"])
print("MOCKED_HTTP_ACCESS_TESTS:",result["local_http_auth_tests"])
print("MAIN_DASHBOARD_ATTACHED:",result["main_dashboard_routes_attached"])
print("REAL_USER_HTTP_E2E:",result["real_signed_in_http_e2e"])
print("REPORTING_RELEASE:",result["reporting_production"])
print("BLOCKER_NAMES:",",".join(result["issues"]))
print("RECEIPT:",out_path)
print("DATABASE_WRITES:NO CLOUD_DEPLOY:NO TRAFFIC_CHANGE:NO")
print("FINANCIAL_EXECUTION:RESTRICTED")
print("BATCH18_RESULT="+json.dumps({
    k:result[k] for k in ("import_completeness","private_auth_candidate","cookie_name_source",
                          "local_http_auth_tests","reporting_production","issues")},
    ensure_ascii=False,separators=(",",":")))
print("BATCH 18 COMPLETE")
PY
