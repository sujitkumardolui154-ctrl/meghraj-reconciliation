"""Static canary isolation regression checks."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "deployment" / "reporting_staging"

class CanaryIsolationTests(unittest.TestCase):
    def test_isolated_source_rejects_finance_actions(self):
        src=(PKG/"app.py").read_text()
        self.assertNotIn("production_gateway",src)
        self.assertNotIn("invoice_import_apply",src)
        self.assertNotIn("gcloud run deploy",src)
        self.assertIn("verify_session_cookie(cookie, check_revoked=True",src)
        self.assertIn('claims.get("sbi_report_viewer") is True',src)

    def test_canary_packaging_requires_reviewed_blueprint(self):
        docker=(PKG/"Dockerfile").read_text()
        self.assertIn("USER reportuser",docker)
        self.assertIn("sbi_credit_report_auth.py",docker)
        self.assertIn("dashboard_sessions.py",docker)
        self.assertNotIn("COPY . .",docker)

    def test_only_get_health_and_protected_reports(self):
        src=(PKG/"app.py").read_text()
        self.assertIn('@app.get("/health")',src)
        self.assertNotIn("@app.post(",src)


    def test_report_routes_fail_closed_for_missing_revoked_and_wrong_roles(self):
        """Exercise the actual Flask authorization callback without cloud calls."""
        import importlib.util
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch

        sys.path.insert(0, str(ROOT / "dashboard_source"))
        sys.path.insert(0, str(PKG))
        try:
            spec = importlib.util.spec_from_file_location("sbi_private_canary_under_test", PKG / "app.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            client = module.app.test_client()
            url = "/reports/credit-note/summary"
            self.assertEqual(client.get(url).status_code, 403)
            client.set_cookie(module.SESSION_COOKIE, "synthetic-cookie")
            with patch.object(module, "firebase_app", return_value=object()), \
                 patch.object(module.auth, "verify_session_cookie", side_effect=ValueError("revoked")):
                self.assertEqual(client.get(url).status_code, 403)
            for claims, disabled, expected in [
                ({}, False, 403),
                ({"dil_dashboard": True}, False, 403),
                ({"sbi_report_viewer": True}, False, 403),
                ({"dil_dashboard": True, "sbi_report_viewer": True}, True, 403),
                ({"dil_dashboard": True, "sbi_report_viewer": True}, False, 503),
            ]:
                user = SimpleNamespace(uid="synthetic-uid", disabled=disabled, custom_claims=claims)
                with patch.object(module, "firebase_app", return_value=object()), \
                     patch.object(module.auth, "verify_session_cookie", return_value={"uid": "synthetic-uid"}) as verify, \
                     patch.object(module.auth, "get_user", return_value=user), \
                     patch("sbi_credit_report_auth._read_snapshot", side_effect=ValueError("private snapshot unavailable")):
                    self.assertEqual(client.get(url).status_code, expected)
                    self.assertTrue(verify.call_args.kwargs["check_revoked"])
        finally:
            sys.path.remove(str(PKG))
            sys.path.remove(str(ROOT / "dashboard_source"))

if __name__=="__main__":
    unittest.main()
