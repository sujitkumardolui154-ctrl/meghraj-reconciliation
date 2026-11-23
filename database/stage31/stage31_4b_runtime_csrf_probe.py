#!/usr/bin/env python3
"""Stage 31.4B: bounded local synthetic CSRF origin check against deployed code.

No browser tokens, Firebase sessions, privileged app routes, DB connections,
network calls, or live app mutations. Do not print origin allowlist or cookies.
The check uses a TEST Flask request context in an isolated Python process
inside the existing release image, importing only the deployed session helper.
"""
import sys
sys.path.insert(0, "/app")
from flask import Flask
from dashboard_sessions import csrf_valid, CSRF_COOKIE

PRODUCTION_ORIGIN = "https://pr129.13-232-241-221.sslip.io"
FAKE_COOKIE = "c" * 64
FAKE_HEADER_MISMATCH = "d" * 64
app = Flask("stage31_4b_runtime_csrf_source_probe")

def test_origin(origin, token):
    headers = {
        "Origin": origin,
        "X-DIL-CSRF": token,
        "Cookie": f"{CSRF_COOKIE}={FAKE_COOKIE}",
    }
    with app.test_request_context(
        "/__stage31_4/invoice/preview",
        method="POST",
        headers=headers,
    ):
        return csrf_valid() is True

def main():
    print("STAGE31_4B_CSRF_PROBE=DEPLOYED_SOURCE_SYNTHETIC_CONTEXT_NO_SECRETS")
    try:
        good = test_origin(PRODUCTION_ORIGIN, FAKE_COOKIE)
        wrong_origin = test_origin("https://untrusted.invalid", FAKE_COOKIE)
        wrong_token = test_origin(PRODUCTION_ORIGIN, FAKE_HEADER_MISMATCH)
        missing_origin = test_origin("", FAKE_COOKIE)
    except Exception:
        print("STAGE31_4B_CSRF_ORIGIN_RUNTIME=REVIEW_REQUIRED_PROBE_ERROR")
        print("STAGE31_4B_CSRF_PROBE_REAL_OWNER_LOGIN=NOT_PERFORMED")
        return 0
    print("STAGE31_4B_CSRF_UNTRUSTED_ORIGIN_DENIED=" + (
        "PASS" if not wrong_origin else "FAIL"
    ))
    print("STAGE31_4B_CSRF_MISMATCHED_TOKEN_DENIED=" + (
        "PASS" if not wrong_token else "FAIL"
    ))
    print("STAGE31_4B_CSRF_MISSING_ORIGIN_DENIED=" + (
        "PASS" if not missing_origin else "FAIL"
    ))
    if good and not any((wrong_origin, wrong_token, missing_origin)):
        print("STAGE31_4B_CSRF_ORIGIN_RUNTIME=PASS_SYNTHETIC_PRODUCTION_ORIGIN")
    else:
        print("STAGE31_4B_CSRF_ORIGIN_RUNTIME=REVIEW_REQUIRED_NO_UPLOAD_ACTIVATION")
    print("STAGE31_4B_CSRF_PROBE_REAL_OWNER_LOGIN=NOT_PERFORMED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
