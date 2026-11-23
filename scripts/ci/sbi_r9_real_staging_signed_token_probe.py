"""R9 opt-in REAL Firebase signed-token staging QA. NOT run by GitHub CI.

This is intentionally an isolated *manual* harness. It never uses production
Firebase, an Auth emulator, AWS, live SBI records, or financial posting.
It creates/deletes disposable test users ONLY in an explicitly allowlisted
separate Firebase staging project, subject to runtime identity checks.
Do not pass tokens, passwords or secrets in command-line arguments.
"""
from __future__ import annotations

import io
import json
import os
import secrets
import stat
import tempfile
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

PRODUCTION_PROJECT = "meghraj-reconciliation"
GATE_VALUE = "R9_REAL_FIREBASE_STAGING_QA_ONLY"
LAST_RUN_CHECK = "R9_REAL_STAGING_SIGNED_TOKENS"
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def fail(reason: str):
    raise RuntimeError("R9_REAL_STAGING_REFUSED: " + reason)


def check_environment():
    """No Firebase SDK import or credential discovery before these checks."""
    if os.environ.get("SBI_R9_REAL_STAGING_PROBE") != GATE_VALUE:
        fail("dedicated explicit R9 gate required")
    if os.environ.get("SBI_R8_STAGING_MODE") != "SBI_R8_STAGING_ONLY_NONFINANCIAL":
        fail("R8 staging-only mode required")
    if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        fail("Auth Emulator forbidden for real signed-token QA")
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        fail("service-account JSON file forbidden")
    if os.environ.get("FIREBASE_WEB_API_KEY"):
        fail("inherited Firebase web API key forbidden")
    if os.environ.get("SBI_PAYMENT_EVIDENCE_DIR"):
        fail("inherited payment evidence storage forbidden")
    if os.environ.get("SBI_PRIVATE_WORKSPACE_DB"):
        fail("inherited workspace database forbidden")
    project = os.environ.get("SBI_R8_STAGING_FIREBASE_PROJECT_ID", "")
    if project == PRODUCTION_PROJECT or not __import__("re").fullmatch(
        r"sbi-r8-staging-[a-z][a-z0-9-]{2,12}", project
    ):
        fail("separate staging project prefix required")
    key = os.environ.get("SBI_R8_STAGING_FIREBASE_WEB_API_KEY", "")
    if not 20 <= len(key) <= 120 or any(c.isspace() for c in key):
        fail("separately supplied staging web API key required")
    site = os.environ.get("SBI_R8_STAGING_SITE_ORIGIN", "")
    from urllib.parse import urlsplit
    try:
        url = urlsplit(site)
    except ValueError:
        fail("separate HTTPS staging origin required")
    if (
        url.scheme != "https"
        or not url.hostname
        or not url.hostname.startswith("sbi-r8-staging-")
        or url.username or url.password or url.port is not None
        or url.path or url.query or url.fragment
        or site != f"https://{url.hostname}"
        or site == "https://sbi-preview.13-232-241-221.sslip.io"
    ):
        fail("separate HTTPS staging origin required")
    for name in ("GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        other = os.environ.get(name)
        if other and other != project:
            fail("inherited Google project does not match approved staging project")
    if not os.environ.get("SBI_READONLY_QUARANTINE_SOL_KEYS"):
        fail("explicit synthetic-only quarantine SOL keys required")
    return project, site, key


def real_sign_in(email, password, web_api_key):
    """Use real Identity Toolkit, NOT the emulator. NEVER log any tokens."""
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        "?key=" + quote(web_api_key, safe="")
    )
    data = json.dumps({
        "email": email, "password": password, "returnSecureToken": True,
    }).encode("utf-8")
    with urlopen(
        Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        ),
        timeout=20,
    ) as response:
        if response.status != 200:
            fail("real test-project sign-in rejected")
        return json.load(response)["idToken"]


def xlsx():
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = "PAYMENT EVIDENCE"
    sheet.append(("Description", "SOL ID", "Credit Amount"))
    sheet.append(("SYNTHETIC R9 QA ONLY", "07001", 5.25))
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def check(value, message):
    if not value:
        raise RuntimeError("R9_REAL_STAGING_QA_FAILED: " + message)


