"""Stage17 endpoint security and behavior tests using a synthetic Flask app.

Never starts or imports the real PR129 app; no financial writes.
"""
import unittest
from unittest.mock import patch

from flask import Flask
from pg_reporting_blueprint import pg_reporting_blueprint
from sbi_pg_reporting import ReportCounts


class Stage17BlueprintTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("stage17_synthetic")
        self.app.register_blueprint(pg_reporting_blueprint)
        self.client = self.app.test_client()

    def test_anonymous_deny_by_default(self):
        with patch("pg_reporting_blueprint.read_report_counts") as read:
            resp = self.client.get("/api/reporting/v2/postgresql-summary")
            self.assertEqual(resp.status_code, 403)
            read.assert_not_called()

    def test_false_or_failed_auth_deny(self):
        self.app.config["SBI_PG_REPORT_AUTH_CHECK"] = lambda: False
        resp = self.client.get("/api/reporting/v2/postgresql-summary")
        self.assertEqual(resp.status_code, 403)
        def broken():
            raise ValueError("synthetic")
        self.app.config["SBI_PG_REPORT_AUTH_CHECK"] = broken
        self.assertEqual(self.client.get("/api/reporting/v2/postgresql-summary").status_code, 403)

    def test_authorized_staging_mock_receives_report_counts(self):
        self.app.config["SBI_PG_REPORT_AUTH_CHECK"] = lambda: True
        with patch("pg_reporting_blueprint.read_report_counts", return_value=ReportCounts(0, 0)) as read:
            resp = self.client.get("/api/reporting/v2/postgresql-summary")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["invoice_report_rows"], 0)
        self.assertEqual(resp.get_json()["payment_report_rows"], 0)
        self.assertEqual(resp.get_json()["mode"], "read_only")
        read.assert_called_once_with()

    def test_database_exception_fails_closed(self):
        self.app.config["SBI_PG_REPORT_AUTH_CHECK"] = lambda: True
        with patch("pg_reporting_blueprint.read_report_counts", side_effect=RuntimeError("synthetic")):
            resp = self.client.get("/api/reporting/v2/postgresql-summary")
        self.assertEqual(resp.status_code, 503)
        self.assertNotIn("synthetic", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
