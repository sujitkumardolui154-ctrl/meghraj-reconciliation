"""A01 synthetic authorization tests. No sessions, cloud reads or user records."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_report_access", ROOT / "dashboard_source" / "sbi_report_access.py"
)
access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(access)


def person(*, uid="synthetic-uid", disabled=False, **claims):
    return SimpleNamespace(uid=uid, disabled=disabled, custom_claims=claims)


class ReportingAccessTests(unittest.TestCase):
    def test_explicit_report_viewer_only(self):
        user = person(dil_dashboard=True, sbi_report_viewer=True)
        identity = {"uid": "synthetic-uid"}
        self.assertTrue(access.can_view_report(user, identity))
        self.assertFalse(access.can_view_report(user, identity, change_report=True))
        user.custom_claims["sbi_reconciliation_change_viewer"] = True
        self.assertTrue(access.can_view_report(user, identity, change_report=True))

    def test_dashboard_login_or_admin_does_not_imply_report_access(self):
        identity = {"uid": "synthetic-uid"}
        for claims in (
            {}, {"dil_dashboard": True}, {"dil_admin": True},
            {"dil_admin": True, "dil_dashboard": True},
            {"sbi_report_viewer": True},
            {"dil_dashboard": True, "sbi_report_viewer": 1},
            {"dil_dashboard": True, "sbi_report_viewer": "true"},
            {"dil_dashboard": True, "sbi_reconciliation_change_viewer": True},
        ):
            with self.subTest(claims=claims):
                self.assertFalse(access.can_view_report(person(**claims), identity))

    def test_missing_disabled_or_identity_mismatch_fails_closed(self):
        valid = person(dil_dashboard=True, sbi_report_viewer=True)
        for user, identity in (
            (None, {"uid": "synthetic-uid"}),
            (valid, None),
            (valid, {}),
            (valid, {"uid": "other-uid"}),
            (valid, {"uid": 1}),
            (person(uid="", dil_dashboard=True, sbi_report_viewer=True), {"uid": ""}),
            (person(disabled=True, dil_dashboard=True, sbi_report_viewer=True), {"uid": "synthetic-uid"}),
            (SimpleNamespace(uid="synthetic-uid", disabled=False, custom_claims=None), {"uid": "synthetic-uid"}),
        ):
            with self.subTest(user=str(type(user)), identity=identity):
                self.assertFalse(access.can_view_report(user, identity))

    def test_role_gate_runs_before_backend_auth_token(self):
        """Static contract for production source, not an authenticated HTTP E2E."""
        source = (ROOT / "dashboard_source" / "production_gateway.py").read_text()
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ("forward_database_report", "reconciliation_change_gateway"):
            fn = functions[name]
            first_guard = ast.get_source_segment(source, fn.body[0])
            self.assertIn("can_view_report", first_guard)
            self.assertIn("getattr(g, \"dil_user\", None)", first_guard)
            self.assertIn("getattr(g, \"dil_identity\", None)", first_guard)
            self.assertIn("403", first_guard)
            self.assertLess(source.index("can_view_report", fn.lineno and
                source.index("def " + name)), source.index(
                "get_backend_token", source.index("def " + name)))
        self.assertIn("change_report=True", ast.get_source_segment(
            source, functions["reconciliation_change_gateway"].body[0]))
        self.assertIn("token = get_backend_token(target)", ast.get_source_segment(
            source, functions["forward_database_report"]))

    def test_no_firebase_auth_role_bypass_in_credit_note(self):
        source = (ROOT / "dashboard_source" / "production_gateway.py").read_text()
        self.assertIn("sbi_credit_report_viewer", source)
        self.assertIn("install_sessions(app)", source)
        self.assertIn("create_credit_note_blueprint(_authorize_credit_note_report)", source)


if __name__ == "__main__":
    unittest.main()
