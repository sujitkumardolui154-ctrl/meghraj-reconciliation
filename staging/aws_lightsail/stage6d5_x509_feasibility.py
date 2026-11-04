#!/usr/bin/env python3
"""Stage 6D.5: offline X.509 Google WIF library compatibility preflight.

Runs inside the previously built Docker image through stdin (no rebuild).
Never reads certificate, key, ADC or AWS metadata; does not connect to Google.
Checks minimum library version only; not a credential setup or login test.
"""
from importlib import metadata
import json
import re
from pathlib import Path

MIN_GOOGLE_AUTH = (2, 39, 0)
REQUIRED_SOURCES = {
    "/app/dashboard_sessions.py": (
        "verify_session_cookie(", "check_revoked=True",
        "auth.get_user(", "auth.revoke_refresh_tokens(",
        "auth.create_session_cookie(",
    ),
    "/app/stage6_aws_guard.py": ("Stage 6 AWS backend integration disabled",),
    "/app/stage6d_private_entry.py": ("SBI_STAGE6_PRIVATE_ONLY", "SBI_STAGE6_FINANCIAL_EXECUTION"),
}

def parse_version(version):
    m = re.match(r"^(\\d+)\\.(\\d+)\\.(\\d+)(?:[+.-].*)?$", version)
    return tuple(int(group) for group in m.groups()) if m else None

def inspect(version_lookup=metadata.version, read_text=None):
    read_text = read_text or (lambda path: Path(path).read_text(encoding="utf-8"))
    installed = {}
    for name in ("google-auth", "firebase-admin"):
        try:
            installed[name] = version_lookup(name)
        except metadata.PackageNotFoundError:
            installed[name] = None
    library_version = parse_version(installed["google-auth"] or "")
    x509_support_version = bool(library_version and library_version >= MIN_GOOGLE_AUTH)
    files_present = True
    security_contract = True
    for file, markers in REQUIRED_SOURCES.items():
        try:
            code = read_text(file)
        except (OSError, UnicodeError):
            files_present = False
            security_contract = False
            continue
        if not all(marker in code for marker in markers):
            security_contract = False
    ready = bool(installed["firebase-admin"] and x509_support_version and security_contract)
    return {
        "stage": "6D.5",
        "audit": "X509_WIF_LIBRARY_COMPATIBILITY_OFFLINE_ONLY",
        "google_auth_version": installed["google-auth"] or "NOT_INSTALLED",
        "firebase_admin_version": installed["firebase-admin"] or "NOT_INSTALLED",
        "google_auth_minimum_for_x509": "2.39.0",
        "x509_version_requirement": "PASS" if x509_support_version else "BLOCKED",
        "source_files_available": "PASS" if files_present else "BLOCKED",
        "revocation_and_financial_guard_contract": "PASS" if security_contract else "BLOCKED",
        "existing_lightsail_only": True,
        "certificate_and_private_key": "NOT_CREATED_OR_READ",
        "x509_wif_provider": "NOT_CONFIGURED",
        "google_iam_change": "NOT_PERFORMED",
        "firebase_real_login": "NOT_TESTED",
        "financial_database": "NOT_CONNECTED",
        "production_deployment": "BLOCKED",
        "batch_qa": "PASS" if ready else "BLOCKED",
        "next_gate": (
            "INDEPENDENT_X509_WIF_SECURITY_COST_AND_ROTATION_REVIEW"
            if ready else "REVIEW_GOOGLE_AUTH_DEPENDENCY_AND_EXISTING_IMAGE"
        ),
    }

def main():
    report = inspect()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["batch_qa"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
