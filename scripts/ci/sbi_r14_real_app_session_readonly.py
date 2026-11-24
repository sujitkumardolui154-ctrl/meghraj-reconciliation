"""R14 manual REAL Firebase ID token -> local SBI Flask session integration.

Cloud Shell only, separately authorized sbi-r9-staging. Never runs from CI.
No user/claim changes, database connection, AWS deployment, upload, or logout
(which would revoke refresh tokens). No secrets, user data or tokens printed.
"""
from __future__ import annotations

import getpass
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

PROJECT = "sbi-r9-staging"
QA_ACCOUNT = "sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com"
TEST_EMAIL = "sbi-r9-test01@example.com"
TEST_ORIGIN = "https://sbi-r9-staging-local.invalid"  # Flask test client only; NO DNS/AWS
OPT_IN = "R14_REAL_STAGING_APP_SESSION_READONLY"
ROOT = Path(__file__).resolve().parents[2]


class R14Refused(RuntimeError):
    pass


def refuse(code: str):
    raise R14Refused(code)


def check_environment(environ=None):
    env = os.environ if environ is None else environ
    if env.get("SBI_R14_REAL_APP_SESSION") != OPT_IN:
        refuse("EXPLICIT_APPROVAL_GATE_REQUIRED")
    if env.get("CI") or env.get("GITHUB_ACTIONS"):
        refuse("GITHUB_CI_FORBIDDEN")
    if env.get("GCLOUD_PROJECT") != PROJECT:
        refuse("ACTIVE_GCLOUD_PROJECT_NOT_STAGING")
    for name in ("GCP_PROJECT", "GOOGLE_CLOUD_PROJECT"):
        if env.get(name) and env[name] != PROJECT:
            refuse("INHERITED_GCLOUD_PROJECT_MISMATCH")
    for name in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "FIREBASE_AUTH_EMULATOR_HOST",
        "FIREBASE_WEB_API_KEY",
        "SBI_PAYMENT_EVIDENCE_DIR",
        "SBI_PRIVATE_WORKSPACE_DB",
        "SBI_R9_REAL_STAGING_PROBE",
        "SBI_R11_READONLY_FIREBASE",
        "SBI_R8_STAGING_FIREBASE_WEB_API_KEY",
        "SBI_R8_STAGING_EVIDENCE_DIR",
    ):
        if env.get(name):
            refuse("INHERITED_ENVIRONMENT_FORBIDDEN")
    keys = env.get("SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS", "")
    if not keys or not all(
        re.fullmatch(r"[0-9]{1,12}", x.strip())
        for x in keys.split(",")
    ):
        refuse("APPROVED_SYNTHETIC_SOL_KEYS_REQUIRED")
    return keys


