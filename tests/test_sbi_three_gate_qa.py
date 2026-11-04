"""Synthetic-only test suite for the fail-closed three-gate automation."""
import importlib.util
import os
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("three_gate", ROOT / "tools/sbi_three_gate_qa.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class ThreeGateAutomationTests(TestCase):
    def test_offline_never_certs_live_checks(self):
        with patch.object(gate, "offline_tests", return_value={"synthetic": "PASS"}):
            data, success = gate.run("offline")
        self.assertTrue(success)
        self.assertEqual(data["firebase_real_login"], "NOT_TESTED")
        self.assertEqual(data["live_original_53_parity"], "NOT_VERIFIED")
        self.assertEqual(data["reconciliation_bank_payment_parity"], "NOT_VERIFIED")
        self.assertEqual(data["production_cutover"], "BLOCKED")
        self.assertEqual(data["financial_writes"], 0)

    def test_offline_failure(self):
        with patch.object(gate, "offline_tests", return_value={"synthetic": "FAIL"}):
            data, success = gate.run("offline")
        self.assertFalse(success)
        self.assertEqual(data["status"], "OFFLINE_TESTS_FAILED")

    def test_live_requires_private_approval(self):
        with patch.dict(os.environ, {"SBI_PRIVATE_QA_APPROVED": ""}):
            data, success = gate.run("private-live")
        self.assertFalse(success)
        self.assertEqual(data["status"], "BLOCKED_PRIVATE_APPROVAL_REQUIRED")

    def test_unapproved_host_does_not_receive_password(self):
        env = {"SBI_QA_FIREBASE_API_KEY": "synthetic",
               "SBI_QA_FIREBASE_EMAIL": "qa@example.invalid",
               "SBI_QA_FIREBASE_PASSWORD": "synthetic",
               "SBI_QA_DASHBOARD_URL": "https://attacker.run.app",
               "SBI_QA_TEST_ACCOUNT_ISOLATED": "true"}
        with patch.dict(os.environ, env), patch.object(gate, "req_json") as remote:
            with self.assertRaisesRegex(gate.Blocked, "UNAPPROVED_DASHBOARD_HOST"):
                gate.real_auth()
            remote.assert_not_called()

    def test_primary_account_denied(self):
        env = {"SBI_QA_FIREBASE_API_KEY": "synthetic",
               "SBI_QA_FIREBASE_EMAIL": "sujitkumardolui154@gmail.com",
               "SBI_QA_FIREBASE_PASSWORD": "synthetic",
               "SBI_QA_DASHBOARD_URL": "https://sbi-dashboard-109590290120.asia-south1.run.app",
               "SBI_QA_TEST_ACCOUNT_ISOLATED": "true"}
        with patch.dict(os.environ, env), patch.object(gate, "req_json") as remote:
            with self.assertRaisesRegex(gate.Blocked, "UNSAFE_QA_IDENTITY"):
                gate.real_auth()
            remote.assert_not_called()

    def test_private_passes_do_not_approve_financial_release(self):
        with patch.dict(os.environ, {"SBI_PRIVATE_QA_APPROVED": "true"}), \
                patch.object(gate, "real_auth", return_value={
                    "firebase_real_login": "PASS", "dashboard_real_session": "PASS"}), \
                patch.object(gate, "approved_source", return_value=("a"*64, [[""]*53])), \
                patch.object(gate, "live_db", return_value={"live_original_53_parity": "PASS"}), \
                patch.object(gate, "report_values", return_value={
                    "financial_report_values": "SOURCE_REPORT_PARTITION_PASS",
                    "reconciliation_bank_payment_parity": "NOT_VERIFIED"}):
            data, success = gate.run("private-live")
        self.assertFalse(success)
        self.assertEqual(data["reconciliation_bank_payment_parity"], "NOT_VERIFIED")
        self.assertEqual(data["production_cutover"], "BLOCKED")

if __name__ == "__main__":
    main()
