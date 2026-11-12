"""Synthetic end-to-end tests using the REAL dashboard session middleware.

Firebase verify/get_user calls are mocked; this DOES NOT certify a live login.
No financial database client or network call is constructed.
"""
import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard_source"))
sys.path.insert(0, str(ROOT / "backend_source"))
from staging.sbi_cn_isolated_stage_app import create_app
import dashboard_sessions as sessions
from sbi_cn_staging_preview import ROLE

ORIGIN = sorted(sessions.ORIGINS)[0]
CSV = b"Invoice No,Credit Note No,Credit Note Description\nMXP1001,MXPCN1001,CREDIT NOTE @ 30/11/2024\n"


def user(claim=True, disabled=False):
    return SimpleNamespace(
        uid="synthetic-user", email="test@example.invalid",
        disabled=disabled,
        custom_claims={"dil_dashboard": True, ROLE: claim},
    )


class IsolatedStageAppTests(unittest.TestCase):
    def setUp(self):
        self.patch_env = patch.dict(
            os.environ,
            {"SBI_CN_ISOLATED_STAGE": "1",
             "SBI_CN_STAGING_PREVIEW_ENABLED": "true"},
        )
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def csrf(self):
        token = "a" * 64
        self.client.set_cookie(sessions.CSRF_COOKIE, token)
        return token

    def session(self):
        self.client.set_cookie(
            sessions.SESSION_COOKIE,
            "SYNTHETIC_COOKIE_REJECTED_BY_REAL_FIREBASE",
        )

    def post(self, *, data=CSV, csrf=True, origin=ORIGIN, claim=True):
        if csrf:
            token = self.csrf()
        else:
            token = ""
        headers = {
            "Origin": origin, "X-DIL-CN-Preview": "1",
        }
        if token:
            headers["X-DIL-CSRF"] = token
        with patch.object(sessions, "firebase_app", return_value=object()), \
             patch.object(sessions.auth, "verify_session_cookie",
                          return_value={"uid": "synthetic-user"}) as verify, \
             patch.object(sessions.auth, "get_user",
                          return_value=user(claim=claim)) as get_user:
            response = self.client.post(
                "/staging/credit-note/import-preview",
                data={"file": (io.BytesIO(data), "credit.csv")},
                content_type="multipart/form-data", headers=headers,
            )
            if self.client.get_cookie(sessions.SESSION_COOKIE):
                # In any authenticated test the REAL guard must call verify
                # with revoked-cookie checking, not just look at a fake g.user.
                if origin == ORIGIN:
                    verify.assert_called_once()
                    self.assertTrue(verify.call_args.kwargs["check_revoked"])
                    get_user.assert_called_once()
            return response

    def test_01_factory_requires_isolated_stage_profile(self):
        with patch.dict(os.environ, {"SBI_CN_ISOLATED_STAGE": ""}):
            with self.assertRaisesRegex(RuntimeError, "ISOLATED_STAGING"):
                create_app()

    def test_02_anonymous_upload_denied_by_real_session_middleware(self):
        self.assertEqual(self.post().status_code, 401)

    def test_03_missing_credit_note_role_denied(self):
        self.session()
        self.assertEqual(self.post(claim=False).status_code, 403)

    def test_04_valid_role_without_csrf_denied(self):
        self.session()
        self.assertEqual(self.post(csrf=False).status_code, 403)

    def test_05_foreign_origin_denied_before_firebase_verification(self):
        self.session()
        self.assertEqual(self.post(origin="https://invalid.example.invalid").status_code, 403)

    def test_06_authenticated_preview_denies_import_and_reports_not_connected(self):
        self.session()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["import_ready"])
        self.assertFalse(data["database_changed"])
        self.assertEqual(data["registry_status"], "BLOCKED")
        self.assertEqual(data["reason"], "STAGING_FINANCIAL_DATABASE_NOT_CONNECTED")
        self.assertEqual(data["summary"]["source_rows"], 1)
        self.assertEqual(data["rows"][0]["status"], "REVIEW_PENDING_REGISTRY")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_07_invalid_mxp_number_in_error_count(self):
        self.session()
        response = self.post(data=CSV.replace(b"MXPCN1001", b"CN1001"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["summary"]["error_flags"]["INVALID_CREDIT_NOTE_NO_NON_MXP"],
            1,
        )
        self.assertEqual(response.get_json()["rows"][0]["status"], "ERROR")

    def test_08_empty_registry_does_not_count_as_duplicate_free_certification(self):
        self.session()
        response = self.post()
        self.assertEqual(response.get_json()["summary"]["register_status"], "NOT_VERIFIED")

    def test_09_error_csv_is_authorization_protected(self):
        self.session()
        token = self.csrf()
        with patch.object(sessions, "firebase_app", return_value=object()), \
             patch.object(sessions.auth, "verify_session_cookie",
                          return_value={"uid": "synthetic-user"}), \
             patch.object(sessions.auth, "get_user",
                          return_value=user()):
            response = self.client.post(
                "/staging/credit-note/import-preview?format=errors",
                data={"file": (io.BytesIO(CSV), "credit.csv")},
                headers={"Origin": ORIGIN, "X-DIL-CN-Preview": "1",
                         "X-DIL-CSRF": token},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"REVIEW_PENDING_REGISTRY", response.data)
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_10_disabled_feature_flag_fails_closed(self):
        self.session()
        with patch.dict(os.environ, {"SBI_CN_STAGING_PREVIEW_ENABLED": "false"}):
            self.assertEqual(self.post().status_code, 503)

    def test_11_no_apply_or_financial_writer_routes(self):
        self.session()
        with patch.object(sessions, "firebase_app", return_value=object()), \
             patch.object(sessions.auth, "verify_session_cookie",
                          return_value={"uid": "synthetic-user"}), \
             patch.object(sessions.auth, "get_user",
                          return_value=user()):
            self.assertEqual(
                self.client.post("/staging/credit-note/import-apply", headers={"Origin": ORIGIN}).status_code,
                404,
            )
        routes = [rule.rule for rule in self.app.url_map.iter_rules()]
        self.assertFalse(any("apply" in route or "write" in route for route in routes))

    def test_12_session_revocation_fails_closed(self):
        self.session()
        with patch.object(sessions, "firebase_app", return_value=object()), \
             patch.object(sessions.auth, "verify_session_cookie",
                          side_effect=ValueError("revoked")) as verify:
            response = self.client.post(
                "/staging/credit-note/import-preview",
                headers={"Origin": ORIGIN},
            )
        self.assertEqual(response.status_code, 401)
        self.assertTrue(verify.call_args.kwargs["check_revoked"])

    def test_13_readonly_health_endpoint_requires_login(self):
        self.assertEqual(self.client.get("/healthz").status_code, 401)

    def test_14_source_does_not_register_in_production_gateway(self):
        source = (ROOT / "dashboard_source" / "production_gateway.py").read_text()
        self.assertNotIn("create_credit_note_staging_blueprint", source)
        self.assertNotIn("sbi_cn_isolated_stage_app", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
