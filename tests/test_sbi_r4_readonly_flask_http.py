"""Synthetic Flask test-client HTTP QA for the R4 read-only adapter.

Firebase identities are mocked in memory; no real bank, AWS or DB writes.
"""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT/"dashboard_source", ROOT/"staging/aws_login_v150",
               ROOT/"staging/railway_public"):
    sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location(
    "sbi_r4_mock_app", ROOT/"staging/aws_login_v150/app.py"
)
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)


def evidence(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PAYMENT EVIDENCE"
    sheet.append(["Description", "SOL ID", "Credit Amount"])
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


class ReadOnlyR4FlaskTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix="sbi-r4-synthetic-")
        self.addCleanup(self.private.cleanup)
        appmod.app.testing = True
        self.client = appmod.app.test_client()
        self.client.set_cookie("__Host-dil_session", "synthetic", secure=True)
        self.client.set_cookie("__Host-dil_csrf", "a"*64, secure=True)

    def auth(self, uid="qa-owner"):
        stack = ExitStack()
        user = SimpleNamespace(
            uid=uid, email="qa@example.invalid", disabled=False,
            display_name="QA", custom_claims={"dil_dashboard": True}
        )
        stack.enter_context(patch.dict(os.environ, {
            "SBI_PAYMENT_EVIDENCE_DIR": self.private.name,
            "SBI_PRIVATE_WORKSPACE_DB": "",
            "SBI_READONLY_QUARANTINE_SOL_KEYS": "3970,6884,6928",
        }))
        stack.enter_context(patch("dashboard_sessions.firebase_app",
                                  return_value=None))
        stack.enter_context(patch(
            "dashboard_sessions.auth.verify_session_cookie",
            return_value={"uid": uid}
        ))
        stack.enter_context(patch("dashboard_sessions.auth.get_user",
                                  return_value=user))
        return stack

    def headers(self):
        return {"Origin": appmod.SITE_ORIGIN, "X-DIL-CSRF": "a"*64}

    def upload(self, rows):
        return self.client.post(
            "/api/payment-evidence/upload",
            data={"file": (io.BytesIO(evidence(rows)), "SYNTHETIC_R4.xlsx")},
            headers=self.headers(), content_type="multipart/form-data",
        )

    def preflight(self, receipt, headers=None):
        return self.client.post(
            "/api/payment-reconciliation/preflight",
            json={"receipt_id": receipt},
            headers=self.headers() if headers is None else headers,
        )

    def test_unauthenticated_status_denied(self):
        anonymous = appmod.app.test_client()
        self.assertEqual(
            anonymous.get("/api/payment-reconciliation/status").status_code,
            401,
        )

    def test_valid_evidence_still_financially_blocked(self):
        with self.auth():
            upload = self.upload([("SYNTHETIC NOV-26", "001505", 113.84)])
            self.assertEqual(upload.status_code, 201)
            response = self.preflight(upload.json["receipt_id"])
            self.assertEqual(response.status_code, 503)
            self.assertEqual(
                response.json["code"], "APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED"
            )
            self.assertEqual(
                response.json["read_only_adapter"]["evidence_rows_reviewed"],
                1,
            )
            self.assertFalse(response.json["financial_writes"])
            self.assertTrue(response.json["financial_apply_locked"])

    def test_upstream_parser_duplicate_refusal_preserved(self):
        with self.auth():
            rows = [("SYNTHETIC DUPLICATE", "001505", 1)]*2
            upload = self.upload(rows)
            self.assertEqual(upload.status_code, 201)
            response = self.preflight(upload.json["receipt_id"])
            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                response.json["code"], "PAYMENT_EVIDENCE_REVIEW_REQUIRED"
            )

    def test_case_and_zero_padding_near_duplicate_quarantined(self):
        with self.auth():
            upload = self.upload([
                ("SYNTHETIC SAME", "03970", 5.25),
                ("synthetic same", "3970", 5.25),
            ])
            self.assertEqual(upload.status_code, 201)
            response = self.preflight(upload.json["receipt_id"])
            self.assertEqual(response.status_code, 503)
            counts = response.json["read_only_adapter"]["review_hold_counts"]
            self.assertEqual(counts["BLOCKED_SOL_IDENTITY_GROUP"], 2)
            self.assertEqual(
                counts["SAME_LOOKING_UPLOAD_ROWS_NOT_BANK_DUPLICATE_PROOF"], 2
            )

    def test_owner_scoping_and_csrf(self):
        with self.auth("alpha"):
            receipt = self.upload([("SYNTHETIC", "001505", 5)]).json["receipt_id"]
            invalid = self.preflight(
                receipt, headers={"Origin": appmod.SITE_ORIGIN}
            )
            self.assertEqual(invalid.status_code, 403)
        with self.auth("beta"):
            self.assertEqual(self.preflight(receipt).status_code, 404)

    def test_bank_date_cutoff_is_upload_only(self):
        with self.auth():
            receipt = self.upload([("SYNTHETIC", "001505", 5)]).json["receipt_id"]
            response = self.preflight(receipt)
            self.assertEqual(response.status_code, 503)
            review = response.json["read_only_adapter"]
            self.assertEqual(
                review["owner_confirmed_upload_cutoff"][
                    "owner_confirmed_intake_cutoff_ist"
                ], "2026-11-23T00:00:00+05:30"
            )
            self.assertFalse(review["bank_origin_authenticated"])
            self.assertFalse(review["financial_writes"])

    def test_run_and_apply_remain_forbidden(self):
        with self.auth():
            for path in ("/api/payment-reconciliation/run", "/api/imports/apply"):
                self.assertEqual(
                    self.client.post(
                        path, json={}, headers=self.headers()
                    ).status_code, 403,
                )


if __name__ == "__main__":
    unittest.main()
