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
    def test_login_required(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 401)
    def test_health_non_sensitive(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["financial_data_connected"])
    def test_api_denied_after_login(self):
        import base64
        token = base64.b64encode(b"tester:a-very-long-test-only-password").decode()
        response = self.client.post("/api/imports/apply", headers={"Authorization": "Basic "+token})
        self.assertEqual(response.status_code, 403)
if __name__ == "__main__":
    unittest.main()
