"""Synthetic F04 transport contract tests. No Firebase, model, invoice or network I/O."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from flask import Flask, g

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dashboard_source" / "dil_chat_transport.py"
JS = ROOT / "dashboard_source" / "dil_floating_assistant.js"
GATEWAY = ROOT / "dashboard_source" / "production_gateway.py"


class InvoiceChatTransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import transport without touching real Firebase credentials.
        fake_session = types.ModuleType("dashboard_sessions")
        fake_session.csrf_valid = lambda: True
        with patch.dict(sys.modules, {"dashboard_sessions": fake_session}):
            spec = importlib.util.spec_from_file_location("synthetic_dil_transport", SOURCE)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        cls.mod = mod

    def setUp(self):
        app = Flask(__name__)
        app.testing = True
        app.register_blueprint(self.mod.dil_chat)
        self.user = SimpleNamespace(
            uid="synthetic-user", disabled=False,
            custom_claims={"dil_dashboard": True, "sbi_invoice_reader": True}
        )
        self.identity = {"uid": "synthetic-user"}

        @app.before_request
        def synthetic_session():
            g.dil_user = self.user
            g.dil_identity = self.identity

        self.client = app.test_client()

    def post(self, json=None, headers=None):
        return self.client.post("/api/dil/chat", json=json, headers=headers)

    def test_authenticated_and_entitled_has_no_data_connector(self):
        r = self.post({"question": "Compare all invoices and TDS differences"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("not connected", r.get_json()["error"])
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_missing_and_mismatched_identity_denied(self):
        for uid in ("other-user", "", None):
            with self.subTest(uid=uid):
                self.identity["uid"] = uid
                self.assertEqual(self.post({"question": "Find invoice"}).status_code, 403)

    def test_claim_revocation_disabled_and_wrong_type_denied(self):
        for claims in (
            {"dil_dashboard": True},
            {"dil_dashboard": True, "sbi_invoice_reader": "true"},
            {"dil_dashboard": False, "sbi_invoice_reader": True},
        ):
            with self.subTest(claims=claims):
                self.user.custom_claims = claims
                self.assertEqual(self.post({"question": "Find invoice"}).status_code, 403)
        self.user.custom_claims = {"dil_dashboard": True, "sbi_invoice_reader": True}
        self.user.disabled = True
        self.assertEqual(self.post({"question": "Find invoice"}).status_code, 403)

    def test_invalid_question_or_extra_parameters_rejected(self):
        for payload in (
            {}, {"question": ""}, {"question": 15},
            {"question": "x" * 2001},
            {"question": "invoice\x00"},
            {"question": "find", "uid": "someone-else"},
            {"question": "find", "admin": True},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload).status_code, 400)

    def test_csrf_denied_when_verifier_fails(self):
        with patch.object(self.mod, "csrf_valid", return_value=False):
            self.assertEqual(self.post({"question": "find invoice"}).status_code, 403)

    def test_wrong_media_type_denied(self):
        result = self.client.post("/api/dil/chat", data="question=hello",
                                  content_type="application/x-www-form-urlencoded")
        self.assertEqual(result.status_code, 415)

    def test_integration_source_has_no_direct_financial_or_model_io(self):
        src = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("requests.get(", src)
        self.assertNotIn("firestore.client(", src)
        self.assertNotIn("requests.post(", src)
        self.assertIn('return _reply("Verified read-only invoice retrieval is not connected", 503)', src)

    def test_ui_connected_only_to_same_origin_session_bound_endpoint(self):
        js = JS.read_text(encoding="utf-8")
        gw = GATEWAY.read_text(encoding="utf-8")
        self.assertIn('fetch("/auth/csrf"', js)
        self.assertIn('fetch("/api/dil/chat"', js)
        self.assertIn('"X-DIL-CSRF": tokenBody.csrf_token', js)
        self.assertIn('credentials: "same-origin"', js)
        self.assertIn("bubble.textContent = message", js)
        self.assertIn("app.register_blueprint(dil_chat)", gw)


if __name__ == "__main__":
    unittest.main()
