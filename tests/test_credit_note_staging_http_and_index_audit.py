"""Synthetic HTTP gateway and historical registry preflight tests (no cloud).

These tests mock the global Firebase session middleware and CSRF helper; they
do NOT certify a real Firebase login or the deployed application's permissions.
"""
import io
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, g
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard_source"))
sys.path.insert(0, str(ROOT / "backend_source"))
from sbi_cn_staging_preview import (
    create_credit_note_staging_blueprint, ROLE, FEATURE_FLAG
)
from credit_note_registry_audit import audit_historical_registry_sources


def sample_user(*, entitled=True, disabled=False, dashboard=True, uid="synthetic"):
    return SimpleNamespace(uid=uid, disabled=disabled, custom_claims={
        "dil_dashboard": dashboard, ROLE: entitled
    })


class StagingBlueprintTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.auth_user = sample_user()
        self.auth_uid = "synthetic"
        self.csrf_allowed = True
        self.fake_session = types.ModuleType("dashboard_sessions")
        self.fake_session.csrf_valid = lambda: self.csrf_allowed
        self.app = Flask("synthetic_cn_staging_test")
        self.app.config.update(TESTING=True, SECRET_KEY="SYNTHETIC_ONLY")
        self.app.extensions["dil_sessions"] = True

        @self.app.before_request
        def mock_verifier():
            # Only a synthetic mock of the existing Firebase session middleware.
            if self.auth_user is not None:
                g.dil_user = self.auth_user
                g.dil_identity = {"uid": self.auth_uid}

        def handler(filename, data):
            self.calls.append((filename, data))
            return ({
                "rows": [],
                "summary": {"source_rows": 1, "error_rows": 1},
                "registry_status": "BLOCKED",
                "release_status": "REVIEW_REQUIRED",
                "import_ready": False,
                "database_changed": False,
                "financial_writes": 0,
            }, b"Source Row,Status\r\n2,ERROR\r\n")

        self.app.register_blueprint(create_credit_note_staging_blueprint(handler))
        self.client = self.app.test_client()
        self.route = "/staging/credit-note/import-preview"

    def submit(self, *, headers=None, filename="credit.csv", data=b"Invoice No,Credit Note No,Credit Note Description\nMXP1,MXPCN1,CREDIT NOTE\n", query=""):
        hdr = {"Origin": "https://synthetic.example.invalid", "X-DIL-CN-Preview": "1"}
        if headers:
            hdr.update(headers)
        with patch.dict("os.environ", {FEATURE_FLAG: "true"}), patch.dict(
            sys.modules, {"dashboard_sessions": self.fake_session}
        ):
            return self.client.post(
                self.route + query,
                data={"file": (io.BytesIO(data), filename)},
                content_type="multipart/form-data", headers=hdr,
            )

    def test_feature_disabled_denied_before_handler(self):
        with patch.dict("os.environ", {FEATURE_FLAG: "false"}):
            response = self.client.post(self.route)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(self.calls), 0)

    def test_anonymous_denied(self):
        self.auth_user = None
        response = self.submit()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])

    def test_missing_claim_denied(self):
        self.auth_user = sample_user(entitled=False)
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(self.calls, [])

    def test_admin_not_substitute_for_explicit_role(self):
        user = sample_user(entitled=False)
        user.custom_claims["dil_admin"] = True
        self.auth_user = user
        self.assertEqual(self.submit().status_code, 403)

    def test_disabled_user_denied(self):
        self.auth_user = sample_user(disabled=True)
        self.assertEqual(self.submit().status_code, 403)

    def test_uid_mismatch_denied(self):
        self.auth_uid = "someone-else"
        self.assertEqual(self.submit().status_code, 403)

    def test_missing_session_installer_denied(self):
        self.app.extensions["dil_sessions"] = False
        self.assertEqual(self.submit().status_code, 503)
        self.assertEqual(self.calls, [])

    def test_failed_csrf_denied(self):
        self.csrf_allowed = False
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(self.calls, [])

    def test_no_preview_intent_denied(self):
        self.assertEqual(self.submit(headers={"X-DIL-CN-Preview": ""}).status_code, 403)

    def test_authorized_preview_is_still_blocked_for_write(self):
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["import_ready"], False)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(len(self.calls), 1)

    def test_error_download_after_authorization(self):
        response = self.submit(query="?format=errors")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"Source Row,Status\r\n2,ERROR\r\n")
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_invalid_extension_denied_without_handler(self):
        self.assertEqual(self.submit(filename="credit.zip").status_code, 400)
        self.assertEqual(self.calls, [])

    def test_path_traversal_filename_denied(self):
        self.assertEqual(self.submit(filename="../secrets.csv").status_code, 400)
        self.assertEqual(self.calls, [])

    def test_explicit_format_required(self):
        self.assertEqual(self.submit(query="?format=apply").status_code, 400)

    def test_get_and_apply_not_exposed(self):
        self.assertEqual(self.client.get(self.route).status_code, 405)
        self.assertEqual(self.client.post("/staging/credit-note/import-apply").status_code, 404)

    def test_unsafe_response_fails_closed(self):
        def untrusted(filename, data):
            return ({
                "release_status": "APPROVED",
                "import_ready": True,
                "database_changed": False,
            }, b"")
        self.app.view_functions["sbi_cn_staging_preview_v1.credit_note_preview"].__closure__
        # The injected handler is closed over by the route; verify the gate
        # with a fresh independent app to avoid changing the application.
        app = Flask("unsafe_cn_test")
        app.extensions["dil_sessions"] = True
        @app.before_request
        def auth_mock():
            g.dil_user = sample_user()
            g.dil_identity = {"uid": "synthetic"}
        app.register_blueprint(create_credit_note_staging_blueprint(untrusted))
        self.app = app
        self.client = app.test_client()
        self.assertEqual(self.submit().status_code, 503)


