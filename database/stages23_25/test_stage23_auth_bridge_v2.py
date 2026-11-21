"""Stage 23 v2 candidate auth bridge: targeted synthetic unit tests only.

No real Firebase identity is used and passing tests do not authorize cutover.
"""
import sys
import types
import unittest
from unittest.mock import patch

from flask import Flask, g
from pg_reporting_blueprint import pg_reporting_blueprint
from sbi_pg_reporting import ReportCounts
from stage23_auth_bridge import authorize_postgres_report


class Stage23BridgeV2Tests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("stage23_v2_synthetic")
        self.app.config["SBI_PG_REPORT_AUTH_CHECK"] = authorize_postgres_report
        self.app.register_blueprint(pg_reporting_blueprint)

    @staticmethod
    def fake_policy(callback):
        m = types.ModuleType("sbi_report_access")
        m.can_view_report = callback
        return m

    def test_anonymous_route_denied(self):
        self.assertEqual(
            self.app.test_client().get("/api/reporting/v2/postgresql-summary").status_code,
            403
        )

    def test_legacy_context_names_are_not_accepted(self):
        with self.app.test_request_context():
            g.user = object()
            g.identity = {"uid": "synthetic"}
            self.assertFalse(authorize_postgres_report())

    def test_missing_or_non_dict_identity_is_denied(self):
        with self.app.test_request_context():
            g.dil_user = object()
            self.assertFalse(authorize_postgres_report())
            g.dil_identity = "synthetic"
            self.assertFalse(authorize_postgres_report())

    def test_existing_policy_approves_only_exact_true(self):
        user = object()
        def policy(candidate, identity, change_report=False):
            return candidate is user and identity.get("uid") == "synthetic" and change_report is False
        with patch.dict(sys.modules, {"sbi_report_access": self.fake_policy(policy)}):
            with self.app.test_request_context():
                g.dil_user = user
                g.dil_identity = {"uid": "synthetic"}
                self.assertTrue(authorize_postgres_report())
                g.dil_identity = {"uid": "different"}
                self.assertFalse(authorize_postgres_report())

    def test_truthy_non_boolean_policy_result_denied(self):
        with patch.dict(sys.modules, {"sbi_report_access": self.fake_policy(lambda *a, **kw: "yes")}):
            with self.app.test_request_context():
                g.dil_user = object()
                g.dil_identity = {"uid": "synthetic"}
                self.assertFalse(authorize_postgres_report())

    def test_policy_exception_denied(self):
        def invalid(*args, **kwargs):
            raise RuntimeError("synthetic")
        with patch.dict(sys.modules, {"sbi_report_access": self.fake_policy(invalid)}):
            with self.app.test_request_context():
                g.dil_user = object()
                g.dil_identity = {"uid": "synthetic"}
                self.assertFalse(authorize_postgres_report())

    def test_signed_in_route_synthetic_success(self):
        user = object()
        def policy(candidate, identity, change_report=False):
            return candidate is user and identity.get("uid") == "synthetic" and not change_report
        @self.app.before_request
        def synthetic_auth():
            g.dil_user = user
            g.dil_identity = {"uid": "synthetic"}
        with patch.dict(sys.modules, {"sbi_report_access": self.fake_policy(policy)}):
            with patch("pg_reporting_blueprint.read_report_counts", return_value=ReportCounts(0, 0)) as reader:
                response = self.app.test_client().get("/api/reporting/v2/postgresql-summary")
                self.assertEqual(response.status_code, 200)
                reader.assert_called_once_with()

    def test_route_denied_user_does_not_query_db(self):
        @self.app.before_request
        def synthetic_auth():
            g.dil_user = object()
            g.dil_identity = {"uid": "synthetic"}
        with patch.dict(sys.modules, {"sbi_report_access": self.fake_policy(lambda *args, **kwargs: False)}):
            with patch("pg_reporting_blueprint.read_report_counts") as reader:
                response = self.app.test_client().get("/api/reporting/v2/postgresql-summary")
                self.assertEqual(response.status_code, 403)
                reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
