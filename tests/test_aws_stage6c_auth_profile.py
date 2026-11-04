"""Stage 6C exact origin matching and AWS backend hold (offline synthetic)."""
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]/"dashboard_source"
sys.path.insert(0, str(ROOT))
from stage6_origin_policy import is_allowed_origin, private_aws_origin, CLOUD_RUN_ORIGINS

AWS = {"SBI_STAGE6_AUTH_PROFILE": "aws-private-staging",
       "SBI_STAGE6_AWS_ORIGIN": "https://sbi-stage6.13-232-241-221.sslip.io"}

class OriginTests(unittest.TestCase):
    def test_cloud_run_default_exact_compatibility(self):
        for origin in CLOUD_RUN_ORIGINS:
            self.assertTrue(is_allowed_origin(origin, {}))
        self.assertFalse(is_allowed_origin("https://evil.example", {}))
        self.assertFalse(is_allowed_origin(None, {}))
        self.assertFalse(is_allowed_origin(next(iter(CLOUD_RUN_ORIGINS))+"/", {}))

    def test_aws_private_exact_only(self):
        self.assertEqual(private_aws_origin(AWS), AWS["SBI_STAGE6_AWS_ORIGIN"])
        self.assertTrue(is_allowed_origin(AWS["SBI_STAGE6_AWS_ORIGIN"], AWS))
        self.assertFalse(is_allowed_origin("https://login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app", AWS))
        self.assertFalse(is_allowed_origin(AWS["SBI_STAGE6_AWS_ORIGIN"]+"/", AWS))

    def test_missing_malformed_or_unknown_profile_fails_closed(self):
        for value in ("", "http://sbi-stage6.13-232-241-221.sslip.io",
                      "https://*.sslip.io", "https://evil.example",
                      "https://sbi-stage6.13-232-241-221.sslip.io/path",
                      "https://user@sbi-stage6.13-232-241-221.sslip.io",
                      "https://sbi-stage6.13-232-241-221.sslip.io:8080"):
            env = {**AWS, "SBI_STAGE6_AWS_ORIGIN": value}
            self.assertIsNone(private_aws_origin(env), msg=value)
            self.assertFalse(is_allowed_origin(value, env))
        self.assertFalse(is_allowed_origin(next(iter(CLOUD_RUN_ORIGINS)),
                            {"SBI_STAGE6_AUTH_PROFILE":"unknown"}))

    def test_original_route_specific_allowlists(self):
        origin = next(iter(CLOUD_RUN_ORIGINS))
        self.assertFalse(is_allowed_origin(origin, {}, cloud_origins=set()))
        self.assertTrue(is_allowed_origin(origin, {}, cloud_origins={origin}))
        self.assertTrue(is_allowed_origin(AWS["SBI_STAGE6_AWS_ORIGIN"], AWS, cloud_origins=set()))

class GuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from flask import Flask
        from stage6_aws_guard import install_aws_private_guard
        app=Flask(__name__)
        install_aws_private_guard(app)
        @app.get("/")
        def home():
            return "static test"
        @app.get("/api/reports")
        def reports():
            return "never accessible in AWS"
        @app.get("/reports/credit-note.csv")
        def note():
            return "never accessible in AWS"
        @app.get("/auth/csrf")
        def csrf():
            return "synthetic placeholder (not actual firebase auth)"
        cls.app=app

    def test_aws_financial_routes_rejected(self):
        with patch.dict("os.environ", AWS):
            client=self.app.test_client()
            self.assertEqual(client.get("/api/reports").status_code, 503)
            self.assertEqual(client.get("/reports/credit-note.csv").status_code, 503)
            self.assertEqual(client.get("/auth/csrf").status_code, 200)

    def test_missing_origin_and_unknown_profile_fail_closed(self):
        with patch.dict("os.environ", {"SBI_STAGE6_AUTH_PROFILE":"aws-private-staging"}, clear=True):
            self.assertEqual(self.app.test_client().get("/").status_code, 503)
        with patch.dict("os.environ", {"SBI_STAGE6_AUTH_PROFILE":"typo"}, clear=True):
            self.assertEqual(self.app.test_client().get("/api/reports").status_code, 503)

    def test_default_preserves_original_route_wiring(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.app.test_client().get("/api/reports").status_code, 200)

if __name__=="__main__":
    unittest.main()
