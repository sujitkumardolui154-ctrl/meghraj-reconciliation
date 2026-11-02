import os
import sys
import json
import time
import socket
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [
    str(ROOT / "dashboard_source"),
    str(ROOT / "backend_source"),
    str(ROOT / "source"),
]

os.environ["FIREBASE_WEB_API_KEY"] = (
    "TEST_ONLY_NOT_A_REAL_FIREBASE_KEY"
)

from production_gateway import app
from firebase_admin import auth

REPORT = ROOT / "reports/step154_complete_qa.json"

results = []
context = {}


def record(name, status, detail):
    results.append({
        "test": name,
        "status": status,
        "detail": str(detail)[:500],
    })
    print(f"{status}: {name} — {detail}", flush=True)


def block_network(*args, **kwargs):
    raise RuntimeError(
        "External network access prohibited in QA"
    )


def csrf_headers(client):
    response = client.get("/auth/csrf")
    if response.status_code != 200:
        raise RuntimeError(
            f"CSRF bootstrap HTTP {response.status_code}"
        )

    data = response.get_json(silent=True) or {}
    token = None

    if isinstance(data, dict):
        for key in (
            "csrfToken", "csrf_token",
            "token", "csrf"
        ):
            if isinstance(data.get(key), str):
                token = data[key]
                break

    # Application may use a CSRF cookie rather
    # than returning the token in JSON.
    cookies = response.headers.getlist("Set-Cookie")

    if not token:
        for cookie in cookies:
            first = cookie.split(";", 1)[0]
            if "=" in first:
                name, value = first.split("=", 1)
                if "csrf" in name.lower():
                    token = value
                    break

    if not token:
        raise RuntimeError(
            "Could not identify CSRF token; "
            "review application's actual CSRF contract"
        )

    return [
        {"X-CSRF-Token": token},
        {"X-CSRFToken": token},
        {"X-XSRF-Token": token},
    ]


def identity():
    return {
        "uid": "qa-synthetic-user",
        "email": "qa@example.invalid",
        "email_verified": True,
        "auth_time": int(time.time()),
        "firebase": {"sign_in_provider": "password"},
    }


def cookie_headers(response):
    return response.headers.getlist("Set-Cookie")


def perform_mock_login():
    """
    Exercises the real Flask session route.
    Only external Firebase operations are mocked.
    CSRF handling is not patched.
    """
    client = app.test_client()
    headers_list = csrf_headers(client)

    attempts = []

    for headers in headers_list:
        for field in ("idToken", "id_token", "token"):
            with patch.object(
                auth, "verify_id_token",
                return_value=identity()
            ) as verify, patch.object(
                auth, "create_session_cookie",
                return_value="QA_SYNTHETIC_SESSION_COOKIE"
            ) as create, patch.object(
                auth, "verify_session_cookie",
                return_value=identity()
            ):
                response = client.post(
                    "/auth/session",
                    json={
                        field: "QA_SYNTHETIC_ID_TOKEN"
                    },
                    headers=headers,
                )

                attempts.append({
                    "status": response.status_code,
                    "field": field,
                    "firebase_verify_called": verify.called,
                    "firebase_cookie_called": create.called,
                })

                if (
                    response.status_code in (200, 201, 204)
                    and verify.called
                    and create.called
                ):
                    context["client"] = client
                    context["headers"] = headers
                    context["login_response"] = response
                    context["identity"] = identity()
                    return

    raise RuntimeError(
        "Authenticated mock login did not succeed. "
        "Observed: " + json.dumps(attempts)
    )


def run_existing_suite():
    path = ROOT / "tests/test_meghraj_complete_auth.py"

    if not path.is_file():
        record(
            "Existing 18-test suite",
            "BLOCKED",
            "Original test file missing"
        )
        return

    process = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(sys.path),
        },
    )

    output = process.stdout + process.stderr

    if process.returncode == 0 and "skipped=4" in output:
        record(
            "Existing 18-test suite",
            "PASS",
            "14 passed; 4 intentionally skipped"
        )
    elif process.returncode == 0:
        record(
            "Existing 18-test suite",
            "REVIEW",
            "Suite exited successfully; inspect individual counts"
        )
    else:
        record(
            "Existing 18-test suite",
            "FAIL",
            output[-400:]
        )


def test_valid_login():
    try:
        perform_mock_login()
        record(
            "15 Valid authenticated login",
            "PASS",
            "Firebase verification and cookie creation called"
        )
    except Exception as exc:
        record(
            "15 Valid authenticated login",
            "BLOCKED",
            exc
        )


