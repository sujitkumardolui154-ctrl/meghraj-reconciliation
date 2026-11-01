"""Read-only CREDIT NOTE routes: synthetic Firebase/session authorization contract.

No real users, Firebase credentials, network calls, Firestore writes or invoices.
The real deployed session boundary is not certified by this test; real Cloud Run
HTTP E2E and import-ledger QA remain separate release gates.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

DASH = Path(__file__).resolve().parents[1] / "dashboard_source"
sys.path.insert(0, str(DASH))

from production_gateway import app  # noqa: E402
import dashboard_sessions  # noqa: E402
import sbi_credit_report_auth  # noqa: E402

ROUTES = (
    "/reports/credit-note/summary",
    "/reports/credit-note.csv",
    "/reports/credit-note/conflicts.csv",
    "/reports/credit-note/ui",
)
METADATA = {
    "all_invoice_rows": 14374,
    "credit_note_unique_invoices": 1009,
    "credit_note_confirmed_unique_invoices": 1004,
    "conflicting_duplicate_invoice_numbers": 5,
    "completed_import_rows": 0,
    "report_sha256": "SYNTHETIC_SHA_NOT_REAL",
}
SYNTHETIC_REPORT = b"synthetic,report\r\nno real,invoice\r\n"
SYNTHETIC_CONFLICTS = b"synthetic,conflict\r\n"


def sample_user(*, report_viewer=False, dashboard=True, disabled=False,
                uid="synthetic-user", admin=False):
    return SimpleNamespace(
        uid=uid,
        email="synthetic@example.invalid",
        disabled=disabled,
        custom_claims={
            "dil_dashboard": dashboard,
            "sbi_credit_report_viewer": report_viewer,
            "dil_admin": admin,
        },
    )


class CreditNoteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.assertTrue(app.extensions.get("dil_sessions"))
        self.assertEqual(len([r for r in app.url_map.iter_rules()
                              if r.rule == ROUTES[0]]), 1)

    def add_cookie(self):
        self.client.set_cookie(
            dashboard_sessions.SESSION_COOKIE,
            "SYNTHETIC_INVALID_IN_REAL_FIREBASE",
            domain="localhost",
        )

    def get_authenticated(self, route, user, *, identity_uid="synthetic-user",
                          snapshot=None):
        self.add_cookie()
        if snapshot is None:
            snapshot = (METADATA, SYNTHETIC_REPORT, SYNTHETIC_CONFLICTS)
        firebase_app = object()
        with patch.object(dashboard_sessions, "firebase_app",
                          return_value=firebase_app), \
             patch.object(dashboard_sessions.auth, "verify_session_cookie",
                          return_value={"uid": identity_uid}) as verifier, \
             patch.object(dashboard_sessions.auth, "get_user",
                          return_value=user) as get_user, \
             patch.object(sbi_credit_report_auth, "_read_snapshot",
                          return_value=snapshot) as reader:
            response = self.client.get(route)
            verifier.assert_called_once_with(
                "SYNTHETIC_INVALID_IN_REAL_FIREBASE",
                check_revoked=True,
                app=firebase_app,
            )
            get_user.assert_called_once_with(identity_uid, app=firebase_app)
            return response, reader

    def test_01_all_credit_paths_are_registered(self):
        for path in ROUTES:
            with self.subTest(path=path):
                rules = [r for r in app.url_map.iter_rules() if r.rule == path]
                self.assertEqual(len(rules), 1, "Missing or duplicate route")
                self.assertIn("GET", rules[0].methods)

    def test_02_anonymous_requests_denied_before_data_read(self):
        with patch.object(sbi_credit_report_auth, "_read_snapshot") as reader:
            for route in ROUTES:
                with self.subTest(route=route):
                    result = self.client.get(route, follow_redirects=False)
                    self.assertEqual(result.status_code, 401)
                    self.assertIn("no-store", result.headers["Cache-Control"])
            reader.assert_not_called()

    def test_03_dashboard_user_without_report_role_denied(self):
        for route in ROUTES:
            with self.subTest(route=route):
                response, reader = self.get_authenticated(
                    route, sample_user(report_viewer=False))
                self.assertEqual(response.status_code, 403)
                reader.assert_not_called()

    def test_04_generic_admin_claim_cannot_override_report_permission(self):
        response, reader = self.get_authenticated(
            ROUTES[0], sample_user(admin=True, report_viewer=False))
        self.assertEqual(response.status_code, 403)
        reader.assert_not_called()

    def test_05_dashboard_access_required_before_report_viewer(self):
        response, reader = self.get_authenticated(
            ROUTES[0], sample_user(report_viewer=True, dashboard=False))
        self.assertEqual(response.status_code, 403)
        reader.assert_not_called()

    def test_06_disabled_user_denied(self):
        response, reader = self.get_authenticated(
            ROUTES[0], sample_user(report_viewer=True, disabled=True))
        self.assertEqual(response.status_code, 403)
        reader.assert_not_called()

    def test_07_mismatched_authenticated_uid_denied(self):
        response, reader = self.get_authenticated(
            ROUTES[0], sample_user(report_viewer=True, uid="different-user"))
        self.assertEqual(response.status_code, 403)
        reader.assert_not_called()

    def test_08_revoked_or_expired_cookie_denied(self):
        self.add_cookie()
        for reason in ("expired", "revoked"):
            with self.subTest(reason=reason), \
                 patch.object(dashboard_sessions, "firebase_app",
                              return_value=object()), \
                 patch.object(dashboard_sessions.auth, "verify_session_cookie",
                              side_effect=ValueError(reason)) as verifier, \
                 patch.object(sbi_credit_report_auth, "_read_snapshot") as reader:
                response = self.client.get(ROUTES[0])
                self.assertEqual(response.status_code, 401)
                self.assertIn("no-store", response.headers["Cache-Control"])
                verifier.assert_called_once()
                self.assertTrue(verifier.call_args.kwargs["check_revoked"])
                reader.assert_not_called()
                # Revocation clears the simulated browser cookie; replace it
                # for the next rejection path.
                self.add_cookie()

    def test_09_explicit_report_viewer_gets_summary(self):
        result, reader = self.get_authenticated(
            ROUTES[0], sample_user(report_viewer=True))
        self.assertEqual(result.status_code, 200)
        data = result.get_json()
        self.assertEqual(data["all_invoice_rows"], 14374)
        self.assertEqual(data["conflicting_duplicate_invoice_numbers"], 5)
        self.assertEqual(data["release_status"], "REVIEW_REQUIRED")
        self.assertEqual(data["import_completeness"], "NOT_CERTIFIED")
        self.assertEqual(data["financial_execution"], "RESTRICTED")
        self.assertIn("no-store", result.headers["Cache-Control"])
        reader.assert_called_once()

    def test_10_explicit_report_viewer_gets_read_only_csvs(self):
        for route, expected in [
            (ROUTES[1], SYNTHETIC_REPORT),
            (ROUTES[2], SYNTHETIC_CONFLICTS),
        ]:
            with self.subTest(route=route):
                response, reader = self.get_authenticated(
                    route, sample_user(report_viewer=True))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, expected)
                self.assertIn("text/csv", response.content_type)
                self.assertIn("attachment", response.headers["Content-Disposition"])
                self.assertIn("no-store", response.headers["Cache-Control"])
                reader.assert_called_once()

    def test_11_explicit_report_viewer_gets_review_ui(self):
        response, reader = self.get_authenticated(
            ROUTES[3], sample_user(report_viewer=True))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"REVIEW_REQUIRED", response.data)
        self.assertIn(b"Financial execution restricted", response.data)
        self.assertIn("no-store", response.headers["Cache-Control"])
        reader.assert_called_once()

    def test_12_unavailable_private_snapshot_fails_closed(self):
        self.add_cookie()
        with patch.object(dashboard_sessions, "firebase_app",
                          return_value=object()), \
             patch.object(dashboard_sessions.auth, "verify_session_cookie",
                          return_value={"uid": "synthetic-user"}), \
             patch.object(dashboard_sessions.auth, "get_user",
                          return_value=sample_user(report_viewer=True)), \
             patch.object(sbi_credit_report_auth, "_read_snapshot",
                          side_effect=ValueError("No private snapshot configured")):
            result = self.client.get(ROUTES[0])
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("No private snapshot configured", result.data.decode())

    def test_13_other_dashboard_endpoints_still_need_login(self):
        self.assertEqual(self.client.get("/api/reports").status_code, 401)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
