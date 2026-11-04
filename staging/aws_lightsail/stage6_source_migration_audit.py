#!/usr/bin/env python3
"""Stage 6 source migration dependency audit. Read-only; fail closed for cutover.

Scans pinned local source. Does not read env values, connect to cloud services,
retrieve financial data, build containers, deploy or mutate any infrastructure.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

FILES = {
    "dashboard_gateway": "dashboard_source/production_gateway.py",
    "dashboard_html": "dashboard_source/index.html",
    "firebase_sessions": "dashboard_source/dashboard_sessions.py",
    "cloud_identity": "dashboard_source/cloud_auth.py",
    "login_pages": "dashboard_source/dashboard_login_pages.py",
    "dashboard_requirements": "dashboard_source/requirements.txt",
    "preview_app": "staging/railway_public/app.py",
    "preview_compose": "staging/aws_lightsail/compose.yaml",
    "report_backend": "backend_source/report_api.py",
}
FEATURE_MARKERS = {
    "reconciliation_dashboard_ui": ("dashboard_html", "Reconciliation"),
    "authenticated_firebase_sessions": ("firebase_sessions", "verify_session_cookie"),
    "login_and_csrf": ("firebase_sessions", "csrf_valid"),
    "account_admin": ("dashboard_gateway", "install_user_management(app)"),
    "report_index": ("dashboard_gateway", '@app.get("/api/reports")'),
    "reconciliation_changes": ("dashboard_gateway", "reconciliation_change_gateway"),
    "import_preview_and_review": ("dashboard_gateway", "database_import_gateway"),
    "credit_note": ("dashboard_gateway", "create_credit_note_blueprint"),
    "assistant_ui_only": ("dashboard_gateway", "dil_floating_assistant.js"),
    "monitoring": ("dashboard_gateway", "fetch_monitoring"),
}
BLOCKERS = {
    "cloud_run_identity_tokens": ("cloud_identity", "fetch_id_token"),
    "hardcoded_cloud_run_backend": ("dashboard_gateway", "sbi-supervisor-backend"),
    "fixed_gcloud_browser_origins": ("firebase_sessions", "login-v150---sbi-dashboard"),
    "firebase_admin_credentials_on_aws": ("firebase_sessions", "firebase_admin.initialize_app"),
    "firestore_tied_to_gcloud": ("report_backend", "firestore.Client"),
    "aws_preview_not_full_gateway": ("preview_compose", "../railway_public"),
    "financial_api_explicitly_disabled_in_preview": ("preview_app", "Financial API disabled in public preview"),
}

def audit(root: Path) -> dict:
    root=root.resolve()
    contents={}
    for key, rel in FILES.items():
        file=(root/rel).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            raise ValueError("required source file missing: " + rel)
        contents[key]=file.read_text(encoding="utf-8")
    features={name:marker in contents[file] for name,(file,marker) in FEATURE_MARKERS.items()}
    blockers={name:marker in contents[file] for name,(file,marker) in BLOCKERS.items()}
    # This is source analysis, never proof of a live deployed version or parity.
    return {
       "stage":"6","mode":"READ_ONLY_SOURCE_DEPENDENCY_AUDIT",
       "source_reference":"repository working tree, NOT verified Cloud Run deployment",
       "feature_source_markers":features,
       "migration_dependencies_detected":blockers,
       "full_application_on_aws":"NOT_VERIFIED",
       "firebase_session_auth_on_aws":"NOT_VERIFIED",
       "aws_to_gcp_service_identity":"NOT_CONFIGURED_OR_VERIFIED",
       "finance_database_copy_or_connect":"NOT_PERFORMED",
       "production_change":False,"financial_writes":0,
       "stage6_release_gate":"BLOCKED_UNTIL_PRIVATE_PARITY_AUTH_AND_DATA_GATES",
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    args=p.parse_args()
    try:
        print(json.dumps(audit(Path(args.repo)),indent=2,sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError) as exc:
        print("STAGE6_AUDIT_BLOCKED="+type(exc).__name__+": "+str(exc))
        return 2
if __name__=="__main__":
    raise SystemExit(main())
