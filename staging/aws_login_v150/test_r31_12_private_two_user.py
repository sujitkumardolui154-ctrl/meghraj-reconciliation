"""R31.12 offline security contracts. No Firebase, Docker, PostgreSQL or receipts."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
HOST = (ROOT / "r31_12_private_two_user_gate.py").read_text("utf-8")
INNER = (ROOT / "r31_12_private_two_user_incontainer.py").read_text("utf-8")


class R3112PrivateTwoUserContracts(unittest.TestCase):
    def test_sources_parse(self):
        ast.parse(HOST)
        ast.parse(INNER)

    def test_existing_second_account_required_and_no_account_mutations(self):
        self.assertIn("check_second_firebase()", HOST)
        self.assertIn("BLOCKED_NOT_DISTINCT_AND_APPROVED", HOST)
        self.assertIn("signin(key)", HOST)
        for value in ("create_user(", "set_custom_user_claims(",
                      "update_user(", "delete_user("):
            self.assertNotIn(value, HOST + INNER)

    def test_two_firebase_tokens_real_sdk_verified(self):
        self.assertIn("auth.verify_id_token(t, check_revoked=True", INNER)
        self.assertIn("auth.get_user(uid, app=sdk)", INNER)
        self.assertIn("uids[0] != MASTER_UID", INNER)
        self.assertIn("uids[1] == MASTER_UID or uids[0] == uids[1]", INNER)
        self.assertIn('get("dil_dashboard") is not True', INNER)
        self.assertIn('get("dil_admin") is True', INNER)

    def test_private_csrf_session_and_cookie_bound_to_uid(self):
        self.assertIn('client.get("/auth/csrf"', INNER)
        self.assertIn('client.post(', INNER)
        self.assertIn('"Origin": SITE_ORIGIN, "X-DIL-CSRF": csrf', INNER)
        self.assertIn("auth.verify_session_cookie(", INNER)
        self.assertIn('claims.get("uid") != expected_uid', INNER)
        self.assertIn('client.get("/api/r31-private-qa/status"', INNER)

    def test_no_financial_writes_or_test_receipt_mutations(self):
        for forbidden in ("INSERT INTO ", "UPDATE sbi.", "DELETE FROM ",
                          "ALTER TABLE ", "DROP TABLE ", "CREATE POLICY ",
                          "make_receipts(", "cleanup_receipts(",
                          "docker run", "docker build", "caddy reload"):
            self.assertNotIn(forbidden, HOST + INNER)
        self.assertIn('FINANCIAL_WRITES", "NONE_BY_TEST"', INNER)

    def test_private_host_pipes_tokens_and_never_approves_release(self):
        self.assertIn('"id_tokens": tokens', HOST)
        self.assertIn("input=payload", HOST)
        self.assertIn("stderr=subprocess.DEVNULL", HOST)
        self.assertIn("ALLOWED.fullmatch(line)", HOST)
        self.assertNotIn("print(tokens", HOST + INNER)
        self.assertNotIn("print(password", HOST + INNER)
        self.assertIn("DB_R31_12_RELEASE_STATUS=IDENTITY_QA_ONLY_PRODUCTION_BLOCKED", HOST)
        self.assertIn("return 2", HOST)
        self.assertIn('PRIVATE_QA_ROUTE=NOT_PUBLIC', HOST)


if __name__ == "__main__":
    unittest.main()
