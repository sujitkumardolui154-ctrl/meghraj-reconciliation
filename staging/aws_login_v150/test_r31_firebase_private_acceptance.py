"""Offline DB-R31.7 contract tests; no Firebase login or PostgreSQL writes."""
from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path
import unittest
import zipfile

from payment_evidence_upload import _parse
from r31_firebase_private_incontainer_smoke import synthetic_excel

ROOT=Path(__file__).resolve().parent
HOST=(ROOT/"r31_real_firebase_qa_acceptance.py").read_text(encoding="utf-8")
REMOTE=(ROOT/"r31_firebase_private_incontainer_smoke.py").read_text(encoding="utf-8")


class GenuineAuthAcceptanceContracts(unittest.TestCase):
    def test_synthetic_excel_matches_actual_upload_parser(self):
        buffer,name=synthetic_excel()
        raw=buffer.getvalue()
        self.assertTrue(name.endswith(".xlsx"))
        self.assertTrue(zipfile.is_zipfile(BytesIO(raw)))
        details=_parse(raw)
        self.assertEqual((
            details["source_rows"],
            details["valid_rows"],
            details["review_rows"],
            details["valid_credit_total"],
        ),(2,1,1,"118.00"))
        self.assertEqual(
            details["preview"][0]["sol_id"],"001505")

    def test_real_firebase_password_remains_on_host(self):
        self.assertIn("getpass.getpass(",HOST)
        self.assertIn("identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",HOST)
        self.assertIn('"id_token": token',HOST)
        self.assertIn('"exec", "-i", "-w", "/app"',HOST)
        self.assertIn('input=payload',HOST)
        self.assertNotIn('print(password',HOST)
        self.assertNotIn('print(token',HOST)

    def test_no_public_router_or_role_migration(self):
        self.assertIn("PRIVATE_STAGE_IDENTITY_OR_NETWORK_CHANGED",HOST)
        self.assertIn("ISOLATED_QA_DB_IDENTITY_NOT_CONFIRMED",HOST)
        self.assertNotIn("docker run",HOST)
        self.assertNotIn("docker network connect",HOST)
        self.assertNotIn("Caddyfile",HOST)
        self.assertNotIn("GRANT INSERT",HOST)
        self.assertNotIn("sbi_reconciliation_main",REMOTE)

    def test_real_session_and_csrf_required(self):
        self.assertIn('client.post("/auth/session"',REMOTE)
        self.assertIn('client.get("/auth/me"',REMOTE)
        self.assertIn('client.get("/auth/csrf"',REMOTE)
        self.assertIn('X-DIL-CSRF',REMOTE)
        self.assertIn('CROSS_ORIGIN_CSRF_REJECTION',REMOTE)
        self.assertIn('REAL_FIREBASE_QA_PG_SOURCE_SYNC=PASS',REMOTE)
        self.assertIn('ALREADY_RECORDED',REMOTE)

    def test_output_rupees_and_no_auto_matching(self):
        self.assertIn('TEST_CREDIT = Decimal("118.00")',REMOTE)
        self.assertIn("RUP",REMOTE.upper())
        self.assertIn('"001505"',REMOTE)
        self.assertIn('"NOT_CALCULATED"',REMOTE)
        self.assertIn('"Credit Received (INR)"',REMOTE)
        self.assertIn('REAL_FIREBASE_INR_118_00_REPORT_PARITY=PASS',REMOTE)
        self.assertIn('PRODUCTION_FINANCIAL_WRITES=NONE_BY_QA',REMOTE)

    def test_no_secrets_printed_and_no_user_creations(self):
        self.assertNotIn('print(token',REMOTE)
        self.assertNotIn('print(id_token',REMOTE)
        self.assertNotIn('create_user(',REMOTE)
        self.assertNotIn('set_custom_user_claims(',REMOTE)
        self.assertNotIn('auth.revoke_refresh_tokens',REMOTE)
        self.assertIn('CREDENTIALS_SAVED=NO',REMOTE)


if __name__=="__main__":
    unittest.main()