def execute():
    project, origin, web_key = check_environment()

    # Discover bound runtime identity only AFTER the explicit environment gate.
    # Reject cross-project ADC, even when the Firebase SDK is given an explicit
    # project option. A nonproduction identity must be bound to staging only.
    import google.auth
    credentials, adc_project = google.auth.default(
        scopes=("https://www.googleapis.com/auth/cloud-platform",)
    )
    del credentials
    if adc_project != project:
        fail("runtime ADC project mismatch or unknown; no auth-user mutation permitted")

    import sys
    if str(SOURCE_ROOT / "staging/aws_login_v150") not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT / "staging/aws_login_v150"))
    from firebase_admin import auth

    with tempfile.TemporaryDirectory(prefix="sbi-r8-staging-r9-", dir="/tmp") as dir_name:
        Path(dir_name).chmod(0o700)
        if stat.S_IMODE(Path(dir_name).stat().st_mode) != 0o700:
            fail("private temporary evidence directory must be 0700")
        os.environ["SBI_R8_STAGING_EVIDENCE_DIR"] = dir_name

        import r8_staging_entrypoint as stage
        check(stage.project == project, "staging launcher project differs")
        check(stage.origin == origin, "staging origin differs")
        check(stage.app.config["SBI_R8_FINANCIAL_APPLY_LOCKED"], "financial Apply not locked")

        # Local Flask test client, NOT a public/production deployment.
        client = stage.app.test_client()
        fb_app = stage.session_config.firebase_app()
        created = []
        password = secrets.token_urlsafe(24) + "Aa1!"
        accounts = {}
        unique = uuid.uuid4().hex[:12]

        try:
            for role in ("primary", "secondary"):
                email = f"sbi-r9-{role}-{unique}@example.invalid"
                user = auth.create_user(
                    email=email, password=password, app=fb_app
                )
                created.append(user.uid)
                auth.set_custom_user_claims(
                    user.uid, {"dil_dashboard": True}, app=fb_app,
                )
                accounts[role] = {"uid": user.uid, "email": email}

            def login(session_client, role):
                csrf = session_client.get("/auth/csrf")
                check(csrf.status_code == 200, "CSRF endpoint")
                csrf_value = csrf.json["csrf_token"]
                signed = real_sign_in(
                    accounts[role]["email"], password, web_key
                )
                verified = auth.verify_id_token(
                    signed, check_revoked=True, app=fb_app
                )
                check(verified.get("aud") == project, "signed token wrong audience")
                check(
                    verified.get("iss") == "https://securetoken.google.com/" + project,
                    "signed token wrong issuer",
                )
                check(
                    verified.get("firebase", {}).get("sign_in_provider") == "password",
                    "non-password sign-in provider",
                )
                r = session_client.post(
                    "/auth/session",
                    json={"idToken": signed},
                    headers={
                        "Origin": origin,
                        "X-DIL-CSRF": csrf_value,
                    },
                )
                check(r.status_code == 200, "real signed-token login failed")
                check(
                    any(
                        c.startswith("__Host-dil_session=")
                        and "Secure" in c and "HttpOnly" in c
                        for c in r.headers.getlist("Set-Cookie")
                    ),
                    "secure session cookie missing",
                )
                return csrf_value

            csrf_a = login(client, "primary")
            me = client.get("/auth/me")
            check(me.status_code == 200, "protected identity response")
            check(me.json["administrator"] is False, "staging master privileges")
            status = client.get("/api/payment-reconciliation/status")
            check(status.status_code == 200, "protected reconciliation status")
            check(status.json["engine"] == "NOT_CONNECTED", "engine unexpectedly connected")
            check(status.json["financial_apply_locked"] is True, "Apply lock missing")

            data = xlsx()
            upload = client.post(
                "/api/payment-evidence/upload",
                data={"file": (io.BytesIO(data), "SYNTHETIC_R9.xlsx")},
                headers={"Origin": origin, "X-DIL-CSRF": csrf_a},
                content_type="multipart/form-data",
            )
            check(upload.status_code == 201, "synthetic staging upload refused")
            check(upload.json["financial_writes"] is False, "financial write reported")
            rid = upload.json["receipt_id"]
            dup = client.post(
                "/api/payment-evidence/upload",
                data={"file": (io.BytesIO(data), "SYNTHETIC_R9.xlsx")},
                headers={"Origin": origin, "X-DIL-CSRF": csrf_a},
                content_type="multipart/form-data",
            )
            check(dup.status_code == 409, "duplicate should be refused")

            pre = client.post(
                "/api/payment-reconciliation/preflight",
                json={"receipt_id": rid},
                headers={"Origin": origin, "X-DIL-CSRF": csrf_a},
            )
            check(pre.status_code == 503, "reconciliation must remain disconnected")
            check(
                pre.json["code"] == "APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED",
                "wrong preflight lock",
            )
            for route in ("/api/payment-reconciliation/run", "/api/imports/apply"):
                denied = client.post(
                    route, json={},
                    headers={"Origin": origin, "X-DIL-CSRF": csrf_a},
                )
                check(denied.status_code == 403, "financial route must be denied")

            other_client = stage.app.test_client()
            csrf_b = login(other_client, "secondary")
            foreign = other_client.get("/api/payment-evidence/uploads/" + rid)
            check(foreign.status_code == 404, "cross-user receipt disclosed")
            foreign_preflight = other_client.post(
                "/api/payment-reconciliation/preflight",
                json={"receipt_id": rid},
                headers={"Origin": origin, "X-DIL-CSRF": csrf_b},
            )
            check(foreign_preflight.status_code == 404, "cross-user preflight disclosed")

            # Live Firebase admin permissions check: disabling an account must
            # invalidate subsequent protected access. Restore before cleanup.
            uid = accounts["primary"]["uid"]
            auth.update_user(uid, disabled=True, app=fb_app)
            check(
                client.get("/api/payment-reconciliation/status").status_code in (401, 403),
                "disabled Firebase user could still access status",
            )
            auth.update_user(uid, disabled=False, app=fb_app)
            print("R9_SIGNED_TEST_PROJECT_TOKEN=PASS")
            print("R9_REAL_SESSION_OWNERSHIP_CSRF_AND_LOCK=PASS")
            print("R9_SBI_FINANCIAL_RECORDS=NOT_USED")
            print("R9_AWS_DEPLOYMENT=NOT_PERFORMED")
            print("R9_FINANCIAL_APPLY=LOCKED")
        finally:
            # If cleanup fails, raise: do not claim staging was clean.
            problems = []
            for uid in reversed(created):
                try:
                    auth.delete_user(uid, app=fb_app)
                except Exception:
                    problems.append("test user cleanup failed")
            if problems:
                raise RuntimeError(
                    "R9_REAL_STAGING_CLEANUP_FAILED: test users require secure review"
                )
            print("R9_TEST_USERS_DELETED=PASS")


if __name__ == "__main__":
    # Deliberately uses no external services before the explicit fail-closed guard.
    check_environment()
    execute()
