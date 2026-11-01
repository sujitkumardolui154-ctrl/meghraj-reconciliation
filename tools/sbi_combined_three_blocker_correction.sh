#!/usr/bin/env bash
# SBI one-shot correction: import evidence + role-protected candidate + local auth QA.
# DOES NOT deploy or change main traffic, Firestore, IAM, or financial allocations.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
mkdir -p reports/credit_note/batch17_candidate
python3 - <<'PY'
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import ast, hashlib, json, re, sys

root=Path("dashboard_source")
out=Path("reports/credit_note/batch17_candidate")
out.mkdir(exist_ok=True,parents=True)
result={"name":"SBI_COMBINED_CORRECTION_V1",
 "checked_utc":datetime.now(timezone.utc).isoformat(),
 "import_completeness":"NOT_CERTIFIED",
 "role_protected_candidate":"BLOCKED",
 "real_authenticated_http_e2e":"PENDING",
 "source_modified":False,"deployed":False,"traffic_changed":False,
 "financial_execution":"RESTRICTED","issues":[]}
def issue(s):
    if s not in result["issues"]:result["issues"].append(s)
# Reuse the passed all-invoice report: only checksum/manifest existence, not full old QA.
manifests=sorted(Path("reports/credit_note").glob("SBI_CREDIT_NOTE_ALL_INVOICES_*.json"),
                 key=lambda p:p.stat().st_mtime)
if not manifests:
    issue("APPROVED_MANIFEST_MISSING")
else:
    path=manifests[-1];csvpath=path.with_suffix(".csv")
    try:
        doc=json.loads(path.read_text(encoding="utf-8"))
        ok=csvpath.is_file() and hashlib.sha256(csvpath.read_bytes()).hexdigest()==doc.get("report_sha256")
        result["approved_snapshot_checksum"]=bool(ok)
        result["approved_snapshot_invoice_rows"]=doc.get("all_invoice_rows")
        result["approved_snapshot_import_rows"]=doc.get("completed_import_rows")
        if not ok:issue("REPORT_CHECKSUM_MISMATCH")
    except Exception as exc:
        issue("APPROVED_REPORT_READ_"+type(exc).__name__)
# Read the entire known import receipt collection and direct import row collection.
# Only certify the currently configured v140 pipeline, and only for recognizable
# non-applied statuses. Do not silently treat an unfamiliar receipt as a non-import.
try:
    from google.cloud import firestore
    from backend_source.report_api import completed_import_rows
    db=firestore.Client(project="meghraj-reconciliation")
    def pages(collection,cap=20000):
        cursor=None
        count=0
        while True:
            q=collection.order_by("__name__").limit(100)
            if cursor is not None:q=q.start_after(cursor)
            docs=list(q.get(timeout=45))
            for d in docs:
                count+=1
                if count>cap:raise ValueError("Import ledger exceeds review cap")
                yield d
            if len(docs)<100:break
            cursor=docs[-1]
    receipts=list(pages(db.collection("dashboard_import_receipts_v140")))
    row_exists=any(db.collection("dashboard_invoice_rows_v140").limit(1).get(timeout=45))
    imported=completed_import_rows(db)
    imported_count=len(imported) if hasattr(imported,"__len__") else -1
    status_counts=Counter()
    evidence_clean=True
    non_applied={"preview","previewed","rejected","duplicate","duplicate_rejected",
                 "failed","error","cancelled","canceled","dry_run","dry-run","not_applied"}
    for snap in receipts:
        record=snap.to_dict() or {}
        raw=record.get("status") or record.get("state") or record.get("import_status") or ""
        status=str(raw).strip().lower()
        status_counts[status or "MISSING"]+=1
        # An unknown state, reported apply marker, or positive applied row count
        # is an open accounting item, not proof of zero completed imports.
        if status not in non_applied:
            evidence_clean=False
        for field in ("applied_rows","applied_count","inserted_rows","inserted_count"):
            value=record.get(field)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and value>0:
                evidence_clean=False
    result["import_evidence"]={
      "known_receipts":len(receipts),
      "receipt_status_counts":dict(status_counts),
      "direct_import_rows_exist":row_exists,
      "completed_import_rows_reader_count":imported_count,
      "full_known_v140_ledger_read":True}
    # Verify current manifest says 0 imports; cannot certify a baseline created
    # at an unknown date as current without matching source identity.
    if (evidence_clean and not row_exists and imported_count==0 and
        manifests and doc.get("completed_import_rows")==0 and
        result.get("approved_snapshot_checksum")):
        result["import_completeness"]="V140_NO_APPLIED_IMPORTS_EVIDENCE_PASS"
    else:
        issue("IMPORT_LEDGER_OR_SNAPSHOT_FRESHNESS_REVIEW")
