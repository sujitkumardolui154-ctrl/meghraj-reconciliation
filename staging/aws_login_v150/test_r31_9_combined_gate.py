"""Offline R31.9 safety contracts: no Docker, Firebase or PostgreSQL."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
HOST = (ROOT/"r31_9_combined_gate.py").read_text("utf-8")
INNER = (ROOT/"r31_9_combined_incontainer.py").read_text("utf-8")


class R319SecuritySourceTests(unittest.TestCase):
    def test_python_syntax(self):
        ast.parse(HOST)
        ast.parse(INNER)

    def test_credentials_are_hidden_and_piped_not_logged(self):
        self.assertIn('getpass.getpass("Existing Firebase TEST user email (hidden): ")',HOST)
        self.assertIn('getpass.getpass("Existing Firebase TEST user password (hidden): ")',HOST)
        self.assertIn('"id_tokens": tokens',HOST)
        self.assertIn('stdin=subprocess.PIPE',HOST)
        self.assertIn('stderr=subprocess.DEVNULL',HOST)
        self.assertNotIn('print(email',HOST)
        self.assertNotIn('print(token',HOST)

    def test_no_financial_or_production_changes(self):
        for forbidden in (
            "ALTER TABLE", "CREATE POLICY", "INSERT INTO sbi.",
            "DELETE FROM sbi.", "UPDATE sbi.",
            "auth.create_user(", "auth.set_custom_user_claims(",
        ):
            self.assertNotIn(forbidden,INNER)
        for forbidden in ("docker run","docker build","docker network connect"):
            self.assertNotIn(forbidden,HOST)
        self.assertIn('SET TRANSACTION READ ONLY',INNER)

    def test_two_distinct_authenticated_users_and_cleanup(self):
        self.assertIn('if a[2] == b[2]:',INNER)
        self.assertIn('auth.verify_session_cookie(',INNER)
        self.assertIn('auth.get_user(',INNER)
        self.assertIn('foreign_get.status_code != 404',INNER)
        self.assertIn('foreign_sync.status_code != 404',INNER)
        self.assertIn('cleanup_receipts(receipts)',INNER)
        self.assertIn('NOT_TESTED_SECOND_ACCOUNT_UNAVAILABLE',INNER)

    def test_rls_not_overclaimed(self):
        self.assertIn('NOT_ENABLED_ALL_TABLES',INNER)
        self.assertIn('NOT_VERIFIED_BY_CATALOG',INNER)
        self.assertNotIn('emit("RLS_EFFECTIVE_TENANT_GUARD", "PASS")',INNER)

    def test_https_gate_fail_closed(self):
        self.assertIn('HTTPS_E2E=NOT_TESTED_NO_APPROVED_ROUTE',HOST)
        self.assertIn('COMBINED_QA_INCOMPLETE_PRODUCTION_BLOCKED',HOST)
        self.assertIn('return 2',HOST)


if __name__ == "__main__":
    unittest.main()
