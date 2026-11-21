"""Stage23 synthetic authorization integration tests, no real Firebase account.

Only tests that existing policy API can be invoked fail-closed via Flask.g.
These tests do NOT constitute a live authenticated-user end-to-end test.
"""
import sys
import types
import unittest
from unittest.mock import patch

from flask import Flask, g
from stage23_auth_bridge import authorize_postgres_report
from pg_reporting_blueprint import pg_reporting_blueprint
from sbi_pg_reporting import ReportCounts


class Stage23AuthBridgeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("synthetic_stage23_auth")
        self.app.config["SBI_PG_REPORT_AUTH_CHECK"] = authorize_postgres_report
        self.app.register_blueprint(pg_reporting_blueprint)

    def test_default_deny(self):
        self.assertEqual(self.app.test_client().get("/api/reporting/v2/postgresql-summary").status_code, 403)

    def test_missing_identity_deny(self):
        with self.app.test_request_context("/api/reporting/v2/postgresql-summary"):
            g.user = object()
            self.assertFalse(authorize_postgres_report())

    def test_missing_user_deny(self):
        with self.app.test_request_context():
            g.identity = {"uid": "synthetic-user"}
            self.assertFalse(authorize_postgres_report())

    def test_report_policy_grants_only_exact_true(self):
        fake = types.ModuleType("sbi_report_access")
        def can_view_report(user, identity, change_report=False):
            return user is sentinel and identity.get("uid") == "synthetic-user" and change_report is False
        fake.can_view_report = can_view_report
        sentinel = object()
        with patch.dict(sys.modules, {"sbi_report_access": fake}):
            with self.app.test_request_context():
                g.user = sentinel
                g.identity = {"uid": "synthetic-user"}
                self.assertTrue(authorize_postgres_report())
                g.identity = {"uid": "wrong"}
                self.assertFalse(authorize_postgres_report())

    def test_invalid_policy_signature_deny(self):
        fake = types.ModuleType("sbi_report_access")
        def can_view_report(unverified_header):
            return True
        fake.can_view_report = can_view_report
        with patch.dict(sys.modules, {"sbi_report_access": fake}):
            with self.app.test_request_context():
                g.user = object()
                g.identity = {"uid": "synthetic-user"}
                self.assertFalse(authorize_postgres_report())

    def test_policy_exception_deny(self):
        fake = types.ModuleType("sbi_report_access")
        def can_view_report(user, identity):
            raise RuntimeError("synthetic policy exception")
        fake.can_view_report = can_view_report
        with patch.dict(sys.modules, {"sbi_report_access": fake}):
            with self.app.test_request_context():
                g.user = object()
                g.identity = {"uid": "synthetic-user"}
                self.assertFalse(authorize_postgres_report())

    def test_synthetic_flask_route_authorized_counts(self):
        fake = types.ModuleType("sbi_report_access")
        sentinel = object()
        def can_view_report(user, identity, change_report=False):
            return user is sentinel and identity.get("uid") == "synthetic-user" and change_report is False
        fake.can_view_report = can_view_report
        @self.app.before_request
        def synthetic_session():
            g.user = sentinel
            g.identity = {"uid": "synthetic-user"}
        with patch.dict(sys.modules, {"sbi_report_access": fake}), patch(
            "pg_reporting_blueprint.read_report_counts",
            return_value=ReportCounts(0,0)
        ):
            result = self.app.test_client().get("/api/reporting/v2/postgresql-summary")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["invoice_report_rows"], 0)

    def test_synthetic_flask_route_rejects_invalid_claim(self):
        fake = types.ModuleType("sbi_report_access")
        def can_view_report(user, identity, change_report=False):
            return False
        fake.can_view_report = can_view_report
        @self.app.before_request
        def synthetic_session():
            g.user = object()
            g.identity = {"uid": "synthetic-user"}
        with patch.dict(sys.modules, {"sbi_report_access": fake}), patch(
            "pg_reporting_blueprint.read_report_counts"
        ) as query:
            result = self.app.test_client().get("/api/reporting/v2/postgresql-summary")
            self.assertEqual(result.status_code, 403)
            query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