class HistoricalIndexPreflightTests(unittest.TestCase):
    def test_empty_sources_never_certified(self):
        report = audit_historical_registry_sources()
        self.assertFalse(report["can_certify"])
        self.assertIn("credit_notes:MISSING_VERIFIED_SOURCE", report["blockers"])
        self.assertFalse(report["index_backfill_performed"])
        self.assertEqual(report["financial_writes"], 0)

    def test_duplicate_invoice_and_invalid_cn_are_blockers(self):
        report = audit_historical_registry_sources(
            [{"Invoice No": "MXP1"}, {"Invoice No": "MXP1"}],
            [{"Credit Note No": "CN-NOT-MXP"}],
            [{"New Invoice Against Credit Note": "MXPNEW1"}],
        )
        self.assertEqual(report["groups"]["invoices"]["duplicate_groups"], 1)
        self.assertEqual(report["groups"]["invoices"]["duplicate_affected_rows"], 2)
        self.assertEqual(report["groups"]["credit_notes"]["invalid_non_mxp_rows"], 1)
        self.assertFalse(report["can_certify"])

    def test_all_identity_groups_never_claim_independent_approval(self):
        valid = audit_historical_registry_sources(
            [{"Invoice No": "MXP1"}],
            [{"Credit Note No": "MXPCN1"}],
            [{"New Invoice Against Credit Note": "MXPNEW1"}],
            source_proofs={
                "invoice_sha256": "a" * 64,
                "credit_note_sha256": "b" * 64,
                "replacement_sha256": "c" * 64,
            },
        )
        self.assertEqual(valid["groups"]["invoices"]["unique_valid_numbers"], 1)
        self.assertFalse(valid["certificate_created"])
        self.assertIn("INDEPENDENT_SOURCE_AUTHENTICATION_NOT_VERIFIED", valid["blockers"])

    def test_wrong_source_row_type_fails(self):
        with self.assertRaisesRegex(ValueError, "MAPPING"):
            audit_historical_registry_sources(["MXP1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