def test_logout():
    client = context.get("client")

    if client is None:
        record(
            "16 Logout invalidation",
            "BLOCKED",
            "Valid mock session unavailable"
        )
        return

    try:
        before = client.get("/auth/me")

        with patch.object(
            auth, "revoke_refresh_tokens",
            return_value=None
        ):
            logout = client.post(
                "/auth/logout",
                headers=context["headers"]
            )

        after = client.get("/auth/me")

        ok = (
            before.status_code == 200
            and logout.status_code in (200, 204)
            and after.status_code in (401, 403)
        )

        record(
            "16 Logout invalidation",
            "PASS" if ok else "FAIL",
            f"Before={before.status_code}; "
            f"Logout={logout.status_code}; "
            f"After={after.status_code}"
        )
    except Exception as exc:
        record(
            "16 Logout invalidation",
            "BLOCKED",
            exc
        )


def test_expired_session():
    client = context.get("client")

    if client is None:
        record(
            "17 Expired session rejection",
            "BLOCKED",
            "Authenticated cookie not established"
        )
        return

    try:
        # Expiry validation needs a freshly authenticated
        # session after the logout test.
        perform_mock_login()
        client = context["client"]

        # Mock only Firebase's external verification.
        with patch.object(
            auth, "verify_session_cookie",
            side_effect=auth.ExpiredSessionCookieError(
                "QA synthetic expired session",
                cause=None
            )
        ) as verifier:
            response = client.get("/auth/me")

        if not verifier.called:
            record(
                "17 Expired session rejection",
                "BLOCKED",
                "Session identity handler did not call "
                "the patched Firebase verification boundary"
            )
        else:
            record(
                "17 Expired session rejection",
                "PASS" if response.status_code in (401, 403)
                else "FAIL",
                f"Expired cookie HTTP {response.status_code}"
            )
    except Exception as exc:
        record(
            "17 Expired session rejection",
            "BLOCKED",
            exc
        )


def test_secure_cookie():
    response = context.get("login_response")

    if response is None:
        record(
            "18 Secure session cookie",
            "BLOCKED",
            "No successful authenticated login response"
        )
        return

    cookies = cookie_headers(response)

    # Identify the actual HttpOnly session cookie.
    session_cookies = [
        cookie for cookie in cookies
        if "httponly" in cookie.lower()
    ]

    if not session_cookies:
        record(
            "18 Secure session cookie",
            "FAIL",
            "No HttpOnly session cookie found"
        )
        return

    checks = []

    for cookie in session_cookies:
        lower = cookie.lower()
        checks.append(
            "secure" in lower
            and "httponly" in lower
            and "samesite=lax" in lower
            and ("max-age=" in lower
                 or "expires=" in lower)
        )

    record(
        "18 Secure session cookie",
        "PASS" if all(checks) else "FAIL",
        "Runtime Secure, HttpOnly, SameSite "
        "and expiry attributes checked"
    )


print("=== MEGHRAJ COMPLETE AUTHENTICATION QA ===")
print("MODE: SYNTHETIC LOCAL ONLY")
print("EXTERNAL NETWORK: BLOCKED")

with patch.object(socket.socket, "connect",
                  side_effect=block_network):
    run_existing_suite()
    test_valid_login()
    test_secure_cookie()
    test_logout()
    test_expired_session()

summary = {
    "passed": sum(x["status"] == "PASS" for x in results),
    "failed": sum(x["status"] == "FAIL" for x in results),
    "blocked": sum(x["status"] == "BLOCKED" for x in results),
    "review": sum(x["status"] == "REVIEW" for x in results),
}

release_ready = (
    summary["failed"] == 0
    and summary["blocked"] == 0
    and summary["review"] == 0
)

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps({
        "summary": summary,
        "results": results,
        "release_ready_for_further_staging_qa": release_ready,
    }, indent=2),
    encoding="utf-8"
)

print("\n=== STEP 154 FINAL SUMMARY ===")
print("PASSED GROUPS:", summary["passed"])
print("FAILED GROUPS:", summary["failed"])
print("BLOCKED GROUPS:", summary["blocked"])
print("REVIEW GROUPS:", summary["review"])
print("REPORT:", REPORT)
print(
    "STEP 154:",
    "LOCAL TEST GATE PASSED"
    if release_ready else "REVIEW REQUIRED"
)

sys.exit(0 if release_ready else 1)
