#!/usr/bin/env python3
"""Stage 6D.4 identity readiness contract audit — offline, non-mutating.

Audits the pinned source, not the deployed Lightsail runtime or Google IAM.
No import of app modules, cloud SDK, network access, UID, credentials or user data.
"""
import argparse
import json
from pathlib import Path

REQUIRED = {
    "dashboard_source/dashboard_sessions.py": {
        "revocation_checked_session": "verify_session_cookie(",
        "explicit_revocation_flag": "check_revoked=True",
        "live_user_status_and_claims": "auth.get_user(",
        "session_cookie_mint": "auth.create_session_cookie(",
        "logout_revoke": "auth.revoke_refresh_tokens(",
        "host_only_http_only_cookies": "httponly=True",
        "csrf_origin_binding": "is_allowed_origin(request.headers.get(\"Origin\"))",
    },
    "dashboard_source/dashboard_login_pages.py": {
        "firebase_web_config_control": 'FIREBASE_WEB_API_KEY',
        "firebase_login_csp": "https://identitytoolkit.googleapis.com",
    },
    "dashboard_source/dashboard_users.py": {
        "privileged_account_create": "auth.create_user(",
        "privileged_claim_updates": "auth.set_custom_user_claims(",
    },
    "dashboard_source/cloud_auth.py": {
        "cloud_run_id_token_requirement": "id_token.fetch_id_token(",
    },
    "dashboard_source/stage6_aws_guard.py": {
        "backend_routes_fail_closed": "Stage 6 AWS backend integration disabled",
    },
    "dashboard_source/stage6d_private_entry.py": {
        "private_profile_startup": "SBI_STAGE6_PRIVATE_ONLY",
        "finance_disabled": "SBI_STAGE6_FINANCIAL_EXECUTION",
    },
}

def inspect(root):
    root = Path(root).resolve()
    findings = {}
    for relative, markers in REQUIRED.items():
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise ValueError("Missing required source: " + relative)
        contents = candidate.read_text(encoding="utf-8")
        findings.update({label: marker in contents for label, marker in markers.items()})
    source_contract = all(findings.values())
    return {
        "stage": "6D.4",
        "source_contract": "PASS" if source_contract else "FAIL",
        "findings": findings,
        "lightsail_approved_host": True,
        "firebase_web_key_available_on_host": "NOT_VERIFIED",
        "firebase_admin_keyless_runtime_identity": "BLOCKED_NOT_ESTABLISHED",
        "firebase_real_login": "NOT_TESTED",
        "firebase_revocation_live": "NOT_TESTED",
        "firebase_admin_user_read": "NOT_TESTED",
        "finance_database": "NOT_CONNECTED",
        "aws_wif_app_owned_role": "NOT_VERIFIED",
        "google_wif_provider": "USER_REPORTED_DISABLED",
        "new_ec2_server": "NOT_AUTHORIZED",
        "identity_design_decision": "BLOCKED_AWAITING_SECURE_LIGHTSAIL_COMPATIBLE_IDENTITY",
        "production_deployment": "BLOCKED",
        "financial_writes": 0,
        "batch_qa": "PASS" if source_contract else "FAIL",
        "next_gate": "REVIEW_RUNTIME_IDENTITY_OPTIONS_WITHOUT_GOOGLE_IAM_CHANGES" if source_contract else "FIX_SOURCE_SECURITY_CONTRACT",
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",required=True)
    args=parser.parse_args()
    try:
        result=inspect(args.repo)
    except (ValueError, OSError, UnicodeError):
        print("SOURCE_CONTRACT=BLOCKED")
        print("BATCH_QA=BLOCKED")
        print("NEXT_GATE=VERIFY_PINNED_REPOSITORY_FILES")
        return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["batch_qa"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
