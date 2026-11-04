#!/usr/bin/env python3
"""Three-gate SBI QA: synthetic contract tests or restricted read-only live verification.
No financial writes, deployments, or production approval, even if tests pass.
Live mode requires a private runner, dedicated non-admin Firebase identity,
independently approved source CSV and hashes, and Firestore reader-only ADC.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
OFFLINE = (
    "test_sbi_financial_report_parity.py",
    "test_sbi_reconciliation_changes_offline.py",
    "test_sbi_credit_note_53_projection.py",
    "test_financial_contract.py",
)
HOSTS = {
    "sbi-dashboard-109590290120.asia-south1.run.app",
    "sbi-dashboard-ahz6wqeiaq-el.a.run.app",
    "login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app",
}
class Blocked(Exception):
    pass

class DenyRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None

def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise Blocked("PROTECTED_CONFIG_MISSING")
    return value

def req_json(opener, url, data=None, headers=None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = Request(url, data=body, method="GET" if body is None else "POST",
                      headers=headers or {})
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(200001)
            if response.status != 200 or len(raw) > 200000:
                raise Blocked("UNEXPECTED_HTTP_RESULT")
            return json.loads(raw)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        # Do not log URLs, tokens, secrets, cookies, customer values or responses.
        raise Blocked("AUTH_HTTP_BLOCKED") from None

def real_auth():
    key = required("SBI_QA_FIREBASE_API_KEY")
    email = required("SBI_QA_FIREBASE_EMAIL")
    password = required("SBI_QA_FIREBASE_PASSWORD")
    host_url = required("SBI_QA_DASHBOARD_URL").rstrip("/")
    parsed = urlparse(host_url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or parsed.username or parsed.password or parsed.port):
        raise Blocked("UNAPPROVED_DASHBOARD_HOST")
    if os.environ.get("SBI_QA_TEST_ACCOUNT_ISOLATED") != "true":
        raise Blocked("DEDICATED_QA_IDENTITY_NOT_APPROVED")
    if (email.lower() == "sujitkumardolui154@gmail.com"
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
        raise Blocked("UNSAFE_QA_IDENTITY")
    opener = build_opener(DenyRedirects(), HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = "https://identitytoolkit.googleapis.com/v1/accounts:"
    result = req_json(opener, base + "signInWithPassword?key=" + key,
                      {"email": email, "password": password, "returnSecureToken": True})
    token = result.get("idToken")
    if not isinstance(token, str) or not token or not result.get("localId"):
        raise Blocked("REAL_FIREBASE_SIGNIN_NOT_VERIFIED")
    info = req_json(opener, base + "lookup?key=" + key, {"idToken": token})
    users = info.get("users")
    if (not isinstance(users, list) or len(users) != 1
            or users[0].get("localId") != result["localId"]
            or users[0].get("email", "").casefold() != email.casefold()):
        raise Blocked("FIREBASE_IDENTITY_MISMATCH")
    csrf = req_json(opener, host_url + "/auth/csrf").get("csrf_token")
    if not isinstance(csrf, str) or len(csrf) != 64:
        raise Blocked("SESSION_CSRF_NOT_VERIFIED")
    req_json(opener, host_url + "/auth/session",
             {"idToken": token}, {"Origin": host_url, "X-DIL-CSRF": csrf})
    session = req_json(opener, host_url + "/auth/me")
    if (session.get("email", "").casefold() != email.casefold()
            or session.get("administrator") is not False):
        raise Blocked("DASHBOARD_SESSION_IDENTITY_NOT_VERIFIED")
    return {"firebase_real_login": "PASS", "dashboard_real_session": "PASS"}

def approved_source():
    from sbi_financial_report_parity import _load_verified_csv
    sha = required("SBI_QA_APPROVED_SOURCE_SHA256")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise Blocked("INDEPENDENT_SOURCE_DIGEST_REQUIRED")
    rows = _load_verified_csv(required("SBI_QA_SOURCE_CSV_PATH"), sha)
    return sha, rows

def live_db(sha, source):
    if os.environ.get("SBI_QA_READONLY_IDENTITY_CONFIRMED") != "true":
        raise Blocked("READER_IDENTITY_NOT_APPROVED")
    dataset = required("SBI_QA_DATASET_ID")
    if dataset != sha + "-report-v1":
        raise Blocked("DATASET_SOURCE_DIGEST_MISMATCH")
    from google.cloud import firestore
    from sbi_financial_report_parity import SOURCE_HEADERS
    db = firestore.Client(project="meghraj-reconciliation")
    doc = db.collection("dashboard_report_datasets").document(dataset)
    snapshot = doc.get(timeout=20)
    meta = snapshot.to_dict() if snapshot.exists else {}
    size = len(source)
    if (meta.get("state") != "READY" or meta.get("source_sha256") != sha
            or meta.get("original_headers") != SOURCE_HEADERS
            or meta.get("original_columns_state") != "READY"
            or meta.get("original_column_count") != 53
            or meta.get("rows") != size or meta.get("original_columns_row_count") != size):
        raise Blocked("LIVE_DATABASE_METADATA_MISMATCH")
    seen = set()
    query = doc.collection("rows").order_by("__name__")
    cursor = None
    while True:
        page = query.limit(200)
        if cursor is not None:
            page = page.start_after(cursor)
        records = page.get(timeout=60)
        for snapshot in records:
            row = snapshot.to_dict() or {}
            number = row.get("source_row")
            if (type(number) is not int or not 2 <= number < size + 2
                    or number in seen or row.get("source_sha256") != sha
                    or row.get("original_columns_source_sha256") != sha
                    or row.get("original_values") != list(source[number-2])):
                raise Blocked("LIVE_53_COLUMN_SOURCE_PARITY_MISMATCH")
            seen.add(number)
        if len(seen) > size:
            raise Blocked("LIVE_SOURCE_COUNT_EXCEEDED")
        if len(records) < 200:
            break
        cursor = records[-1]
    if len(seen) != size:
        raise Blocked("LIVE_DATABASE_ROWS_INCOMPLETE")
    if db.collection("dashboard_invoice_rows_v140").limit(1).get(timeout=20):
        raise Blocked("IMPORTED_INVOICES_REQUIRE_SEPARATE_PARITY")
    return {"live_original_53_parity": "PASS", "baseline_rows_checked": size}

def report_values(source):
    from sbi_financial_report_parity import _load_verified_csv, evaluate
    manifest_path = Path(required("SBI_QA_REPORT_MANIFEST_PATH"))
    if (not manifest_path.is_file() or manifest_path.is_symlink()
            or manifest_path.stat().st_size > 65536):
        raise Blocked("PRIVATE_REPORT_MANIFEST_MISSING")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    reports = data.get("reports")
    allowed = {"unpaid", "ok", "error-value", "balance-review"}
    if (not isinstance(reports, dict) or
            not {"unpaid", "ok", "error-value"} <= reports.keys() or
            not reports.keys() <= allowed):
        raise Blocked("APPROVED_REPORT_SET_MISSING")
    groups = {name: _load_verified_csv(spec["path"], spec["sha256"])
              for name, spec in reports.items()}
    result = evaluate(source, groups)
    if result["blockers"] or result["partition_report_rows"] != len(source):
        raise Blocked("FINANCIAL_REPORT_VALUE_EXCEPTION_REVIEW")
    # The existing parity evaluator explicitly does not compare bank payments.
    return {"financial_report_values": "SOURCE_REPORT_PARTITION_PASS",
            "reconciliation_bank_payment_parity": "NOT_VERIFIED",
            "report_rows_checked": result["partition_report_rows"]}

def offline_tests():
    results = {}
    for test in OFFLINE:
        try:
            p = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover",
                                "-s", "tests", "-p", test, "-q"],
                               cwd=ROOT, capture_output=True, timeout=120)
            results[test] = "PASS" if p.returncode == 0 else "FAIL"
        except (OSError, subprocess.TimeoutExpired):
            results[test] = "FAIL"
    return results

def run(mode):
    result = {
        "schema": "sbi-three-gate-v1",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "firebase_real_login": "NOT_TESTED",
        "dashboard_real_session": "NOT_TESTED",
        "live_original_53_parity": "NOT_VERIFIED",
        "financial_report_values": "NOT_VERIFIED",
        "reconciliation_bank_payment_parity": "NOT_VERIFIED",
        "financial_writes": 0, "production_deployments": 0,
        "production_cutover": "BLOCKED",
    }
    if mode == "offline":
        result["synthetic_tests"] = offline_tests()
        ok = all(v == "PASS" for v in result["synthetic_tests"].values())
        result["status"] = ("SYNTHETIC_PASS_LIVE_GATES_BLOCKED" if ok
                            else "OFFLINE_TESTS_FAILED")
        return result, ok
    if os.environ.get("SBI_PRIVATE_QA_APPROVED") != "true":
        result["status"] = "BLOCKED_PRIVATE_APPROVAL_REQUIRED"
        return result, False
    try:
        result.update(real_auth())
    except Exception:
        result["firebase_real_login"] = "BLOCKED_OR_FAILED"
        result["dashboard_real_session"] = "BLOCKED_OR_FAILED"
    try:
        sha, source = approved_source()
    except Exception:
        sha, source = None, None
        result["live_original_53_parity"] = "BLOCKED_SOURCE_PROVENANCE"
        result["financial_report_values"] = "BLOCKED_SOURCE_PROVENANCE"
    if source is not None:
        try:
            result.update(live_db(sha, source))
        except Exception:
            result["live_original_53_parity"] = "BLOCKED_OR_FAILED"
        try:
            result.update(report_values(source))
        except Exception:
            result["financial_report_values"] = "BLOCKED_OR_FAILED"
    result["status"] = "REVIEW_REQUIRED_BANK_RECONCILIATION_UNVERIFIED"
    return result, False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "private-live"),
                        default="offline")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report, ok = run(args.mode)
    if args.output.is_symlink():
        raise SystemExit("UNSAFE_QA_OUTPUT_PATH")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("SBI_THREE_GATE_QA=" + report["status"])
    for key in ("firebase_real_login", "dashboard_real_session",
                "live_original_53_parity", "financial_report_values",
                "reconciliation_bank_payment_parity"):
        print(key.upper() + "=" + report[key])
    print("FINANCIAL_WRITES=0")
    print("PRODUCTION_CUTOVER=BLOCKED")
    return 0 if ok else 2

if __name__ == "__main__":
    raise SystemExit(main())
