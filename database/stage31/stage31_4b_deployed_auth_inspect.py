#!/usr/bin/env python3
"""Stage31.4B: source-only audit against ACTUAL RUNNING PR129 container.

This script reads only application Python *source metadata*. It does not
import the app, Firebase, cloud credentials, environment, request cookies,
financial records, or secrets. Output contains boolean evidence and digests.
"""
from __future__ import annotations
import ast
import hashlib
from pathlib import Path

ROOT = Path("/app")
FILES = {
    "app": "app.py",
    "session": "dashboard_sessions.py",
    "report_access": "sbi_report_access.py",
    "postgres_report": "pg_reporting_blueprint.py",
    "stage31_private": "stage31_4_private_preview.py",
}
EXPECTED_SITE = "https://pr129.13-232-241-221.sslip.io"

def q(name: str, value) -> None:
    print(f"STAGE31_4B_{name}={value}")

def ast_file(filename: str):
    path = ROOT / filename
    if not path.is_file():
        return None, None
    contents = path.read_bytes()
    return ast.parse(contents, filename=filename), hashlib.sha256(contents).hexdigest()

def fullname(n):
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        s=fullname(n.value)
        return s + "." + n.attr if s else n.attr
    return ""

def function_calls(tree, name):
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == name]
    calls = set()
    if funcs:
        for node in ast.walk(funcs[0]):
            if isinstance(node, ast.Call):
                calls.add(fullname(node.func))
    return calls

def string_values(tree, symbol):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == symbol for t in n.targets
        ):
            try:
                val=ast.literal_eval(n.value)
                if isinstance(val,(set, tuple, list)):
                    return {str(x) for x in val if isinstance(x,str)}
            except (ValueError,TypeError,MemoryError,RecursionError):
                return None
    return None

def function_names(tree):
    return {n.name for n in ast.walk(tree)
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

def text_constants(tree):
    return {n.value for n in ast.walk(tree)
            if isinstance(n,ast.Constant) and isinstance(n.value,str)}

def run():
    q("AUDIT_MODE", "DEPLOYED_SOURCE_AST_ONLY_NO_SECRETS")
    trees={}
    for key, filename in FILES.items():
        tree,digest=ast_file(filename)
        if tree is None:
            q("DEPLOYED_FILE_"+key.upper(),"ABSENT")
        else:
            trees[key]=tree
            q("DEPLOYED_FILE_"+key.upper(),"PRESENT")
            q("DEPLOYED_SHA256_"+key.upper(),digest)

    if not all(k in trees for k in ("app","session","postgres_report")):
        q("SOURCE_AUTH_REVIEW", "BLOCKED_REQUIRED_FILES_MISSING")
        return 21
    app,session=trees["app"],trees["session"]
    session_methods=function_names(session)
    expected={"install_sessions","csrf_valid","is_master"}
    q("FIREBASE_SESSION_HELPERS_PRESENT",all(x in session_methods for x in expected))

    app_calls={fullname(n.func) for n in ast.walk(app) if isinstance(n,ast.Call)}
    q("GLOBAL_SESSION_INSTALL_CALLED",any(x.endswith("install_sessions") for x in app_calls))
    csrf_calls=function_calls(session,"csrf_valid")
    q("CSRF_ORIGIN_AND_CONSTANT_TIME_COMPARISON_PRESENT",
      {"secrets.compare_digest","request.headers.get","request.cookies.get"}.issubset(csrf_calls))
    protector=function_calls(session,"protect_dashboard")
    q("FIREBASE_SESSION_COOKIE_VERIFICATION_PRESENT",
      any(s.endswith("verify_session_cookie") for s in protector))
    q("FIREBASE_USER_LOOKUP_PRESENT",
      any(s.endswith("get_user") for s in protector))
    q("FIREBASE_SESSION_REVOCATION_CHECK_PRESENT",
      "check_revoked" in {x.arg for n in ast.walk(session)
                          if isinstance(n,ast.Call) for x in n.keywords})
    q("ACTUAL_GLOBAL_BEFORE_REQUEST_DECORATOR_PRESENT",
      any(isinstance(n,ast.FunctionDef) and n.name=="protect_dashboard"
          and any(fullname(d)=="app.before_request" for d in n.decorator_list)
          for n in ast.walk(session)))

    known_origins=string_values(session,"ORIGINS")
    if known_origins is None:
        q("LIVE_ORIGIN_POLICY", "DYNAMIC_OR_UNKNOWN_REVIEW_REQUIRED")
    elif EXPECTED_SITE in known_origins:
        q("LIVE_ORIGIN_POLICY", "PRODUCTION_ORIGIN_PRESENT_IN_STATIC_ALLOWLIST")
    else:
        q("LIVE_ORIGIN_POLICY", "PRODUCTION_ORIGIN_NOT_IN_STATIC_ALLOWLIST_REVIEW_REQUIRED")
    q("PRODUCTION_ORIGIN_MATCH_CHECK","COMPLETE_NO_ORIGIN_LIST_PRINTED")

    access=trees.get("report_access")
    if access is None:
        q("REPORT_ACCESS_SOURCE","REVIEW_REQUIRED_MISSING_SOURCE_FILE")
    else:
        q("EXPLICIT_REPORT_ACCESS_HELPER_PRESENT",
          "can_view_report" in function_names(access))
        q("REPORT_CLAIM_CHECK_FOUND",
          "sbi_report_viewer" in text_constants(access))
    report=trees["postgres_report"]
    q("POSTGRES_READONLY_AUTH_GUARD_PRESENT",
      "require_verified_authorization" in function_names(report))
    q("STAGE31_PRIVATE_PREVIEW_REGISTERED_IN_APP_FILE",
      "stage31_4_private_preview" in text_constants(app)
      or "create_private_preview_blueprint" in app_calls
      or "create_private_preview_blueprint" in {
        fullname(n.func) for n in ast.walk(app) if isinstance(n,ast.Call)})
    q("STAGE31_PRIVATE_DEPLOYED_SOURCE_PRESENT",
      "stage31_private" in trees)
    q("STAGE31_PRIVATE_REAL_AUTH_CALLBACK",
      "NOT_WIRED_NOT_PROVEN")
    q("STAGE31_PRIVATE_DEDICATED_INGEST_AUTH_CLAIM",
      "REQUIRES_DESIGN_AND_REVIEW")
    q("STAGE31_AUTHENTICATED_BROWSER_POST_CSRF",
      "NOT_TESTED_BY_SOURCE_INSPECTION")
    q("STAGE31_4B_SOURCE_INSPECTION",
      "COMPLETE_REVIEW_REQUIRED_BEFORE_PRIVATE_DEPLOYMENT")
    return 0

if __name__=="__main__":
    raise SystemExit(run())
