#!/usr/bin/env python3
"""A01/E07 signed-in reporting HTTP verification (zero writes, no data logged).

The operator must create secure 0600 local files containing ONLY Firebase
__Host-dil_session cookie values from two independent, legitimately signed-in
test users: authorized report viewer and authenticated denied viewer.
Do NOT paste or upload cookie values into chat, GitHub, or artifacts.

  python tools/sbi_reporting_signed_in_e2e.py \
    --base-url https://<private-dashboard-cloud-run-host>.run.app \
    --allowed-cookie-file /private/allowed.cookie \
    --denied-cookie-file /private/denied.cookie

Checks real HTTPS: anonymous 401, role-denied 403, viewer 200 on report
index+CSV. Protected reconciliation changes require a separately authorized
role and existing private receipt for 200; without receipt they are NOT
certified. PASS is reporting-auth readiness only, not financial release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import urllib.error
import urllib.parse
import urllib.request

COOKIE_NAME = "__Host-dil_session"
RECEIPT_RE = re.compile(r"[0-9a-f]{32}\Z")


class ReportingE2EBlocked(ValueError):
    pass


def validate_base_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        raise ReportingE2EBlocked("INVALID_PRIVATE_HTTPS_URL") from None
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host.endswith(".run.app")
            or parsed.username is not None or parsed.password is not None
            or parsed.port is not None or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise ReportingE2EBlocked("PRIVATE_CLOUD_RUN_HTTPS_REQUIRED")
    return url.rstrip("/")


def read_cookie(path):
    path = Path(path)
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > 5000
            or stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise ReportingE2EBlocked("COOKIE_FILE_MUST_BE_PRIVATE_0600")
    value = path.read_text(encoding="utf-8").strip()
    if (not (20 <= len(value) <= 4096)
            or any(ch.isspace() for ch in value)
            or any(ch in value for ch in (";", "\r", "\n"))):
        raise ReportingE2EBlocked("INVALID_COOKIE_FILE")
    return value


def http_status(base, path, cookie=None):
    url = base + path
    headers = {"Accept": "application/json"}
    if cookie is not None:
        headers["Cookie"] = COOKIE_NAME + "=" + cookie
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            # No report/customer data is downloaded, logged or returned.
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (OSError, urllib.error.URLError):
        return 0


def assess(read, *, receipt=None, check_change=False):
    """Pure status-check engine; injectable read() supports synthetic tests."""
    requests = [
        ("ANONYMOUS_REPORT_INDEX", "/api/reports", None, 401),
        ("DENIED_REPORT_INDEX", "/api/reports", "denied", 403),
        ("DENIED_REPORT_CSV", "/api/reports/unpaid.csv", "denied", 403),
        ("ALLOWED_REPORT_INDEX", "/api/reports", "allowed", 200),
        ("ALLOWED_REPORT_CSV", "/api/reports/unpaid.csv", "allowed", 200),
    ]
    if check_change:
        if not isinstance(receipt, str) or RECEIPT_RE.fullmatch(receipt) is None:
            raise ReportingE2EBlocked("VALID_CHANGE_REPORT_RECEIPT_REQUIRED")
        requests += [
            ("DENIED_CHANGE_REPORT", "/api/reports/reconciliation-changes?receipt=" + receipt,
             "denied", 403),
            ("ALLOWED_CHANGE_REPORT", "/api/reports/reconciliation-changes?receipt=" + receipt,
             "change_allowed", 200),
        ]
    results = {}
    for name, path, role, expected in requests:
        status = read(path, role)
        results[name] = {"http": status, "expected": expected,
                         "status": "PASS" if status == expected else "FAIL"}
    return {
        "result": ("REPORTING_AUTH_E2E_PASS" if all(x["status"] == "PASS"
                   for x in results.values()) else "REVIEW_REQUIRED"),
        "checks": results, "change_report_e2e_checked": bool(check_change),
        "firestore_writes": 0, "financial_release": "RESTRICTED",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", required=True)
    p.add_argument("--allowed-cookie-file", type=Path, required=True)
    p.add_argument("--denied-cookie-file", type=Path, required=True)
    p.add_argument("--change-allowed-cookie-file", type=Path)
    p.add_argument("--change-receipt")
    args = p.parse_args(argv)
    try:
        base = validate_base_url(args.base_url)
        allowed = read_cookie(args.allowed_cookie_file)
        denied = read_cookie(args.denied_cookie_file)
        change_allowed = (read_cookie(args.change_allowed_cookie_file)
                          if args.change_allowed_cookie_file else None)
        if allowed == denied or (change_allowed is not None and change_allowed == denied):
            raise ReportingE2EBlocked("TEST_SESSIONS_MUST_BE_DISTINCT")
        if bool(args.change_allowed_cookie_file) != bool(args.change_receipt):
            raise ReportingE2EBlocked("CHANGE_VIEWER_AND_RECEIPT_BOTH_REQUIRED")
        cookies = {"allowed": allowed, "denied": denied,
                   "change_allowed": change_allowed}
        result = assess(
            lambda path, role: http_status(base, path, cookies.get(role)),
            receipt=args.change_receipt,
            check_change=bool(change_allowed),
        )
    except (ReportingE2EBlocked, OSError, UnicodeError, ValueError) as error:
        blocker = str(error) if isinstance(error, ReportingE2EBlocked) else "LOCAL_AUTH_INPUT_INVALID"
        result = {"result": "REVIEW_REQUIRED", "blockers": [blocker],
                  "firestore_writes": 0, "financial_release": "RESTRICTED"}
    # No cookies, identities, receipt IDs, or private response bodies printed.
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["result"] == "REPORTING_AUTH_E2E_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
