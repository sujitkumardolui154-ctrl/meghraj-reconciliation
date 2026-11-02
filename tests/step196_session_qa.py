import os
import inspect
from unittest.mock import patch

os.environ.setdefault(
    "FIREBASE_WEB_API_KEY",
    "TEST_ONLY_NOT_A_REAL_FIREBASE_KEY"
)

from production_gateway import app
from firebase_admin import auth
import dashboard_sessions as ds

print("=== STEP 196: SYNTHETIC SESSION QA ===")

scope = inspect.getclosurevars(ds.csrf_valid)
origins = scope.globals.get(
    "ORIGINS",
    scope.nonlocals.get("ORIGINS", ())
)

if isinstance(origins, str):
    origins = [origins]

origin = next(
    (o.rstrip("/") for o in origins
     if isinstance(o, str) and o.startswith("https://")),
    None
)

if not origin:
    raise SystemExit("BLOCKED: No approved HTTPS Origin")

client = app.test_client()

csrf = client.get("/auth/csrf", base_url=origin)
body = csrf.get_json(silent=True) or {}
token = body.get("csrf_token")

if not isinstance(token, str) or len(token) != 64:
    raise SystemExit("BLOCKED: CSRF bootstrap failed")

headers = {
    "Origin": origin,
    "X-DIL-CSRF": token
}

mock_identity = {
    "uid": "qa-synthetic-user",
    "email": "qa@example.invalid",
    "email_verified": True
}

with (
    patch.object(
        auth, "verify_id_token",
        return_value=mock_identity
    ) as verify_mock,
    patch.object(
        auth, "create_session_cookie",
        return_value="QA_SYNTHETIC_SESSION_COOKIE"
    ) as cookie_mock
):
    response = client.post(
        "/auth/session",
        base_url=origin,
        json={"idToken": "QA_SYNTHETIC_TOKEN"},
        headers=headers
    )

    print("LOGIN HTTP:", response.status_code)
    print("FIREBASE VERIFIED:", verify_mock.called)
    print("SESSION COOKIE API CALLED:", cookie_mock.called)

    cookies = response.headers.getlist("Set-Cookie")

    print("COOKIE HEADER COUNT:", len(cookies))
    print(
        "SECURE FLAG:",
        any("Secure" in c for c in cookies)
    )
    print(
        "HTTPONLY FLAG:",
        any("HttpOnly" in c for c in cookies)
    )
    print(
        "SAMESITE LAX:",
        any("SameSite=Lax" in c for c in cookies)
    )

    if response.status_code == 200 and cookie_mock.called:
        print("TEST 15: PASS — MOCKED LOGIN")
    else:
        print("TEST 15: BLOCKED — LOGIN CONTRACT REVIEW")

print("STEP 196 COMPLETE")
