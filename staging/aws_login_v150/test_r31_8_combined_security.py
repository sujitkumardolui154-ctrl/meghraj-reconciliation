"""DB-R31.8 offline combined-security QA contracts. Does NOT call Firebase/PG."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch, MagicMock
from flask import Flask

import r31_8_combined_security_incontainer as m

ROOT=Path(__file__).resolve().parent
HOST=(ROOT/"r31_8_combined_security.py").read_text("utf-8")
INNER=(ROOT/"r31_8_combined_security_incontainer.py").read_text("utf-8")


class DBR318SecurityOfflineTests(TestCase):
    def test_actual_firebase_middleware_rejects_fake_session_cookie(self):
        # Test real Flask protect_dashboard hook, with a synthetic Firebase
        # verifier rejection. Does not contact Firebase or require secrets.
        from app import app, SITE_ORIGIN
        from dashboard_sessions import SESSION_COOKIE
        from firebase_admin import auth
        with patch("dashboard_sessions.auth.verify_session_cookie",
                   side_effect=auth.InvalidSessionCookieError("invalid test cookie")):
            with app.test_client() as client:
                client.set_cookie(
                    SESSION_COOKIE,"not-a-firebase-session-cookie",
                    domain="sbi-preview.13-232-241-221.sslip.io",
                    secure=True,httponly=True)
                denied=client.get("/api/r31-private-qa/sol-report",
                                  base_url=SITE_ORIGIN)
        self.assertEqual(denied.status_code,401)

    def test_forged_cookie_failure_diagnostic_is_typed_not_secret_text(self):
        self.assertIn("DB_R31_8_CURRENT_CHECK=FORGED_FIREBASE_SESSION_COOKIE",INNER)
        self.assertIn("FORGED_COOKIE_EXCEPTION_",INNER)
        self.assertIn("type(exc).__name__",INNER)
        self.assertNotIn('str(exc)',INNER)

    def test_streaming_runner_emits_approved_receipts_without_batched_capture(self):
        from r31_8_combined_security import accepted_qa_line, ALLOWED_QA_KEYS
        self.assertIn("DB_R31_8_REAL_FIREBASE_SESSION",ALLOWED_QA_KEYS)
        self.assertTrue(accepted_qa_line("DB_R31_8_REAL_FIREBASE_SESSION=PASS"))
        self.assertTrue(accepted_qa_line("STOP=DB_R31_8_FORGED_SESSION_COOKIE_DENIAL"))
        self.assertTrue(accepted_qa_line(
            "DB_R31_8_RELEASE_STATUS=PRIVATE_COMBINED_SECURITY_QA_ONLY_PRODUCTION_BLOCKED"))
        self.assertFalse(accepted_qa_line("TRACEBACK_CREDENTIAL=password"))
        self.assertFalse(accepted_qa_line("DB_R31_8_POSSIBLE_TOKEN=secret-identity-token"))
        self.assertFalse(accepted_qa_line("DB_R31_8_REAL_FIREBASE_SESSION=PASS\\nSECRET"))
        self.assertFalse(accepted_qa_line("DB_R31_8_REAL_FIREBASE_SESSION=secret-token"))
        self.assertNotIn("capture_output=True",HOST)
        self.assertIn('stderr=subprocess.DEVNULL',HOST)
        self.assertIn('selectors.DefaultSelector()',HOST)
        self.assertIn('"python3","-u","-c",source',HOST)
        self.assertIn('DB_R31_8_RUNNING_WAITING_FOR_CHECK=YES',HOST)

    def test_two_report_reads_get_separate_restricted_connections(self):
        first=MagicMock()
        second=MagicMock()
        with (patch.object(m,"_connect",side_effect=[first,second]) as con,
              patch.object(m,"sol_summary",return_value=[{"raw_sol":"001505"}]) as sol,
              patch.object(m,"payment_details",return_value=[{"source_receipt_id":"a"}]) as detail):
            user=type("U",(),{"uid":"synthetic-uid"})()
            a,b=m.report_snapshot(user)
        self.assertEqual(a,[{"raw_sol":"001505"}])
        self.assertEqual(b,[{"source_receipt_id":"a"}])
        self.assertEqual(con.call_count,2)
        first.close.assert_called_once()
        second.close.assert_called_once()
        sol.assert_called_once()
        detail.assert_called_once()

    def test_foreign_receipt_is_exactly_cleaned_from_private_sqlite(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp)
            base.chmod(0o700)
            with patch.object(m,"_store",return_value=base):
                rid,uid=m.add_foreign_receipt()
                with m._connection(base) as db:
                    count=db.execute(
                        "SELECT count(*) FROM receipts WHERE id=? AND owner_uid=?",
                        (rid,uid)
                    ).fetchone()[0]
                self.assertEqual(count,1)
                m.cleanup_foreign_receipt(rid,uid)
                with m._connection(base) as db:
                    count=db.execute("SELECT count(*) FROM receipts WHERE id=?",
                                     (rid,)).fetchone()[0]
                self.assertEqual(count,0)

    def test_secure_cookie_attributes_are_required(self):
        app=Flask(__name__)
        with app.app_context():
            a=app.response_class()
            b=app.response_class()
            a.set_cookie(m.CSRF_COOKIE,"a"*64,secure=True,httponly=True,
                         samesite="Lax",path="/")
            b.set_cookie(m.SESSION_COOKIE,"b"*64,secure=True,httponly=True,
                         samesite="Lax",path="/")
            m.private_cookie_assertions(None,a,b)
            b.set_cookie(m.SESSION_COOKIE,"b"*64,secure=False,httponly=True,
                         samesite="Lax",path="/")
            # A second insecure cookie is not acceptable.
            with self.assertRaises(SystemExit):
                m.private_cookie_assertions(None,a,b)

    def test_source_contract_requires_authenticated_server_user(self):
        from r31_db_r31_owner_source_adapter import authenticated_owner
        user=type("User",(),{"uid":"synthetic-secure-owner"})()
        self.assertEqual(authenticated_owner(user),"synthetic-secure-owner")
        with self.assertRaises(ValueError):
            authenticated_owner(type("User",(),{"uid":None})())

    def test_combined_host_reuses_existing_stage_not_a_new_deploy(self):
        self.assertIn("preflight()",HOST)
        self.assertIn("obtain_firebase_test_id_token(firebase_api_key())",HOST)
        self.assertIn('"exec","-i","-w","/app"',HOST)
        self.assertIn("CADDY_PRIVATE_QA_ROUTE_DETECTED",HOST)
        self.assertNotIn("docker build",HOST)
        self.assertNotIn("docker run",HOST)
        self.assertNotIn("docker network connect",HOST)
        self.assertNotIn("Caddyfile\\n",HOST)
        self.assertNotIn("CREATE USER",HOST)
        self.assertNotIn("CREATE ROLE",HOST)
        self.assertNotIn("INSERT INTO",HOST)

    def test_combined_inner_differentiates_actual_vs_synthetic_other_owner(self):
        self.assertIn("DB_R31_8_AUTHENTICATED_FOREIGN_RECEIPT_GET_SYNC=DENIED",INNER)
        self.assertIn("SECOND_REAL_FIREBASE_OWNER=NOT_TESTED",INNER)
        self.assertIn("PRIVATE_HTTPS_EXTERNAL_E2E=NOT_TESTED_NO_PUBLIC_ROUTE",INNER)
        self.assertIn("PRODUCTION_RLS=NOT_ENABLED",INNER)
        self.assertIn("PRIVATE_COMBINED_SECURITY_QA_ONLY_PRODUCTION_BLOCKED",INNER)

    def test_forged_header_and_owner_parameter_explicit_negative(self):
        self.assertIn('"X-Owner-Uid":foreign_uid',INNER)
        self.assertIn('"/api/r31-private-qa/sol-report?owner_uid="+foreign_uid',INNER)
        self.assertIn("FORGED_OWNER_CHANGED_REPORT",INNER)
        self.assertIn("FOREIGN_RECEIPT_QA_SYNC",INNER)
        self.assertIn("FOREIGN_RECEIPT_PRIVATE_GET",INNER)
        self.assertIn("cleanup_foreign_receipt(foreign_id,foreign_uid)",INNER)

    def test_readonly_role_privileges_checked_but_production_rls_not_claimed(self):
        self.assertIn("SET TRANSACTION READ ONLY",INNER)
        self.assertIn("has_table_privilege",INNER)
        self.assertIn("relrowsecurity",INNER)
        self.assertIn("relforcerowsecurity",INNER)
        self.assertNotIn("ALTER TABLE",INNER)
        self.assertNotIn("CREATE POLICY",INNER)
        self.assertNotIn("GRANT SELECT",INNER)
        self.assertNotIn("sbi_reconciliation_main",INNER)

    def test_only_synthetic_receipt_in_qa_sqlite_no_pg_writes(self):
        self.assertIn("INSERT INTO receipts",INNER)
        self.assertIn("DELETE FROM receipts",INNER)
        self.assertNotIn("INSERT INTO sbi.",INNER)
        self.assertNotIn("UPDATE sbi.",INNER)
        self.assertNotIn("DELETE FROM sbi.",INNER)
        self.assertNotIn("auth.create_user(",INNER)
        self.assertNotIn("auth.set_custom_user_claims(",INNER)


if __name__=="__main__":
    import unittest
    unittest.main()
