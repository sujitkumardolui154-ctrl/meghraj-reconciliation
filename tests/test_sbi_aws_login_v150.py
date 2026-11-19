"""AWS original v1.5 login frontend migration: no live Firebase or financial writes."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LOGIN = ROOT / "staging/aws_login_v150"
DASH = ROOT / "dashboard_source"
sys.path.insert(0, str(DASH))
spec = importlib.util.spec_from_file_location("aws_login_v150_test", LOGIN / "app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AWSLoginV150Tests(unittest.TestCase):
    def setUp(self):
        module.app.testing = True
        self.client = module.app.test_client()

    def test_original_v150_login_page_and_assets_public(self):
        page = self.client.get("/login")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"SBI Workspace", page.data)
        self.assertIn(b"Login v1.5.0", page.data)
        self.assertEqual(self.client.get("/login.css").status_code, 200)
        self.assertEqual(self.client.get("/login.js").status_code, 200)

    def test_original_login_requires_firebase_key_without_faking_success(self):
        with patch.dict(os.environ, {"FIREBASE_WEB_API_KEY": ""}):
            result = self.client.get("/auth/config")
            self.assertEqual(result.status_code, 503)
        with patch.dict(os.environ, {"FIREBASE_WEB_API_KEY": "synthetic-public-browser-key"}):
            result = self.client.get("/auth/config")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["version"], "1.5.0")

    def test_csrf_uses_secure_host_cookie(self):
        resp = self.client.get("/auth/csrf")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("__Host-dil_csrf", resp.headers.get("Set-Cookie", ""))
        self.assertIn("Secure", resp.headers.get("Set-Cookie", ""))

    def test_dashboard_redirect_and_api_denials_when_anonymous(self):
        self.assertEqual(self.client.get("/").status_code, 303)
        self.assertEqual(self.client.get("/dashboard").status_code, 401)
        self.assertEqual(self.client.get("/api/reports").status_code, 401)
        self.assertEqual(self.client.get("/account.js").status_code, 401)
        self.assertEqual(self.client.get("/users").status_code, 401)
        self.assertEqual(self.client.post("/api/upload").status_code, 403)

    def test_untrusted_origin_cannot_create_firebase_session(self):
        response = self.client.post("/auth/session", json={"idToken": "false-token"})
        self.assertEqual(response.status_code, 403)

    def test_aws_exact_origin_allowed_without_wildcard(self):
        from dashboard_sessions import ORIGINS
        self.assertIn(module.SITE_ORIGIN, ORIGINS)
        self.assertNotIn("*", ORIGINS)

    def test_authenticated_page_from_original_ui_but_every_finance_api_403(self):
        user = SimpleNamespace(
            uid="test-only", disabled=False,
            custom_claims={"dil_dashboard": True},
            email="synthetic@example.invalid",
            display_name="Synthetic",
        )
        self.client.set_cookie("__Host-dil_session", "synthetic-session", secure=True)
        with patch("dashboard_sessions.firebase_app", return_value=None), \
             patch("dashboard_sessions.auth.verify_session_cookie", return_value={"uid": "test-only"}), \
             patch("dashboard_sessions.auth.get_user", return_value=user):
            resp = self.client.get("/dashboard")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"SBI Reconciliation", resp.data)
            self.assertEqual(self.client.get("/api/reports").status_code, 403)
            self.assertEqual(self.client.get("/api/qa").status_code, 403)
            self.assertEqual(self.client.get("/users").status_code, 403)
            self.assertEqual(self.client.get("/dashboard.js").status_code, 200)
            self.assertEqual(self.client.get("/account.js").status_code, 200)

    def test_preview_health_declares_no_financial_connection(self):
        body = self.client.get("/healthz").json
        self.assertFalse(body["financial_data_connected"])
        self.assertFalse(body["financial_execution_enabled"])
        self.assertFalse(body["imports_enabled"])

    def test_isolated_docker_only_copies_ui_and_login_code(self):
        docker = (LOGIN / "Dockerfile").read_text()
        self.assertIn("USER 10001:10001", docker)
        self.assertIn("COPY dashboard_source/login.html", docker)
        for forbidden in (
            "production_gateway.py",
            "invoice_import_store.py",
            "payment_report_rules.py",
        ):
            self.assertNotIn(forbidden, docker)

    def test_caddy_routing_keeps_pipeline_on_old_preview(self):
        caddy = (LOGIN / "Caddyfile.phase1").read_text()
        self.assertIn("reverse_proxy sbi-preview:8080", caddy)
        self.assertIn("reverse_proxy sbi-login-v150:8080", caddy)
        self.assertIn("/pipeline", caddy)
        self.assertIn("/login", caddy)
        self.assertIn("/auth/*", caddy)

    def test_rollout_requires_private_key_and_caddy_rollback(self):
        shell = (LOGIN / "deploy_aws_login_v150.sh").read_text()
        self.assertIn("BLOCKED_PRIVATE_FIREBASE_ADMIN_KEY_REQUIRED", shell)
        self.assertIn("LOGIN_ROUTE_AUTOMATIC_ROLLBACK", shell)
        self.assertIn("LEGACY_PIPELINE_LOGIN_GUARD_CHANGED", shell)
        self.assertIn("FINANCIAL_WRITES=DISABLED", shell)


if __name__ == "__main__":
    unittest.main()
