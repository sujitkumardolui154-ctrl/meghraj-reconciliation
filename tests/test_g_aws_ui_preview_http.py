"""Request-level security regression for the nonfinancial AWS UI preview."""
import base64
import importlib
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "staging" / "railway_public"
sys.path.insert(0, str(SOURCE))

class PrivatePreviewHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = importlib.import_module("app").app
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.credentials = patch.dict(os.environ, {
            "PREVIEW_USERNAME": "ui-qa-only",
            "PREVIEW_PASSWORD": "test-private-preview-password-12345",
        })
        self.credentials.start()
        self.client = self.app.test_client()

    def tearDown(self):
        self.credentials.stop()

    def auth(self, password="test-private-preview-password-12345"):
        token = base64.b64encode(("ui-qa-only:" + password).encode()).decode()
        return {"Authorization": "Basic " + token}

    def test_anonymous_preview_page_rejected(self):
        resp = self.client.get("/ui-preview")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Basic", resp.headers.get("WWW-Authenticate", ""))

    def test_anonymous_preview_css_rejected(self):
        self.assertEqual(self.client.get("/ui-preview.css").status_code, 401)

    def test_invalid_credentials_rejected(self):
        self.assertEqual(self.client.get("/ui-preview", headers=self.auth("wrong")).status_code, 401)

    def test_authenticated_preview_page_read_only(self):
        resp = self.client.get("/ui-preview", headers=self.auth())
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Engineering workspace", resp.data)
        self.assertIn("default-src 'none'", resp.headers.get("Content-Security-Policy", ""))
        self.assertIn("no-store", resp.headers.get("Cache-Control", ""))

    def test_authenticated_css(self):
        resp = self.client.get("/ui-preview.css", headers=self.auth())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/css", resp.content_type)

    def test_preview_rejects_post(self):
        resp = self.client.post("/ui-preview", headers=self.auth(), json={})
        self.assertEqual(resp.status_code, 405)

    def test_health_state_nonfinancial(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json["financial_data_connected"], False)

if __name__ == "__main__":
    unittest.main()
