"""
MEGHRAJ SBI RECONCILIATION CONTROL CENTER
Authentication and Login QA Suite
Version: 1.0
Mode: Local synthetic testing only

Does not perform live Firebase login or financial writes.
"""

import os
import sys
import hashlib
import unittest
from pathlib import Path
from html.parser import HTMLParser

# Synthetic client configuration, for this process only.
os.environ["FIREBASE_WEB_API_KEY"] = (
    "TEST_ONLY_NOT_A_REAL_FIREBASE_KEY"
)

ROOT = Path.cwd()
DASH = ROOT / "dashboard_source"
BACKUP = ROOT / "backups/login_ui_step84"

sys.path.insert(0, str(DASH))
sys.path.insert(0, str(ROOT / "backend_source"))
sys.path.insert(0, str(ROOT / "source"))

from production_gateway import app


class LoginParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.inputs = {}
        self.links = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)

        if values.get("id"):
            self.ids.add(values["id"])

        if tag == "input" and values.get("id"):
            self.inputs[values["id"]] = values.get("type")

        if tag == "link":
            self.links.append(values.get("href", ""))

        if tag == "script":
            self.scripts.append(values.get("src", ""))


class MeghrajCompleteAuthTests(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    # ------------------------------------------------
    # LOGIN UI
    # ------------------------------------------------

    def test_01_meghraj_branding(self):
        html = (DASH / "login.html").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "Meghraj _ SBI Reconciliation Control Center",
            html
        )

    def test_02_login_structure(self):
        html = (DASH / "login.html").read_text(
            encoding="utf-8"
        )

        parser = LoginParser()
        parser.feed(html)

        required = (
            "login-form",
            "email",
            "password",
            "sign-in",
            "toggle-password",
        )

        for element in required:
            with self.subTest(element=element):
                self.assertIn(element, parser.ids)

        self.assertEqual(
            parser.inputs.get("email"), "email"
        )
        self.assertEqual(
            parser.inputs.get("password"), "password"
        )

        self.assertIn("/login.css", parser.links)
        self.assertIn("/login.js", parser.scripts)

    def test_03_responsive_design(self):
        css = (DASH / "login.css").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "MEGHRAJ LOGIN UI V2 START", css
        )
        self.assertIn(
            "@media (max-width: 640px)", css
        )
        self.assertIn(
            "prefers-reduced-motion", css
        )

    # ------------------------------------------------
    # AUTHENTICATION SOURCE INTEGRITY
    # ------------------------------------------------

    def test_04_authentication_source_unchanged(self):
        protected = (
            "login.js",
            "cloud_auth.py",
            "dashboard_login_pages.py",
        )

        for name in protected:
            with self.subTest(file=name):
                old = BACKUP / name
                current = DASH / name

                self.assertTrue(
                    old.is_file(),
                    f"Missing backup: {old}"
                )

                self.assertTrue(
                    current.is_file(),
                    f"Missing file: {current}"
                )

                old_hash = hashlib.sha256(
                    old.read_bytes()
                ).digest()

                new_hash = hashlib.sha256(
                    current.read_bytes()
                ).digest()

                self.assertEqual(
                    old_hash, new_hash,
                    f"Protected file changed: {name}"
                )

    # ------------------------------------------------
    # LOGIN ENDPOINTS
    # ------------------------------------------------

    def test_05_login_page_available(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"login-form",
            response.data
        )

    def test_06_login_css_available(self):
        response = self.client.get("/login.css")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"MEGHRAJ LOGIN UI V2 START",
            response.data
        )

    def test_07_login_javascript_available(self):
        response = self.client.get("/login.js")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.strip())

    def test_08_firebase_config_available(self):
        response = self.client.get("/auth/config")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)

        data = response.get_json()
        self.assertIsInstance(data, dict)

    # ------------------------------------------------
    # CSRF AND UNAUTHENTICATED SESSION PROTECTION
    # ------------------------------------------------

    def test_09_csrf_bootstrap(self):
        response = self.client.get("/auth/csrf")

        self.assertEqual(response.status_code, 200)

    def test_10_anonymous_identity_rejected(self):
        response = self.client.get("/auth/me")

        self.assertIn(
            response.status_code,
            (401, 403)
        )

    def test_11_session_without_credentials(self):
        response = self.client.post("/auth/session")

        self.assertIn(
            response.status_code,
            (400, 401, 403, 422)
        )

    def test_12_invalid_token_without_csrf(self):
        response = self.client.post(
            "/auth/session",
            json={
                "idToken": "INVALID_SYNTHETIC_TOKEN"
            }
        )

        self.assertIn(
            response.status_code,
            (400, 401, 403, 422)
        )

    def test_13_logout_without_session(self):
        response = self.client.post("/auth/logout")

        self.assertIn(
            response.status_code,
            (400, 401, 403)
        )

    def test_14_unknown_config_route_not_public(self):
        response = self.client.get(
            "/api/login/config",
            follow_redirects=False
        )

        self.assertNotEqual(response.status_code, 200)

    # ------------------------------------------------
    # SESSION LIFECYCLE — VERIFIED OFFLINE FIREBASE MOCK BOUNDARY
    # All Firebase calls are intercepted. No live Firebase or financial access.
    # CSRF is obtained through the actual endpoint, never bypassed.

    def _csrf_headers(self):
        from dashboard_sessions import CSRF_COOKIE, ORIGINS
        token = self.client.get("/auth/csrf").get_json()["csrf_token"]
        self.assertEqual(
            self.client.get_cookie(CSRF_COOKIE).value, token
        )
        return {"Origin": sorted(ORIGINS)[0], "X-DIL-CSRF": token}

    def _login_mocks(self, stack):
        from unittest.mock import patch, Mock
        import time
        from dashboard_sessions import SESSION_COOKIE
        user = Mock(
            uid="synthetic-uid", email="synthetic@example.invalid",
            disabled=False, custom_claims={"dil_dashboard": True},
            display_name="Synthetic"
        )
        identity = {
            "uid": user.uid, "auth_time": time.time(),
            "firebase": {"sign_in_provider": "password"}
        }
        stack.enter_context(patch(
            "dashboard_sessions.firebase_app", return_value=object()
        ))
        verify_id = stack.enter_context(patch(
            "dashboard_sessions.auth.verify_id_token", return_value=identity
        ))
        get_user = stack.enter_context(patch(
            "dashboard_sessions.auth.get_user", return_value=user
        ))
        create = stack.enter_context(patch(
            "dashboard_sessions.auth.create_session_cookie",
            return_value="synthetic-session-cookie"
        ))
        verify_session = stack.enter_context(patch(
            "dashboard_sessions.auth.verify_session_cookie",
            return_value={"uid": user.uid}
        ))
        revoke = stack.enter_context(patch(
            "dashboard_sessions.auth.revoke_refresh_tokens"
        ))
        return user, verify_id, get_user, create, verify_session, revoke

    def test_15_valid_authenticated_login(self):
        from contextlib import ExitStack
        from dashboard_sessions import SESSION_COOKIE
        with ExitStack() as stack:
            user, verify_id, get_user, create, verify_session, revoke = (
                self._login_mocks(stack)
            )
            headers = self._csrf_headers()
            response = self.client.post(
                "/auth/session", json={"idToken": "synthetic-id-token"},
                headers=headers
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["ok"])
            self.assertEqual(
                self.client.get_cookie(SESSION_COOKIE).value,
                "synthetic-session-cookie"
            )
            verify_id.assert_called_once()
            create.assert_called_once()
            me = self.client.get("/auth/me")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.get_json()["email"], user.email)
            verify_session.assert_called_once()

    def test_16_logout_invalidates_session(self):
        from contextlib import ExitStack
        from dashboard_sessions import SESSION_COOKIE, CSRF_COOKIE
        from firebase_admin import auth
        with ExitStack() as stack:
            user, _, _, _, verify_session, revoke = self._login_mocks(stack)
            headers = self._csrf_headers()
            self.assertEqual(self.client.post(
                "/auth/session", json={"idToken": "synthetic-id-token"},
                headers=headers
            ).status_code, 200)
            response = self.client.post("/auth/logout", headers=headers)
            self.assertEqual(response.status_code, 200)
            revoke.assert_called_once()
            self.assertIsNone(self.client.get_cookie(SESSION_COOKIE))
            self.assertIsNone(self.client.get_cookie(CSRF_COOKIE))
            self.assertEqual(self.client.get("/auth/me").status_code, 401)
            # A replayed cookie must be rejected after server revocation.
            self.client.set_cookie(SESSION_COOKIE, "synthetic-session-cookie")
            verify_session.side_effect = auth.RevokedSessionCookieError(
                "synthetic revoked session"
            )
            self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_17_expired_session_rejected(self):
        from contextlib import ExitStack
        from dashboard_sessions import SESSION_COOKIE
        from firebase_admin import auth
        with ExitStack() as stack:
            _, _, _, _, verify_session, _ = self._login_mocks(stack)
            self.client.set_cookie(SESSION_COOKIE, "synthetic-expired")
            verify_session.side_effect = auth.InvalidSessionCookieError(
                "synthetic expired session"
            )
            response = self.client.get("/auth/me")
            self.assertEqual(response.status_code, 401)
            self.assertIsNone(self.client.get_cookie(SESSION_COOKIE))
            self.assertEqual(
                verify_session.call_args.kwargs["check_revoked"], True
            )

    def test_18_secure_session_cookie_flags(self):
        from contextlib import ExitStack
        from dashboard_sessions import SESSION_COOKIE, CSRF_COOKIE
        with ExitStack() as stack:
            self._login_mocks(stack)
            csrf_response = self.client.get("/auth/csrf")
            csrf_cookie = next(
                h for h in csrf_response.headers.getlist("Set-Cookie")
                if h.startswith(CSRF_COOKIE + "=")
            )
            token = csrf_response.get_json()["csrf_token"]
            from dashboard_sessions import ORIGINS
            response = self.client.post(
                "/auth/session", json={"idToken": "synthetic-id-token"},
                headers={
                    "Origin": sorted(ORIGINS)[0], "X-DIL-CSRF": token
                }
            )
            self.assertEqual(response.status_code, 200)
            session_cookie = next(
                h for h in response.headers.getlist("Set-Cookie")
                if h.startswith(SESSION_COOKIE + "=")
            )
            for cookie in (csrf_cookie, session_cookie):
                with self.subTest(cookie=cookie.split("=", 1)[0]):
                    self.assertIn("Secure", cookie)
                    self.assertIn("HttpOnly", cookie)
                    self.assertIn("SameSite=Lax", cookie)
                    self.assertIn("Path=/", cookie)


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("MEGHRAJ AUTHENTICATION QA", flush=True)
    print("MODE: LOCAL SYNTHETIC TEST", flush=True)
    print("=" * 60, flush=True)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        MeghrajCompleteAuthTests
    )

    result = unittest.TextTestRunner(
        verbosity=2
    ).run(suite)

    print("\n=== FINAL QA SUMMARY ===", flush=True)
    print("TEST METHODS:", result.testsRun)
    print("SKIPPED:", len(result.skipped))
    print("FAILURES:", len(result.failures))
    print("ERRORS:", len(result.errors))

    if result.wasSuccessful() and not result.skipped:
        print("STEP 142: ALL TESTS PASSED")
    elif result.wasSuccessful():
        print("STEP 142: AVAILABLE TESTS PASSED")
        print("RELEASE GATE: INCOMPLETE")
    else:
        print("STEP 142: FAILED")

    sys.exit(0 if result.wasSuccessful() else 1)
