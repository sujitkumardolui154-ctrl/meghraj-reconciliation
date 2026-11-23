"""R7: Firebase Auth EMULATOR end-to-end (not production Firebase). Synthetic evidence only.

No auth mocks: sessions are issued by the local Firebase Authentication Emulator.
Refuse to run without exact, disposable local emulator configuration.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from firebase_admin import auth
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
for folder in (
    ROOT / "dashboard_source",
    ROOT / "staging/aws_login_v150",
    ROOT / "staging/railway_public",
):
    sys.path.insert(0, str(folder))

# Critical: fail closed before importing/authenticating any app SDK code.
if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST") != "127.0.0.1:9099":
    raise RuntimeError(
        "R8 refuses real Firebase: local Auth Emulator must be 127.0.0.1:9099"
    )
if os.environ.get("GCLOUD_PROJECT") != "demo-sbi-r7":
    raise RuntimeError("R8 refuses non-demo Firebase project")
if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    raise RuntimeError("R8 must never load a production Firebase service account")

import dashboard_sessions
dashboard_sessions.PROJECT = "demo-sbi-r7"

spec = importlib.util.spec_from_file_location(
    "sbi_r7_firebase_emulator_app", ROOT / "staging/aws_login_v150/app.py"
)
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)
appmod.app.testing = True


def create_synthetic_xlsx(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "PAYMENT EVIDENCE"
    sheet.append(["Description", "SOL ID", "Credit Amount"])
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def sign_in_with_password(email, password):
    endpoint = (
        "http://127.0.0.1:9099/"
        "identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=r7-demo"
    )
    payload = json.dumps({
        "email": email, "password": password, "returnSecureToken": True,
    }).encode("utf-8")
    with urlopen(Request(
        endpoint, data=payload, headers={"Content-Type": "application/json"},
        method="POST",
    ), timeout=10) as reply:
        return json.load(reply)["idToken"]


class R7FirebaseAuthEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fb = dashboard_sessions.firebase_app()
        cls.identities = {}
        suffix = uuid.uuid4().hex[:12]
        cls.password = "R7-local-only-" + uuid.uuid4().hex + "!"
        for role, enabled in (
            ("primary", True),
            ("secondary", True),
            ("unprivileged", False),
        ):
            email = f"r7-{role}-{suffix}@example.invalid"
            user = auth.create_user(
                email=email, password=cls.password, app=cls.fb
            )
            auth.set_custom_user_claims(
                user.uid, {"dil_dashboard": enabled}, app=cls.fb
            )
            cls.identities[role] = {"email": email, "uid": user.uid}

    @classmethod
    def tearDownClass(cls):
        for account in cls.identities.values():
            try:
                auth.delete_user(account["uid"], app=cls.fb)
            except Exception:
                pass

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sbi-r7-emulated-")
        self.addCleanup(self.temp.cleanup)
        old = {
            "SBI_PAYMENT_EVIDENCE_DIR": os.environ.get("SBI_PAYMENT_EVIDENCE_DIR"),
            "SBI_PRIVATE_WORKSPACE_DB": os.environ.get("SBI_PRIVATE_WORKSPACE_DB"),
            "SBI_READONLY_QUARANTINE_SOL_KEYS": os.environ.get(
                "SBI_READONLY_QUARANTINE_SOL_KEYS"
            ),
        }
        os.environ["SBI_PAYMENT_EVIDENCE_DIR"] = self.temp.name
        os.environ["SBI_PRIVATE_WORKSPACE_DB"] = ""
        os.environ["SBI_READONLY_QUARANTINE_SOL_KEYS"] = "7001,7002,7003"

        def restore():
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.addCleanup(restore)
        self.client = appmod.app.test_client()
        self.csrf = self.client.get("/auth/csrf").json["csrf_token"]

    def headers(self, token=None, origin=None):
        return {
            "Origin": origin if origin is not None else appmod.SITE_ORIGIN,
            "X-DIL-CSRF": self.csrf if token is None else token,
        }

    def login(self, role="primary", client=None, csrf=None):
        client = client or self.client
        account = self.identities[role]
        token = sign_in_with_password(account["email"], self.password)
        hdr = {
            "Origin": appmod.SITE_ORIGIN,
            "X-DIL-CSRF": csrf or self.csrf,
        }
        return client.post(
            "/auth/session", json={"idToken": token}, headers=hdr
        )

    def upload(self, rows=None, headers=None, client=None):
        rows = rows or [("SYNTHETIC R7 NOVEMBER", "07001", 5.25)]
        client = client or self.client
        return client.post(
            "/api/payment-evidence/upload",
            data={"file": (
                io.BytesIO(create_synthetic_xlsx(rows)),
                "SYNTHETIC_R7.xlsx",
            )},
            headers=self.headers() if headers is None else headers,
            content_type="multipart/form-data",
        )

    def preflight(self, receipt_id, client=None, headers=None):
        return (client or self.client).post(
            "/api/payment-reconciliation/preflight",
            json={"receipt_id": receipt_id},
            headers=self.headers() if headers is None else headers,
        )

    def test_01_emulator_login_creates_protected_session_cookie(self):
        login = self.login()
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))
        cookies = login.headers.getlist("Set-Cookie")
        session = next(
            c for c in cookies if c.startswith("__Host-dil_session=")
        )
        for required in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(required, session)
        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json["email"], self.identities["primary"]["email"])
        status = self.client.get("/api/payment-reconciliation/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["engine"], "NOT_CONNECTED")
        self.assertTrue(status.json["financial_apply_locked"])

    def test_02_unprivileged_identity_cannot_create_dashboard_session(self):
        login = self.login("unprivileged")
        self.assertEqual(login.status_code, 403)
        self.assertEqual(
            self.client.get("/api/payment-reconciliation/status").status_code,
            401,
        )

    def test_03_invalid_id_token_cannot_create_session(self):
        response = self.client.post(
            "/auth/session",
            json={"idToken": "emulator-invalid"},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_04_password_login_origin_and_csrf_are_required(self):
        account = self.identities["primary"]
        token = sign_in_with_password(account["email"], self.password)
        wrong_origin = self.client.post(
            "/auth/session", json={"idToken": token},
            headers=self.headers(origin="https://evil.invalid"),
        )
        self.assertEqual(wrong_origin.status_code, 403)
        wrong_csrf = self.client.post(
            "/auth/session", json={"idToken": token},
            headers=self.headers(token="0" * 64),
        )
        self.assertEqual(wrong_csrf.status_code, 403)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_05_actual_emulated_session_can_upload_and_read_receipt(self):
        self.assertEqual(self.login().status_code, 200)
        template = self.client.get("/api/payment-evidence/template")
        self.assertEqual(template.status_code, 200)
        upload = self.upload()
        self.assertEqual(upload.status_code, 201, upload.get_data(as_text=True))
        self.assertFalse(upload.json["financial_writes"])
        receipt = upload.json["receipt_id"]
        self.assertEqual(self.client.get(
            "/api/payment-evidence/uploads"
        ).status_code, 200)
        self.assertEqual(self.client.get(
            "/api/payment-evidence/uploads/" + receipt
        ).status_code, 200)
        preflight = self.preflight(receipt)
        self.assertEqual(preflight.status_code, 503)
        self.assertEqual(
            preflight.json["code"], "APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED"
        )
        adapter = preflight.json["read_only_adapter"]
        self.assertEqual(adapter["evidence_rows_reviewed"], 1)
        self.assertFalse(adapter["bank_origin_authenticated"])
        self.assertFalse(adapter["financial_writes"])
        self.assertEqual(
            adapter["owner_confirmed_upload_cutoff"][
                "owner_confirmed_intake_cutoff_ist"
            ], "2026-11-23T00:00:00+05:30"
        )

    def test_06_valid_session_does_not_bypass_upload_csrf(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.upload(
            headers=self.headers(token="1" * 64)
        ).status_code, 403)
        self.assertEqual(self.upload(
            headers=self.headers(origin="https://evil.invalid")
        ).status_code, 403)

    def test_07_cross_user_receipt_access_denied(self):
        self.assertEqual(self.login("primary").status_code, 200)
        receipt = self.upload().json["receipt_id"]
        secondary = appmod.app.test_client()
        other_csrf = secondary.get("/auth/csrf").json["csrf_token"]
        self.assertEqual(
            self.login("secondary", client=secondary, csrf=other_csrf).status_code,
            200,
        )
        self.assertEqual(
            secondary.get("/api/payment-evidence/uploads/" + receipt).status_code,
            404,
        )
        r = secondary.post(
            "/api/payment-reconciliation/preflight",
            json={"receipt_id": receipt},
            headers={"Origin": appmod.SITE_ORIGIN, "X-DIL-CSRF": other_csrf},
        )
        self.assertEqual(r.status_code, 404)

    def test_08_duplicate_workbook_remains_review_only(self):
        self.assertEqual(self.login().status_code, 200)
        first = self.upload()
        self.assertEqual(first.status_code, 201)
        duplicate = self.upload()
        self.assertEqual(duplicate.status_code, 409)

    def test_09_invalid_session_cookie_rejected(self):
        self.assertEqual(self.login().status_code, 200)
        self.client.set_cookie(
            "__Host-dil_session", "invalid-r7-session", secure=True
        )
        response = self.client.get("/api/payment-reconciliation/status")
        self.assertEqual(response.status_code, 401)

    def test_10_financial_post_endpoints_remain_denied(self):
        self.assertEqual(self.login().status_code, 200)
        for path in (
            "/api/payment-reconciliation/run",
            "/api/imports/apply",
        ):
            response = self.client.post(
                path, json={}, headers=self.headers()
            )
            self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get("/healthz").json["financial_execution_enabled"],
            False,
        )


    def test_11_disabled_user_is_rejected_after_session_issued(self):
        self.assertEqual(self.login("primary").status_code, 200)
        uid = self.identities["primary"]["uid"]
        try:
            auth.update_user(uid, disabled=True, app=self.fb)
            response = self.client.get("/api/payment-reconciliation/status")
            self.assertIn(
                response.status_code, (401, 403),
                "Disabled authenticated users must not retain read-only access",
            )
        finally:
            auth.update_user(uid, disabled=False, app=self.fb)

    def test_12_removed_claim_blocks_existing_session(self):
        self.assertEqual(self.login("secondary").status_code, 200)
        uid = self.identities["secondary"]["uid"]
        try:
            auth.set_custom_user_claims(
                uid, {"dil_dashboard": False}, app=self.fb,
            )
            response = self.client.get("/api/payment-reconciliation/status")
            self.assertEqual(response.status_code, 403)
        finally:
            auth.set_custom_user_claims(
                uid, {"dil_dashboard": True}, app=self.fb,
            )

    def test_13_authenticated_preflight_requires_correct_csrf(self):
        self.assertEqual(self.login().status_code, 200)
        upload = self.upload()
        self.assertEqual(upload.status_code, 201)
        receipt = upload.json["receipt_id"]
        for bad in (
            self.headers(token="0" * 64),
            self.headers(origin="https://evil.invalid"),
        ):
            result = self.preflight(receipt, headers=bad)
            self.assertEqual(result.status_code, 403)
            # Outer origin guard may return only {"error": ...}; it denies before the handler.
            self.assertIsNot(result.json.get("financial_writes"), True)


if __name__ == "__main__":
    unittest.main()
