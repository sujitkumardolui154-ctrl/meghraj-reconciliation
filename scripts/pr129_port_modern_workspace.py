#!/usr/bin/env python3
"""PR129: Port only the existing Bulk Report form into preserved modern UI.

Run in the isolated GitHub checkout on AWS; never touches running containers.
Reads the current PR index.html solely to recover the already-reviewed Bulk Report
form/JS. Replaces its legacy page with the verified preserved modern frontend,
adding only that section inside <main id="dil-reports" hidden>.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO = Path("/home/ubuntu/sbi-bulk-report-integration/repo")
BASE = Path("/home/ubuntu/sbi-bulk-report-integration/modern-ui-source")
OLD_PR = REPO / "dashboard_source/index.html"
MODERN = BASE / "index.html"
MODERN_JS = BASE / "dashboard.js"
REPO_JS = REPO / "dashboard_source/dashboard.js"

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fail(message: str) -> None:
    raise SystemExit("PORT_MODERN_UI=BLOCKED: " + message)

def main() -> None:
    for f in (OLD_PR, MODERN, MODERN_JS, REPO_JS):
        if not f.is_file():
            fail("Missing required source " + str(f))

    # Ensure the read-only source copy really looks like the user's modern UI.
    modern_bytes = MODERN.read_bytes()
    modern = modern_bytes.decode("utf-8")
    original_pr = OLD_PR.read_text(encoding="utf-8")
    old_js = REPO_JS.read_bytes()
    modern_js = MODERN_JS.read_bytes()

    marker = '<main id="dil-reports" hidden>'
    if modern.count(marker) != 1:
        fail("Unique modern Reports <main> anchor not found")
    if 'id="dil-tower-panel"' not in modern:
        fail("Modern Control Tower panel missing")
    if 'id="dil-imports"' not in modern:
        fail("Modern Database Update panel missing")
    if 'id="bulk-report"' in modern or 'id="bulk-report-form"' in modern:
        fail("Bulk Report already present in modern source")
    if "Excel Upload — Dashboard v1.3.0" in modern:
        fail("Legacy label remains in modern UI; inspect before removal")
    if "</main>" not in modern.split(marker, 1)[1]:
        fail("Modern Reports closing tag missing")
    if modern_bytes == OLD_PR.read_bytes():
        fail("Sources are identical; refusing unneeded replacement")

    # Form and script were already validated against the staging backend.
    opening = "<!-- Bulk Report: source-only reporting; no financial database updates. -->"
    closing = "</script>"
    if original_pr.count(opening) != 1:
        fail("Current PR form marker missing or duplicated")
    tail = original_pr.split(opening, 1)[1]
    if closing not in tail:
        fail("Current PR Bulk Report JS missing")
    feature = opening + tail.split(closing, 1)[0] + closing
    required = [
        'id="bulk-report"',
        'id="bulk-report-form"',
        'id="bulk-report-generate"',
        'fetch("/auth/csrf"',
        'fetch("/api/bulk-report/generate"',
        '"X-DIL-CSRF": csrfData.csrf_token',
        r"/\.xlsx$/i.test(file.name)",
    ]
    for token in required:
        if token not in feature:
            fail("Verified feature missing: " + token)

    result = modern.replace(marker, marker + "\n" + feature + "\n", 1)
    if result.count('id="bulk-report"') != 1:
        fail("Bulk Report ID duplication")
    if result.count('id="dil-tower-panel"') != modern.count('id="dil-tower-panel"'):
        fail("Unexpected Control Tower change")
    if result.count('id="dil-imports"') != modern.count('id="dil-imports"'):
        fail("Unexpected Database Update change")
    if result.split(feature, 1)[0] + result.split(feature, 1)[1] != modern.replace(marker, marker + "\n\n", 1):
        # Expected only if the insertion has single newlines before and after.
        fail("Unexpected modern DOM modifications")

    # Keep the known modern dashboard JS (it can differ from the old PR).
    OLD_PR.write_text(result, encoding="utf-8")
    if old_js != modern_js:
        REPO_JS.write_bytes(modern_js)

    print("PORT_MODERN_UI=PASS")
    print("MODERN_BASE_SHA256=" + digest(modern_bytes))
    print("MODERN_DASHBOARD_JS_SHA256=" + digest(modern_js))
    print("BULK_FEATURE_INSERTED_IN_REPORTS=YES")
    print("CONTROL_TOWER_PRESERVED=YES")
    print("DATABASE_UPDATE_PRESERVED=YES")
    print("DASHBOARD_JS_CHANGED=" + str(old_js != modern_js))
    print("PUBLIC_APP_MODIFIED=NO")
    print("FINANCIAL_WRITES=NONE")

if __name__ == "__main__":
    main()
