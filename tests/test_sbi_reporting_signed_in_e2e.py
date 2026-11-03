"""Synthetic E2E HTTP status matrix, no real credentials or cloud calls."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_reporting_signed_in_e2e",
    ROOT / "tools" / "sbi_reporting_signed_in_e2e.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ReportingE2ETests(unittest.TestCase):
    def test_pass_requires_anonymous_denied_and_allowed_checks(self):
        statuses = {
            ("/api/reports", None): 401,
            ("/api/reports", "denied"): 403,
            ("/api/reports/unpaid.csv", "denied"): 403,
            ("/api/reports", "allowed"): 200,
            ("/api/reports/unpaid.csv", "allowed"): 200,
        }
        r = probe.assess(lambda path, role: statuses[(path, role)])
        self.assertEqual(r["result"], "REPORTING_AUTH_E2E_PASS")
        self.assertFalse(r["change_report_e2e_checked"])
        self.assertEqual(r["firestore_writes"], 0)
        self.assertEqual(r["financial_release"], "RESTRICTED")

    def test_unavailable_backend_and_unauthorized_denials_cannot_pass(self):
        statuses = {
            ("/api/reports", None): 401,
            ("/api/reports", "denied"): 200,
            ("/api/reports/unpaid.csv", "denied"): 403,
            ("/api/reports", "allowed"): 503,
            ("/api/reports/unpaid.csv", "allowed"): 503,
        }
        r = probe.assess(lambda path, role: statuses[(path, role)])
        self.assertEqual(r["result"], "REVIEW_REQUIRED")
        self.assertEqual(r["checks"]["DENIED_REPORT_INDEX"]["status"], "FAIL")
        self.assertEqual(r["checks"]["ALLOWED_REPORT_INDEX"]["status"], "FAIL")

    def test_change_report_needs_distinct_role_and_real_receipt(self):
        with self.assertRaises(probe.ReportingE2EBlocked):
            probe.assess(lambda path, role: 200, check_change=True, receipt=None)
        receipt = "b" * 32
        statuses = {
            ("/api/reports", None): 401,
            ("/api/reports", "denied"): 403,
            ("/api/reports/unpaid.csv", "denied"): 403,
            ("/api/reports", "allowed"): 200,
            ("/api/reports/unpaid.csv", "allowed"): 200,
            ("/api/reports/reconciliation-changes?receipt=" + receipt, "denied"): 403,
            ("/api/reports/reconciliation-changes?receipt=" + receipt, "change_allowed"): 200,
        }
        r = probe.assess(lambda path, role: statuses[(path, role)],
                         check_change=True, receipt=receipt)
        self.assertEqual(r["result"], "REPORTING_AUTH_E2E_PASS")
        self.assertTrue(r["change_report_e2e_checked"])

    def test_cloud_run_only_not_public_preview(self):
        good = "https://staging---sbi-dashboard-example.asia-south1.run.app"
        self.assertEqual(probe.validate_base_url(good), good)
        for url in ("http://example.run.app", "https://host.sslip.io",
                    "https://example.com", "https://foo.run.app@malicious.example",
                    "https://foo.run.app:8080", "https://foo.run.app/api",
                    "https://foo.run.app?token=bad"):
            with self.subTest(url=url):
                with self.assertRaises(probe.ReportingE2EBlocked):
                    probe.validate_base_url(url)

    def test_cookie_files_must_be_private_and_never_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cookie"
            p.write_text("x" * 140)
            p.chmod(0o644)
            with self.assertRaises(probe.ReportingE2EBlocked):
                probe.read_cookie(p)
            p.chmod(0o600)
            self.assertEqual(probe.read_cookie(p), "x" * 140)
            p.write_text("x" * 30 + ";evil=1")
            with self.assertRaises(probe.ReportingE2EBlocked):
                probe.read_cookie(p)

    def test_does_not_call_payment_or_financial_writers(self):
        source = (ROOT / "tools" / "sbi_reporting_signed_in_e2e.py").read_text()
        for banned in ("firestore.Client(", "firebase_admin", "requests.post(",
                       ".commit(", "gcloud run deploy", "docker compose up"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