except Exception as exc:
    result["import_evidence_error"]=type(exc).__name__
    issue("IMPORT_READ_ONLY_RECONCILIATION_FAILED")
# Role-gated candidate (not active). Requires verified Firebase session cookie
# plus explicit custom claim. The existing app login flow remains untouched.
production=root/"production_gateway.py"
feature=root/"sbi_credit_report_auth.py"
if not production.is_file() or not feature.is_file():
    issue("PRODUCTION_GATEWAY_OR_CREDIT_MODULE_MISSING")
else:
    src=production.read_text(encoding="utf-8")
    try:
        tree=ast.parse(src,filename=str(production))
        apps=[]
        install_session=False
        routes=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                if isinstance(node.func,ast.Name) and node.func.id=="install_sessions":
                    install_session=True
                if (isinstance(node.func,ast.Attribute) and
                    node.func.attr in ("get","post","route") and node.args and
                    isinstance(node.args[0],ast.Constant) and
                    isinstance(node.args[0].value,str)):
                    routes.append(node.args[0].value)
        for node in tree.body:
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call):
                if isinstance(node.value.func,ast.Name) and node.value.func.id=="Flask":
                    if any(isinstance(t,ast.Name) and t.id=="app" for t in node.targets):
                        apps.append(node.lineno)
        if len(apps)!=1 or not install_session:
            issue("PRODUCTION_APP_OR_LOGIN_INSTALL_NOT_UNIQUE")
        elif any(p.startswith("/reports/credit-note") for p in routes):
            issue("PRODUCTION_CREDIT_ROUTE_COLLISION")
        else:
            bridge=root/"sbi_credit_report_auth_bridge.py"
            if bridge.exists() and "SBI_CREDIT_FIREBASE_ROLE_BRIDGE_V1" not in bridge.read_text(encoding="utf-8"):
                issue("EXISTING_AUTH_BRIDGE_UNRECOGNIZED")
            else:
                bridge_text='''"""SBI_CREDIT_FIREBASE_ROLE_BRIDGE_V1 — explicit report viewing permission.

Only the verified Firebase Admin session-cookie identity with a server-side
custom claim authorizes report reads. Without configuration, deny all.
"""
import os
from flask import request

def may_view_credit_note():
    cookie_name=os.environ.get("SBI_CREDIT_SESSION_COOKIE_NAME","").strip()
    if not cookie_name or not cookie_name.replace("_","").isalnum():
        return False
    cookie=request.cookies.get(cookie_name)
    if not cookie:
        return False
    try:
        from firebase_admin import auth
        claims=auth.verify_session_cookie(cookie,check_revoked=True)
    except Exception:
        return False
    if not isinstance(claims,dict) or not claims.get("uid"):
        return False
    return claims.get("sbi_credit_report_viewer") is True or claims.get("admin") is True
'''
                candidate=src.rstrip()+'''


# SBI_CREDIT_AUTH_ONLY_ZERO_TRAFFIC_CANDIDATE_V1
from sbi_credit_report_auth_bridge import may_view_credit_note
from sbi_credit_report_auth import create_credit_note_blueprint
app.register_blueprint(create_credit_note_blueprint(may_view_credit_note))
'''
                ast.parse(candidate,filename="production_gateway_candidate.py")
                # Do not touch dashboard_source or its active production service.
                (out/"sbi_credit_report_auth_bridge.py").write_text(bridge_text,encoding="utf-8")
                (out/"production_gateway_candidate.py").write_text(candidate,encoding="utf-8")
                (out/"production_gateway_candidate.py").chmod(0o600)
                (out/"sbi_credit_report_auth_bridge.py").chmod(0o600)
                result["role_protected_candidate"]="WRITTEN_PRIVATE_CANDIDATE_ONLY"
                result["auth_config"]="SBI_CREDIT_SESSION_COOKIE_NAME required; Firebase admin or sbi_credit_report_viewer custom claim required"
    except Exception as exc:
        issue("PRODUCTION_CANDIDATE_"+type(exc).__name__)
