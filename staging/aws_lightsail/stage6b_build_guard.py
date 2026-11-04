#!/usr/bin/env python3
"""Package-only validation; runtime intentionally disabled until Stage 6C."""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
REQUIRED = (
    "production_gateway.py", "index.html", "dashboard_sessions.py",
    "dashboard_login_pages.py", "dashboard_users.py",
    "dashboard_account_pages.py", "cloud_auth.py",
    "sbi_report_access.py", "sbi_credit_report_auth.py",
    "dil_floating_assistant.js", "dashboard.js", "login.html",
)

def verify(root=ROOT):
    missing = [p for p in REQUIRED if not (root / p).is_file()]
    if missing:
        raise ValueError("Required dashboard files absent: " + ", ".join(missing))
    data = (root/"production_gateway.py").read_text()
    for marker in ("install_sessions(app)", "install_user_management(app)",
                   "database_import_gateway", "reconciliation_change_gateway",
                   "create_credit_note_blueprint"):
        if marker not in data:
            raise ValueError("Full dashboard gateway missing source contract: " + marker)
    return True

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate-source", action="store_true")
    group.add_argument("--block-startup", action="store_true")
    args = parser.parse_args()
    if args.block_startup:
        print("STAGE6B_STARTUP=BLOCKED_PENDING_AUTH_IDENTITY_AND_BACKEND_PARITY", file=sys.stderr)
        return 78
    try:
        verify()
    except (ValueError, OSError) as exc:
        print("STAGE6B_SOURCE=BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print("STAGE6B_SOURCE=PACKAGE_COMPLETE_NOT_DEPLOYABLE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
