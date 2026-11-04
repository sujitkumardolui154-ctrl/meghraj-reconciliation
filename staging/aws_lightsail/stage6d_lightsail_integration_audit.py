#!/usr/bin/env python3
"""Stage 6D — Lightsail full-app integration dependency audit (offline, no writes).

Identifies Firebase browser vs Admin and Cloud Run dependencies using source
markers. Never reads credential files, makes network requests or deploys.
"""
import argparse
import json
from pathlib import Path

SOURCE_FILES = {
    "gateway": "dashboard_source/production_gateway.py",
    "sessions": "dashboard_source/dashboard_sessions.py",
    "login": "dashboard_source/login.js",
    "login_pages": "dashboard_source/dashboard_login_pages.py",
    "cloud_auth": "dashboard_source/cloud_auth.py",
    "aws_guard": "dashboard_source/stage6_aws_guard.py",
    "docker": "staging/aws_lightsail/Dockerfile.stage6b",
    "credit_note": "dashboard_source/sbi_credit_report_auth.py",
    "user_admin": "dashboard_source/dashboard_users.py",
}

MARKERS = {
    "browser_firebase_password_signin": ("login", "identitytoolkit.googleapis.com"),
    "firebase_web_config_endpoint": ("login_pages", "FIREBASE_WEB_API_KEY"),
    "firebase_admin_revoked_session_verify": ("sessions", "verify_session_cookie"),
    "firebase_admin_user_lookup": ("sessions", "auth.get_user("),
    "firebase_admin_create_session": ("sessions", "auth.create_session_cookie("),
    "firebase_admin_revocation": ("sessions", "auth.revoke_refresh_tokens("),
    "admin_can_create_users": ("user_admin", "auth.create_user("),
    "cloud_run_backend_token": ("cloud_auth", "id_token.fetch_id_token("),
    "cloud_run_monitoring_gateway": ("gateway", "fetch_monitoring"),
    "cloud_run_report_gateway": ("gateway", "forward_database_report"),
    "credit_note_gcs": ("credit_note", "storage.Client("),
    "aws_backend_fail_closed": ("aws_guard", "Stage 6 AWS backend integration disabled"),
    "package_only_image": ("docker", "--block-startup"),
}

def audit(root):
    root = Path(root).resolve()
    content = {}
    for key, rel in SOURCE_FILES.items():
        p=(root / rel).resolve()
        if not p.is_relative_to(root) or not p.is_file():
            raise ValueError("Required source file missing: "+rel)
        content[key]=p.read_text(encoding="utf-8")
    findings={key:(marker in content[file]) for key,(file,marker) in MARKERS.items()}
    return {
        "stage": "6D",
        "audit": "LIGHTSAIL_FULL_APPLICATION_INTEGRATION_READ_ONLY",
        "source_markers": findings,
        "identity_design": {
            "browser_firebase_signin": "POTENTIALLY_LIGHTSAIL_COMPATIBLE_REQUIRES_HTTPS_DOMAIN",
            "firebase_admin_session_and_user_checks": "BLOCKED_REQUIRES_TRUSTED_GOOGLE_CREDENTIAL",
            "google_cloud_run_backend": "BLOCKED_REQUIRES_AUDITED_TOKEN_EXCHANGE",
            "lightsail_sts_service_role": "UNTRUSTED_FOR_WIF_ACCOUNT_MISMATCH",
            "new_ec2_role": "NOT_ATTACHED_TO_LIGHTSAIL",
            "wif_pool_and_provider": "USER_REPORTED_DISABLED",
        },
        "recommendation": "LIGHTSAIL_FIRST_FEASIBILITY_NO_EC2_PURCHASE",
        "cloud_run_live_revision": "NOT_VERIFIED",
        "aws_authenticated_login": "NOT_VERIFIED",
        "financial_access": "DISABLED",
        "production_changes": 0,
        "release": "BLOCKED_PENDING_IDENTITY_AND_PRIVATE_APP_PARITY",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    args=p.parse_args()
    try:
        print(json.dumps(audit(args.repo),indent=2,sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print("STAGE6D_AUDIT=BLOCKED_"+type(exc).__name__)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
