"""Stage 9 combined source-only reporting integration contracts.

No Firestore, AWS, browser sessions, financial snapshots, writes or deployments.
A green result certifies fail-closed interface/schema behavior, NOT value parity.
"""
import base64
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "backend_source"))


def module_at(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


gateway = module_at(BASE / "backend_source/aws_readonly_reporting_app.py", "sbi_stage9_gateway")
invoice = module_at(BASE / "backend_source/invoice_source_schema.py", "sbi_stage9_invoice")
credit_adapter = module_at(BASE / "backend_source/credit_note_53_adapter.py", "sbi_stage9_credit")
credit_report = module_at(BASE / "backend_source/credit_note_report.py", "sbi_stage9_credit_report")
suspense = module_at(BASE / "backend_source/suspense_report_contract.py", "sbi_stage9_suspense")
changes = module_at(BASE / "backend_source/reconciliation_changes_offline.py", "sbi_stage9_changes")
access = module_at(BASE / "dashboard_source/sbi_report_access.py", "sbi_stage9_access")
CREDS = {"SBI_AWS_REPORT_USERNAME": "synthetic-operator",
         "SBI_AWS_REPORT_PASSWORD": "synthetic-not-a-real-password-123456"}
AUTH = "Basic " + base64.b64encode(
    (CREDS["SBI_AWS_REPORT_USERNAME"] + ":" + CREDS["SBI_AWS_REPORT_PASSWORD"]).encode()
).decode()
ROUTES = ("unpaid", "ok", "balance-review", "suspense", "credit-note",
          "reconciliation-changes")


class Stage9CombinedReadOnlyContractTests(unittest.TestCase):
    def setUp(self):
        gateway.app.testing = True
        self.http = gateway.app.test_client()

    def test_all_six_report_names_are_approved_only(self):
        self.assertEqual(set(gateway.REPORTS), set(ROUTES))
        with patch.dict(os.environ, CREDS, clear=True):
            for name in ROUTES:
                with self.subTest(name=name):
                    path = "/reports/" + name + ".csv"
                    anon = self.http.get(path)
                    self.assertEqual(anon.status_code, 401)
                    authorized = self.http.get(path, headers={"Authorization": AUTH})
                    self.assertEqual(authorized.status_code, 503)
                    self.assertEqual(authorized.json["error"], "REPORT_DATA_NOT_CONNECTED")
                    self.assertFalse(authorized.json["financial_execution_enabled"])

    def test_approved_index_and_unknown_report_fail_closed(self):
        with patch.dict(os.environ, CREDS, clear=True):
            self.assertEqual(self.http.get("/reports").status_code, 401)
            self.assertEqual(self.http.get("/reports", headers={"Authorization": AUTH}).status_code, 503)
            self.assertEqual(self.http.get("/reports/unapproved.csv", headers={"Authorization": AUTH}).status_code, 404)
            self.assertEqual(self.http.get("/reports", headers={"Authorization": "Basic bogus"}).status_code, 401)
            self.assertIn("Basic", self.http.get("/reports").headers["WWW-Authenticate"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.http.get("/reports").status_code, 503)

    def test_ready_status_headers_and_financial_gates(self):
        with patch.dict(os.environ, {"SBI_SOURCE_SHA": "a" * 40}, clear=True):
            health = self.http.get("/healthz")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json["monitoring_mode"], "read_only")
            self.assertFalse(health.json["financial_data_connected"])
            self.assertFalse(health.json["financial_execution_enabled"])
            self.assertEqual(health.json["version"], "git-" + "a" * 12)
            self.assertEqual(health.headers["X-Frame-Options"], "DENY")
            self.assertEqual(health.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(health.headers["Referrer-Policy"], "no-referrer")
            self.assertIn("no-store", health.headers["Cache-Control"])
            ready = self.http.get("/readyz")
            self.assertEqual(ready.status_code, 503)
            self.assertEqual(ready.json["error"], "REPORT_DATA_NOT_CERTIFIED")

    def test_all_financial_write_and_import_routes_denied(self):
        with patch.dict(os.environ, CREDS, clear=True):
            for path in ("/api/upload", "/imports/preview", "/imports/apply",
                         "/api/finance", "/api/database-update", "/payments"):
                with self.subTest(path=path):
                    self.assertEqual(self.http.get(path).status_code, 403)
            for path, verb in (("/reports", "POST"), ("/reports", "PUT"),
                               ("/reports", "PATCH"), ("/reports", "DELETE"),
                               ("/api/upload", "POST"), ("/imports/apply", "POST")):
                with self.subTest(path=path, verb=verb):
                    self.assertEqual(self.http.open(path, method=verb).status_code, 403)

    def test_approved_invoice_credit_note_and_payment_headers(self):
        self.assertEqual(len(invoice.HEADERS_53), 53)
        self.assertEqual(len(invoice.HEADERS_35), 35)
        self.assertEqual(len(invoice.HEADERS_34), 34)
        for headers in (invoice.HEADERS_53, invoice.HEADERS_35, invoice.HEADERS_34):
            self.assertEqual(headers[6:8], ["Branch Code", "Client Name"])
        self.assertEqual(invoice.HEADERS_35[8], "Branch Code")
        self.assertEqual(len(credit_adapter.REPORT_HEADERS), 18)
        self.assertEqual(credit_adapter.REPORT_HEADERS, tuple(credit_report.HEADERS))
        for headers in (invoice.HEADERS_53, invoice.HEADERS_35):
            mapping = credit_adapter.header_mapping(headers)
            self.assertEqual(mapping["Branch Code"], 6)
            self.assertEqual(mapping["Client Name"], 7)
        _, summary = credit_adapter.project_credit_notes(invoice.HEADERS_53, [])
        self.assertFalse(summary["source_modified"])
        self.assertEqual(summary["report_columns"], 18)
        self.assertEqual(len(suspense.PAYMENT_HEADERS), 23)
        self.assertEqual(suspense.BANK_CREDIT_INDEX, 8)
        self.assertEqual(suspense.STATUS_INDEX, 12)

    def test_change_report_is_classification_only_and_conflicts_retain_review(self):
        self.assertEqual(len(changes.CSV_HEADERS), 9)
        self.assertEqual(set(changes.CATEGORIES), {
            "NEW", "UNCHANGED", "PAYMENT_ADDED", "PAYMENT_CHANGED",
            "PAYMENT_CLEARED_REVIEW", "CONFLICT",
        })
        old = [{"invoice_no": "MXP-STAGE9-SYNTHETIC", "payment_received": "0", "reconciliation_status": "REVIEW"}]
        new = old + list(old)
        _, summary = changes.make_reconciliation_change_report(old, new)
        self.assertEqual(summary["categories"]["CONFLICT"], 1)
        self.assertTrue(summary["review_required"])
        self.assertFalse(summary["approved_for_settlement"])
        self.assertFalse(summary["source_snapshot_certified"])

    def test_dashboard_access_requires_verified_identity_and_report_claims(self):
        user = SimpleNamespace(uid="synthetic", disabled=False, custom_claims={
            "dil_dashboard": True, "sbi_report_viewer": True,
            "sbi_reconciliation_change_viewer": True})
        self.assertTrue(access.can_view_report(user, {"uid": "synthetic"}))
        self.assertTrue(access.can_view_report(user, {"uid": "synthetic"}, change_report=True))
        self.assertFalse(access.can_view_report(user, None))
        self.assertFalse(access.can_view_report(user, {"uid": "different"}))
        user.disabled = True
        self.assertFalse(access.can_view_report(user, {"uid": "synthetic"}))
        user.disabled = False
        user.custom_claims.pop("sbi_reconciliation_change_viewer")
        self.assertFalse(access.can_view_report(user, {"uid": "synthetic"}, change_report=True))
        user.custom_claims.pop("sbi_report_viewer")
        self.assertFalse(access.can_view_report(user, {"uid": "synthetic"}))


if __name__ == "__main__":
    unittest.main()
