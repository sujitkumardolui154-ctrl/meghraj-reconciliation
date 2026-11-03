import base64
import os
import unittest
from unittest.mock import patch
from app import app


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.env = patch.dict(os.environ, {
            "PREVIEW_USERNAME": "tester",
            "PREVIEW_PASSWORD": "a-very-long-test-only-password",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def auth(self):
        token = base64.b64encode(b"tester:a-very-long-test-only-password").decode()
        return {"Authorization": "Basic " + token}

    def test_login_required(self):
        self.assertEqual(self.client.get("/").status_code, 401)
        self.assertEqual(self.client.get("/api/pipeline/status").status_code, 401)
        self.assertEqual(self.client.get("/pipeline").status_code, 401)

    def test_health_non_sensitive(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["financial_data_connected"])

    def test_dashboard_html_is_auth_protected_and_read_only(self):
        r = self.client.get("/", headers=self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"All stages. One control center.", r.data)
        self.assertIn(b"Financial production restricted", r.data)
        self.assertEqual(r.headers["Cache-Control"], "private, no-store")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_pipeline_status_is_read_only_and_no_mock_agent_running(self):
        record = {
            "sources": {"qa": "available", "staging": "available",
                        "task_register": "available"},
            "financial_api_connected": False,
            "financial_production": "restricted",
            "register": {"available": True, "total": 88, "tasks": []},
        }
        with patch("app.current_pipeline", return_value=record) as status:
            r = self.client.get("/api/pipeline/status", headers=self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["register"]["total"], 88)
        self.assertFalse(r.json["financial_api_connected"])
        status.assert_called_once()

    def test_api_denied_after_login(self):
        for method, path in [("post", "/api/imports/apply"),
                             ("post", "/api/upload"), ("get", "/api/reports"),
                             ("get", "/api/reconciliation/execute")]:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, headers=self.auth())
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
