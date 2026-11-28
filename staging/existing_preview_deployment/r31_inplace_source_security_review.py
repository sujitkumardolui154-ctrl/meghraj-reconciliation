#!/usr/bin/env python3
"""R31 same-Lightsail in-place RLS integration SOURCE REVIEW ONLY.

No HTTP, Docker, Firebase, PostgreSQL, cloud calls, files written, deployments,
approval grants, credential reads, or financial operations.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
STAGE=ROOT/"staging/aws_login_v150"
EXISTING="https://sbi-preview.13-232-241-221.sslip.io/login"
FILES={
    "app":STAGE/"app.py",
    "sessions":ROOT/"dashboard_source/dashboard_sessions.py",
    "stage":STAGE/"r31_stage_blueprint.py",
    "route":STAGE/"r31_11_4_runtime_rls_blueprint.py",
    "adapter":STAGE/"r31_11_4_runtime_rls_adapter.py",
    "caddy":STAGE/"Caddyfile.workspace",
    "baseline_image":STAGE/"Dockerfile.r31_private_staging",
    "candidate_image":STAGE/"Dockerfile.r31_11_4_private_candidate",
}

class ReviewBlocked(Exception): pass

def load_sources(root=ROOT):
    # local source only. No environment variables or secret files read.
    return {key:(root/path.relative_to(ROOT)).read_text(encoding="utf-8")
            for key,path in FILES.items()}

def source_checks(s,policy):
    checks={}
    checks["TARGET_EXACT"]=(policy.get("user_required_url")==EXISTING and
        policy.get("existing_url_must_remain_canonical") is True and
        policy.get("new_application_platform_allowed") is False)
    checks["RELEASE_LOCKS"]=(policy.get("financial_apply")=="LOCKED" and
        policy.get("production_release")=="BLOCKED" and
        policy.get("actual_deployment_performed") is False)
    checks["EXISTING_LOGIN_AUTH_CHAIN"]=(
        'SITE_ORIGIN = "https://sbi-preview.13-232-241-221.sslip.io"' in s["app"]
        and "install_sessions(app)" in s["app"]
        and "auth.verify_session_cookie(" in s["sessions"]
        and "check_revoked=True" in s["sessions"]
        and "g.dil_user = user" in s["sessions"]
        and s["app"].index("install_sessions(app)") <
            s["app"].index("app.register_blueprint(runtime_r3114)"))
    checks["RLS_FEATURE_NOT_ENABLED_BY_DEFAULT"]=(
        'os.environ.get("SBI_R31_PRIVATE_STAGING_ENABLED")' in s["app"]
        and 'os.environ.get("SBI_R31_11_4_RUNTIME_ENABLED")' in s["app"]
        and 'app.register_blueprint(runtime_r3114)' in s["app"])
    checks["BROAD_FLAG_ALSO_REGISTERS_WRITE_QA_ROUTE"]=(
        "app.register_blueprint(stage_r31)" in s["app"]
        and '@stage_r31.post(PREFIX+"/receipts/<receipt_id>/sync")' in s["stage"]
        and "persist_qa_source(" in s["stage"])
    checks["RLS_ENDPOINT_READ_ONLY_BY_SOURCE"]=(
        '@runtime_tenant_rls.get("/api/r31-private-qa/tenant-rls-source-r3114")' in s["route"]
        and "read_tenant_source_only(user" in s["route"]
        and "getattr(g, \"dil_user\", None)" in s["route"]
        and 'financial_execution_enabled=False' in s["route"]
        and 'production_financial_writes=False' in s["route"])
    checks["QA_POSTGRES_FIXED_READ_ONLY"]=(
        'QA_DB = "sbi_r31_11_4_auth_qa_20261126"' in s["adapter"]
        and 'QA_HOST = "sbi-r3114-private-postgres"' in s["adapter"]
        and "SET TRANSACTION READ ONLY" in s["adapter"]
        and "default_transaction_read_only=on" in s["adapter"]
        and "row_security_active(" in s["adapter"]
        and "session_user" in s["adapter"]
        and "sbi_reconciliation_main" not in s["adapter"])
    checks["BASELINE_IMAGE_OMITS_R3114"]=(
        "r31_11_4_runtime_rls_adapter.py" not in s["baseline_image"]
        and "r31_11_4_runtime_rls_blueprint.py" not in s["baseline_image"]
        and "USER 10001:10001" in s["baseline_image"])
    checks["PRIVATE_CANDIDATE_CONTAINS_R3114"]=(
        "r31_11_4_runtime_rls_adapter.py /app/" in s["candidate_image"]
        and "r31_11_4_runtime_rls_blueprint.py /app/" in s["candidate_image"]
        and "USER 10001:10001" in s["candidate_image"])
    checks["CADDY_SOURCE_EXISTING_API_PROXY"]=(
        "/api/*" in s["caddy"]
        and "reverse_proxy sbi-login-workspace:8080" in s["caddy"])
    checks["FINANCIAL_CATCHALL_DENY_IN_SOURCE"]=(
        "@app.route(\"/api/<path:route>\"" in s["app"]
        and "def disabled_financial_api(route):" in s["app"]
        and "financial_execution_enabled=False" in s["app"])
    return checks

def validate_worktree(sha):
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        raise ReviewBlocked("SOURCE_SHA_INVALID")
    try:
        p=subprocess.run(["git","-C",str(ROOT),"rev-parse","HEAD"],
            check=False,text=True,capture_output=True,timeout=10)
        q=subprocess.run(["git","-C",str(ROOT),"status","--porcelain"],
            check=False,text=True,capture_output=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired):
        raise ReviewBlocked("GIT_CHECK_UNAVAILABLE") from None
    if p.returncode or q.returncode or p.stdout.strip()!=sha or q.stdout.strip():
        raise ReviewBlocked("GIT_SOURCE_UNPINNED_OR_DIRTY")

def main(sha):
    print("=== R31 SAME-URL RLS SOURCE SECURITY REVIEW ===",flush=True)
    validate_worktree(sha)
    policy=json.loads(
        (ROOT/"staging/existing_preview_deployment/existing_preview_target_policy.json")
        .read_text("utf-8"))
    checks=source_checks(load_sources(),policy)
    for key,ok in checks.items():
        print("R31_INPLACE_"+key+"="+
              ("PASS_SOURCE_OBSERVED" if ok else "REVIEW_REQUIRED"),flush=True)
    if not all(checks.values()):
        raise ReviewBlocked("SOURCE_CONTRACT_CHANGED")
    print("R31_INPLACE_BROAD_QA_FLAG=RISK_WRITABLE_QA_SYNC_IF_ENABLED",flush=True)
    print("R31_INPLACE_REQUIRED_CHANGE=ISOLATED_SINGLE_ROUTE_GUARD_REVIEW_ONLY",flush=True)
    print("R31_INPLACE_SOURCE_REVIEW=PASS_SCOPE_RISKS_IDENTIFIED_NOT_IMPLEMENTED",flush=True)
    print("R31_INPLACE_REAL_EXISTING_HTTPS_RLS=NOT_TESTED",flush=True)
    print("R31_INPLACE_DEPLOYMENT=NOT_PERFORMED",flush=True)
    return 0

if __name__=="__main__":
    args=argparse.ArgumentParser()
    args.add_argument("--source-sha",required=True)
    opt=args.parse_args()
    try:
        code=main(opt.source_sha)
    except ReviewBlocked as e:
        label=str(e) if re.fullmatch(r"[A-Z0-9_]{3,80}",str(e)) else "SOURCE_REVIEW_BLOCKED"
        print("STOP=R31_INPLACE_"+label,flush=True)
        code=2
    except (OSError,TypeError,ValueError,UnicodeError,KeyError):
        print("STOP=R31_INPLACE_SOURCE_READ_OR_FORMAT_FAILED",flush=True)
        code=2
    finally:
        print("R31_INPLACE_FINANCIAL_APPLY=LOCKED",flush=True)
        print("R31_INPLACE_PRODUCTION_RELEASE=BLOCKED",flush=True)
    raise SystemExit(code)
