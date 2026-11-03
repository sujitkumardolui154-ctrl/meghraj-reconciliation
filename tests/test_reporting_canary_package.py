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

if __name__=="__main__":
    unittest.main()
