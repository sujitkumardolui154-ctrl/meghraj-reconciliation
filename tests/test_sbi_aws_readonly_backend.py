"""Synthetic tests only. No AWS, finance database, credentials or deployment."""
import base64
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend_source/aws_readonly_reporting_app.py"
spec = importlib.util.spec_from_file_location("aws_readonly_reporting_app", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
LOGIN = {"SBI_AWS_REPORT_USERNAME": "synthetic",
         "SBI_AWS_REPORT_PASSWORD": "synthetic-not-a-real-secret-long-pass"}
BASIC = "Basic " + base64.b64encode(
    (LOGIN["SBI_AWS_REPORT_USERNAME"] + ":" + LOGIN["SBI_AWS_REPORT_PASSWORD"]).encode()
).decode()


class AWSReadonlyTests(unittest.TestCase):
    def setUp(self):
        module.app.testing = True
        self.client = module.app.test_client()

    def test_health_and_business_readiness_are_distinct(self):
        with patch.dict(os.environ, {"SBI_SOURCE_SHA": "a" * 40}, clear=True):
            r = self.client.get("/healthz")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json["financial_data_connected"])
            self.assertFalse(r.json["financial_execution_enabled"])
            self.assertEqual(r.json["version"], "git-" + "a" * 12)
            self.assertEqual(self.client.get("/readyz").status_code, 503)

    def test_report_login_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.client.get("/reports").status_code, 503)
        with patch.dict(os.environ, LOGIN, clear=True):
            self.assertEqual(self.client.get("/reports").status_code, 401)
            self.assertIn("Basic", self.client.get("/reports").headers["WWW-Authenticate"])
            self.assertEqual(self.client.get("/reports", headers={"Authorization": "Basic bogus"}).status_code, 401)

    def test_all_approved_reports_still_unavailable(self):
        with patch.dict(os.environ, LOGIN, clear=True):
            self.assertEqual(self.client.get("/reports", headers={"Authorization": BASIC}).status_code, 503)
            for name in module.REPORTS:
                with self.subTest(name=name):
                    r = self.client.get("/reports/" + name + ".csv", headers={"Authorization": BASIC})
                    self.assertEqual(r.status_code, 503)
                    self.assertEqual(r.json["error"], "REPORT_DATA_NOT_CONNECTED")
            self.assertEqual(self.client.get("/reports/unknown.csv", headers={"Authorization": BASIC}).status_code, 404)

    def test_no_upload_import_or_write_method(self):
        with patch.dict(os.environ, LOGIN, clear=True):
            for route in ("/upload", "/api/upload", "/imports/preview", "/payments",
                          "/change-reports", "/supervisor", "/api/finance"):
                with self.subTest(route=route):
                    self.assertEqual(self.client.get(route, headers={"Authorization": BASIC}).status_code, 403)
            for verb in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                with self.subTest(verb=verb):
                    self.assertEqual(self.client.open("/reports", method=verb, headers={"Authorization": BASIC}).status_code, 403)

    def test_no_secret_disclosure_and_secure_headers(self):
        with patch.dict(os.environ, LOGIN, clear=True):
            r = self.client.get("/healthz")
            self.assertNotIn(LOGIN["SBI_AWS_REPORT_PASSWORD"], r.get_data(as_text=True) + str(r.headers))
            self.assertIn("no-store", r.headers["Cache-Control"])
            self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_docker_and_compose_isolate_from_existing_live_preview(self):
        d = (ROOT / "staging/aws_backend_readonly/Dockerfile").read_text()
        c = (ROOT / "staging/aws_backend_readonly/compose.yaml").read_text()
        a = SOURCE.read_text()
        self.assertIn("USER 10001:10001", d)
        self.assertIn("COPY backend_source/aws_readonly_reporting_app.py /app/app.py", d)
        self.assertNotIn("COPY backend_source/ /app", d)
        self.assertIn("127.0.0.1:18086:8080", c)
        self.assertIn("read_only: true", c)
        self.assertIn("internal: true", c)
        self.assertIn('profiles: ["manual-review-only"]', c)
        self.assertIn("cap_drop: [ALL]", c)
        self.assertNotIn("volumes:", c)
        for forbidden in ("firebase_admin", "google.cloud.firestore", "set_custom_user_claims",
                          "subprocess.run", "payment_allocation"):
            self.assertNotIn(forbidden, a)

    def test_ci_cannot_deploy(self):
        c = (ROOT / ".github/workflows/sbi-aws-backend-readonly-qa.yml").read_text()
        self.assertIn("pull_request:", c)
        self.assertIn("contents: read", c)
        for forbidden in ("aws-actions/configure-aws-credentials", "gcloud run deploy",
                          "docker compose up", "ssh ", "deploy:"):
            self.assertNotIn(forbidden, c)


if __name__ == "__main__":
    unittest.main()