def real_login(api_key: str, password: str) -> str:
    request = Request(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
        + quote(api_key, safe=""),
        data=json.dumps({
            "email": TEST_EMAIL, "password": password, "returnSecureToken": True
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            refuse("STAGING_PASSWORD_SIGN_IN_REJECTED")
        token = json.load(response).get("idToken")
    if not isinstance(token, str) or len(token) < 100:
        refuse("SIGNED_ID_TOKEN_NOT_RETURNED")
    return token


def require(value, code):
    if not value:
        refuse(code)


def execute():
    keys = check_environment()
    # Use already-provisioned, staging-scoped ADC. gcloud CLI impersonation
    # alone is not an ADC credential and cannot prove application signing access.
    import google.auth
    credentials, adc_project = google.auth.default(
        scopes=("https://www.googleapis.com/auth/cloud-platform",)
    )
    require(adc_project == PROJECT, "ADC_PROJECT_NOT_STAGING")
    require(
        getattr(credentials, "service_account_email", None) == QA_ACCOUNT,
        "ADC_MUST_BE_STAGING_QA_SERVICE_ACCOUNT",
    )
    require(sys.stdin.isatty() and sys.stderr.isatty(), "INTERACTIVE_TTY_REQUIRED")

    # Hidden interactive inputs. They never go to Github, shell history or logs.
    web_key = getpass.getpass("R14 staging Web API key (hidden): ")
    password = getpass.getpass("R14 disposable test password (hidden): ")
    require(20 <= len(web_key) <= 120 and not any(c.isspace() for c in web_key),
            "STAGING_WEB_API_KEY_INVALID")
    require(bool(password), "TEST_ACCOUNT_PASSWORD_REQUIRED")

    import firebase_admin
    from firebase_admin import auth
    old_env = {name: os.environ.get(name) for name in (
        "SBI_R8_STAGING_MODE", "SBI_R8_STAGING_FIREBASE_PROJECT_ID",
        "SBI_R8_STAGING_SITE_ORIGIN", "SBI_R8_STAGING_FIREBASE_WEB_API_KEY",
        "SBI_R8_STAGING_EVIDENCE_DIR", "SBI_READONLY_QUARANTINE_SOL_KEYS",
        "SBI_PAYMENT_EVIDENCE_DIR", "FIREBASE_WEB_API_KEY",
    )}
    try:
        with tempfile.TemporaryDirectory(prefix="sbi-r8-staging-r14-", dir="/tmp") as dirname:
            Path(dirname).chmod(0o700)
            os.environ.update({
                "SBI_R8_STAGING_MODE": "SBI_R8_STAGING_ONLY_NONFINANCIAL",
                "SBI_R8_STAGING_FIREBASE_PROJECT_ID": PROJECT,
                "SBI_R8_STAGING_SITE_ORIGIN": TEST_ORIGIN,
                "SBI_R8_STAGING_FIREBASE_WEB_API_KEY": web_key,
                "SBI_R8_STAGING_EVIDENCE_DIR": dirname,
                "SBI_READONLY_QUARANTINE_SOL_KEYS": keys,
            })
            sys.path.insert(0, str(ROOT / "staging/aws_login_v150"))
            import r8_staging_entrypoint as stage
            require(stage.project == PROJECT, "APPLICATION_PROJECT_MISMATCH")
            require(stage.app.config.get("SBI_R8_FINANCIAL_APPLY_LOCKED") is True,
                    "FINANCIAL_APPLY_NOT_LOCKED")
            fb = stage.session_config.firebase_app()
            # Firebase user lookup is read-only. User/claim creation is forbidden.
            user = auth.get_user_by_email(TEST_EMAIL, app=fb)
            require(not user.disabled, "TEST_ACCOUNT_DISABLED")
            require((user.custom_claims or {}).get("dil_dashboard") is True,
                    "TEST_ACCOUNT_DASHBOARD_CLAIM_MISSING")

            signed_token = real_login(web_key, password)
            identity = auth.verify_id_token(signed_token, check_revoked=True, app=fb)
            require(identity.get("aud") == PROJECT, "TOKEN_AUDIENCE_INVALID")
            require(identity.get("iss") == "https://securetoken.google.com/" + PROJECT,
                    "TOKEN_ISSUER_INVALID")
            require(identity.get("uid") == user.uid, "TOKEN_USER_MISMATCH")
            require(identity.get("firebase", {}).get("sign_in_provider") == "password",
                    "TOKEN_PROVIDER_INVALID")

            client = stage.app.test_client()
            csrf_response = client.get("/auth/csrf")
            require(csrf_response.status_code == 200, "CSRF_ENDPOINT_FAILED")
            csrf = csrf_response.json["csrf_token"]

            invalid_origin = client.post(
                "/auth/session", json={"idToken": signed_token},
                headers={"Origin": "https://untrusted.invalid", "X-DIL-CSRF": csrf},
            )
            require(invalid_origin.status_code == 403, "ORIGIN_NOT_DENIED")
            invalid_csrf = client.post(
                "/auth/session", json={"idToken": signed_token},
                headers={"Origin": TEST_ORIGIN, "X-DIL-CSRF": "0" * 64},
            )
            require(invalid_csrf.status_code == 403, "CSRF_NOT_DENIED")
            require(client.get("/auth/me").status_code == 401,
                    "UNAUTHENTICATED_IDENTITY_EXPOSED")

            login = client.post(
                "/auth/session", json={"idToken": signed_token},
                headers={"Origin": TEST_ORIGIN, "X-DIL-CSRF": csrf},
            )
            require(login.status_code == 200, "REAL_ID_TO_APP_SESSION_FAILED")
            cookies = login.headers.getlist("Set-Cookie")
            require(any(
                c.startswith("__Host-dil_session=")
                and all(s in c for s in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"))
                for c in cookies
            ), "PROTECTED_SESSION_COOKIE_MISSING")
            me = client.get("/auth/me")
            require(me.status_code == 200, "SIGNED_SESSION_NOT_ACCEPTED")
            require(me.json.get("administrator") is False,
                    "QA_ACCOUNT_RECEIVED_ADMIN_ROLE")
            status = client.get("/api/payment-reconciliation/status")
            require(status.status_code == 200, "AUTHENTICATED_READ_STATUS_FAILED")
            require(status.json.get("engine") == "NOT_CONNECTED",
                    "UNEXPECTED_FINANCIAL_ENGINE_CONNECTION")
            require(status.json.get("financial_database") == "NOT_CONNECTED",
                    "UNEXPECTED_FINANCIAL_DATABASE_CONNECTION")
            require(status.json.get("financial_apply_locked") is True,
                    "FINANCIAL_APPLY_UNLOCKED")
            denial = client.post(
                "/api/payment-reconciliation/run", json={},
                headers={"Origin": TEST_ORIGIN, "X-DIL-CSRF": csrf},
            )
            require(denial.status_code == 403, "FINANCIAL_RUN_NOT_DENIED")
            print("R14_REAL_ID_TO_FLASK_SESSION=PASS")
            print("R14_SESSION_COOKIE_CSRF_ORIGIN=PASS")
            print("R14_SESSION_PROTECTED_STATUS=PASS")
            print("R14_FINANCIAL_APPLY=LOCKED")
            print("R14_AWS_HTTP_DEPLOYMENT=NOT_TESTED")
            print("R14_ROLE_REVOCATION_AND_OWNER_ISOLATION=NOT_TESTED")
            print("R14_FIREBASE_USERS_AND_FINANCIAL_WRITES=NONE")
    finally:
        for name, value in old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    try:
        execute()
    except R14Refused as exc:
        print("R14_REAL_APP_SESSION=BLOCKED:" + str(exc))
        raise SystemExit(2) from None
    except Exception:
        # Deliberately do not emit exceptions: SDK errors may contain sensitive data.
        print("R14_REAL_APP_SESSION=BLOCKED:SECURE_RUNTIME_OR_PROVIDER_ERROR")
        raise SystemExit(2) from None
