import os
import time
import inspect
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault(
    "FIREBASE_WEB_API_KEY",
    "TEST_ONLY_NOT_A_REAL_FIREBASE_KEY"
)

from production_gateway import app
from firebase_admin import auth
import dashboard_sessions as ds

print("=== STEP 217: AUTHORIZED SYNTHETIC LOGIN ===")

scope = inspect.getclosurevars(ds.csrf_valid)
origins = scope.globals.get(
    "ORIGINS", scope.nonlocals.get("ORIGINS", ())
)

if isinstance(origins, str):
    origins = [origins]

origin = next(
    (o.rstrip("/") for o in origins
     if isinstance(o, str) and o.startswith("https://")),
    None
)

if not origin:
    raise SystemExit("BLOCKED: Approved HTTPS origin unavailable")

client = app.test_client()
csrf = client.get("/auth/csrf", base_url=origin)
token = (csrf.get_json(silent=True) or {}).get("csrf_token")

if not isinstance(token, str) or len(token) != 64:
    raise SystemExit("BLOCKED: Invalid CSRF bootstrap")

identity = {
    "uid": "qa-synthetic-user",
    "email": "qa@example.invalid",
    "email_verified": True,
    "auth_time": int(time.time()),
    "firebase": {
        "sign_in_provider": "password"
    }
}

user = SimpleNamespace(
    uid="qa-synthetic-user",
    email="qa@example.invalid",
    disabled=False,
    custom_claims={"dil_dashboard": True}
)

with (
    patch.object(
        auth, "verify_id_token",
        return_value=identity
    ) as verification,
    patch.object(
        auth, "get_user",
        return_value=user
    ) as user_lookup,
    patch.object(
        auth, "create_session_cookie",
        return_value="QA_SYNTHETIC_SESSION_COOKIE"
    ) as session_creation
):
    response = client.post(
        "/auth/session",
        base_url=origin,
        json={"idToken": "QA_SYNTHETIC_ID_TOKEN"},
        headers={
            "Origin": origin,
            "X-DIL-CSRF": token
        }
    )

    cookie_headers = response.headers.getlist("Set-Cookie")
    session_cookies = [
        c for c in cookie_headers
        if "QA_SYNTHETIC_SESSION_COOKIE" in c
    ]

    print("LOGIN HTTP:", response.status_code)
    print("TOKEN VERIFICATION:", verification.called)
    print("USER LOOKUP:", user_lookup.called)
    print("SESSION CREATION:", session_creation.called)
    print("SESSION COOKIE PRESENT:", bool(session_cookies))
    print(
        "SECURE:",
        bool(session_cookies) and all(
            "Secure" in c for c in session_cookies
        )
    )
    print(
        "HTTPONLY:",
        bool(session_cookies) and all(
            "HttpOnly" in c for c in session_cookies
        )
    )
    print(
        "SAMESITE LAX:",
        bool(session_cookies) and all(
            "SameSite=Lax" in c for c in session_cookies
        )
    )

    passed = (
        response.status_code == 200
        and verification.called
        and user_lookup.called
        and session_creation.called
        and bool(session_cookies)
        and all(
            "Secure" in c
            and "HttpOnly" in c
            and "SameSite=Lax" in c
            for c in session_cookies
        )
    )

    print("STEP 217:", "PASS" if passed else "BLOCKED")

    if not passed:
        raise SystemExit(1)
