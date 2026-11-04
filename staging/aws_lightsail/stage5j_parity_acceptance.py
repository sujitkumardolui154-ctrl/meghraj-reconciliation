#!/usr/bin/env python3
"""Stage 5J: source contract parity + restricted unauthenticated endpoint audit.

No credentials read, no mutations, no financial calls and no production promotion.
Source comparison uses the pinned local checkout, NOT proof of deployed Cloud Run.
"""
import argparse
import json
import pathlib
import re
import urllib.error
import urllib.request

# Explicitly source-derived features; evidence requires checking exact markers.
CONTRACTS = {
    "monitoring": ("/api/health", "/api/pipeline/status"),
    "reports": ("/api/reports", "/api/reports"),
    "reconciliation_changes": ("/api/reports/reconciliation-changes", "/api/reports/reconciliation-changes"),
    "import_preview": ("/api/imports/", "/api/imports/"),
    "credit_note": ("credit-note", "credit-note"),
    "account_session": ("dashboard_sessions", "dashboard_sessions"),
    "floating_assistant_ui": ("dil_floating_assistant.js", "dil_floating_assistant.js"),
}
REFERENCE = "dashboard_source"
PREVIEW = "staging/railway_public"
REF_FILES = ("production_gateway.py", "index.html", "dashboard_sessions.py", "dil_floating_assistant.js")
PREVIEW_FILES = ("app.py", "pipeline.html")
BASE = "https://sbi-preview.13-232-241-221.sslip.io"

def source_scan(root):
    root = pathlib.Path(root).resolve()
    refs = [root / REFERENCE / x for x in REF_FILES]
    previews = [root / PREVIEW / x for x in PREVIEW_FILES]
    if not all(p.is_file() for p in refs + previews):
        raise ValueError("required pinned source files unavailable")
    reference = "\n".join(p.read_text(encoding="utf-8") for p in refs)
    preview = "\n".join(p.read_text(encoding="utf-8") for p in previews)
    result = {}
    for feature, (ref_marker, preview_marker) in CONTRACTS.items():
        result[feature] = {
            "cloud_run_source_declares": ref_marker in reference,
            "aws_preview_source_declares": preview_marker in preview,
            "deployment_verified": False,
        }
    return result

def get_status(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "SBI-Stage5J-readonly"})
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError):
        return "UNAVAILABLE"

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",required=True)
    args=parser.parse_args()
    try:
        features=source_scan(args.repo)
        unauth={
            "/": get_status(BASE+"/"),
            "/api/pipeline/status": get_status(BASE+"/api/pipeline/status"),
            "/api/reports": get_status(BASE+"/api/reports"),
            "/api/upload": get_status(BASE+"/api/upload"),
        }
        gate = unauth["/"] in (401,403) and all(
            unauth[x] in (401,403,404,405,503) for x in
            ("/api/pipeline/status", "/api/reports", "/api/upload"))
        report={
            "stage":"5J",
            "source_contracts":features,
            "source_comparison_only":True,
            "aws_unauthenticated_http":unauth,
            "unauthenticated_boundary":"PASS" if gate else "REVIEW_REQUIRED",
            "authenticated_functional_acceptance":"NOT_PERFORMED",
            "cloud_run_deployed_version_parity":"NOT_VERIFIED",
            "actual_certificate_recovery":"NOT_TESTED",
            "financial_writes":0,
            "production_changed":False,
            "release_decision":"REVIEW_REQUIRED",
        }
        print(json.dumps(report,indent=2,sort_keys=True))
        return 0 if gate else 2
    except (OSError, ValueError) as exc:
        print("STAGE5J_BLOCKED="+type(exc).__name__)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