outpath=Path("reports/consolidated_reporting_correction.json")
outpath.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
outpath.chmod(0o600)
print("REPORT_IMPORT_EVIDENCE:",result["import_completeness"])
print("ROLE_GUARDED_ROUTE_CANDIDATE:",result["role_protected_candidate"])
print("LIVE_SIGNED_IN_USER_HTTP_TEST:",result["real_authenticated_http_e2e"])
print("CORRECTION_BLOCKERS:",", ".join(result["issues"]) or "None for candidate generation")
print("CANDIDATE REPORT:",outpath)
PY

# Runtime independence tests: deny no session, deny invalid/revoked cookie,
# reject non-role bearer, and allow only explicitly role-granted verified cookie.
python3 - <<'PY'
from pathlib import Path
from unittest.mock import patch
import importlib.util, os, sys, types
from flask import Flask

candidate=Path("reports/credit_note/batch17_candidate/sbi_credit_report_auth_bridge.py")
if not candidate.is_file():
    print("ROLE-GATE SYNTHETIC QA: NOT RUN, candidate unavailable")
else:
    spec=importlib.util.spec_from_file_location("sbi_auth_candidate",candidate)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    app=Flask(__name__)
    os.environ["SBI_CREDIT_SESSION_COOKIE_NAME"]="sbi_session"
    firebase=types.ModuleType("firebase_admin")
    firebase.auth=types.SimpleNamespace(verify_session_cookie=lambda *a,**kw: None)
    with patch.dict(sys.modules,{"firebase_admin":firebase}):
        with app.test_request_context("/"):
            assert mod.may_view_credit_note() is False
        with app.test_request_context("/",headers={"Cookie":"sbi_session=bogus"}):
            assert mod.may_view_credit_note() is False
        firebase.auth.verify_session_cookie=lambda c,check_revoked=False: {"uid":"synthetic-id","admin":False,"sbi_credit_report_viewer":False}
        with app.test_request_context("/",headers={"Cookie":"sbi_session=bogus"}):
            assert mod.may_view_credit_note() is False
        firebase.auth.verify_session_cookie=lambda c,check_revoked=False: {"uid":"synthetic-id","sbi_credit_report_viewer":True} if check_revoked else None
        with app.test_request_context("/",headers={"Cookie":"sbi_session=bogus"}):
            assert mod.may_view_credit_note() is True
    print("ROLE-GATE SYNTHETIC QA: PASS (anonymous / invalid / no-role denied; explicit role approved)")
PY

echo "===== COMBINED CORRECTION RESULT ====="
echo "MAIN DASHBOARD SOURCE: UNCHANGED"
echo "CLOUD RUN TRAFFIC: UNCHANGED"
echo "SIGNED-IN HTTP E2E: REQUIRES ZERO-TRAFFIC LIVE CANDIDATE"
echo "FINANCIAL EXECUTION: RESTRICTED"
echo "COMBINED CORRECTION PREPARATION COMPLETE"
