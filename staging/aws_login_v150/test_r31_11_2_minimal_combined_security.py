"""Minimal R31.11.2 combined QA: offline tests, never contact AWS."""
from __future__ import annotations
import ast
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import r31_11_2_minimal_combined_security as gate

SOURCE=(Path(__file__).resolve().parent/
        "r31_11_2_minimal_combined_security.py").read_text("utf-8")

class MinimalCombinedSecurityTests(unittest.TestCase):
    def test_code_compiles_and_is_only_readonly(self):
        ast.parse(SOURCE)
        for dangerous in (
            '"createdb"', '"pg_dump"', '"pg_restore"',
            '"INSERT INTO"', '"UPDATE sbi."', '"DELETE FROM"',
            '"docker","run"', '"docker","build"', 'set_custom_user_claims',
            'auth.create_user', 'caddy reload', 'SBI_R31_PRIVATE_STAGING_ENABLED=',
        ):
            self.assertNotIn(dangerous,SOURCE)
        self.assertIn("clone_readonly_main()",SOURCE)
        self.assertIn("QUARANTINED_R3112",SOURCE)

    def test_one_protected_anonymous_request_is_denied(self):
        self.assertIn("api/r31-private-qa/sol-report",gate.APP_ANONYMOUS_PROBE)
        self.assertIn("status==401",gate.APP_ANONYMOUS_PROBE)
        with patch.object(gate,"docker",return_value=
                          "DB_R31_11_2_ANONYMOUS_SOURCE_READ=PASS_DENIED_401"):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertTrue(gate.anonymous_guard())
        self.assertIn("PASS_DENIED_401",out.getvalue())

    def test_unsafe_anonymous_route_fails(self):
        with patch.object(gate,"docker",return_value=
                          "DB_R31_11_2_ANONYMOUS_SOURCE_READ=FAIL_NOT_DENIED_AS_EXPECTED"):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertFalse(gate.anonymous_guard())
        self.assertIn("STOP=",out.getvalue())

    def test_caddy_guard_refuses_qa_routes(self):
        for config in (
            "reverse_proxy sbi-r31-auth-private-qa:8080",
            "reverse_proxy sbi-r31-auth-qa:8080",
        ):
            with patch.object(gate,"docker",return_value=config):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertFalse(gate.caddy_route_guard())
                self.assertIn("STOP=",out.getvalue())
        with patch.object(gate,"docker",return_value="example.com {respond 200}"):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(gate.caddy_route_guard())

    def test_verified_clone_and_anonymous_pass_still_block_production(self):
        with (patch.object(gate,"clone_readonly_main",return_value=0),
              patch.object(gate,"anonymous_guard",return_value=True),
              patch.object(gate,"caddy_route_guard",return_value=True)):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(gate.main(),2)
        s=out.getvalue()
        self.assertIn("TWO_FIREBASE_USERS=PENDING",s)
        self.assertIn("HTTPS_E2E=PENDING",s)
        self.assertIn("RUNTIME_TENANT_RLS=NOT_CONNECTED",s)
        self.assertIn("PRODUCTION_FINANCIAL_WRITES=NONE_BY_TEST",s)
        self.assertIn("PRODUCTION_BLOCKED",s)

    def test_failed_clone_cannot_be_silently_bypassed(self):
        with (patch.object(gate,"clone_readonly_main",return_value=2),
              patch.object(gate,"anonymous_guard") as anonymous,
              patch.object(gate,"caddy_route_guard") as caddy):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(gate.main(),2)
        anonymous.assert_not_called()
        caddy.assert_not_called()
        self.assertIn("STOP=DB_R31_11_2_CLONE_RLS_NOT_REVERIFIED",out.getvalue())

if __name__=="__main__":
    unittest.main()
