"""R31.11.4H offline combined-mode safety tests: never call real AWS/SDK."""
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
import unittest

import r31_11_4h_combined_readonly_security as stage

GOOD_SHA="a"*40
USERS=[
    {"uid":"fake-ci-uid-a","email":"a@example.invalid"},
    {"uid":"fake-ci-uid-b","email":"b@example.invalid"},
]


class CombinedReadOnlyTests(unittest.TestCase):
    def _checks(self, *, fingerprint=None, users=None):
        entered=[]
        def run_caddy():
            entered.append("caddy")
            return stage.EXPECTED_4G_CADDY_SHA256 if fingerprint is None else fingerprint
        patches=[
            patch.object(stage,"check_repo_and_scope"),
            patch.object(stage.e,"_candidate_source_guards"),
            patch.object(stage.e.infra,"preflight"),
            patch.object(stage.e,"_read_only_qa_catalog"),
            patch.object(stage.e.roles,"_approved_users",return_value=USERS if users is None else users),
            patch.object(stage.e,"_secure_metadata"),
            patch.object(stage.e,"_no_private_qa_runtime_deployment"),
            patch.object(stage.g,"check_database_isolation"),
            patch.object(stage.g,"caddy_preflight",side_effect=run_caddy),
            patch.object(stage.g,"ephemeral_cleanup"),
        ]
        return patches,entered

    def test_combined_runs_all_nonmutating_checks_twice_as_needed(self):
        patches,entered=self._checks()
        with (patches[0] as src,patches[1] as source,
              patches[2] as infra, patches[3] as roles,
              patches[4] as users,patches[5] as metadata,
              patches[6] as deployment,patches[7] as pg,
              patches[8] as caddy,patches[9] as cleanup,
              redirect_stdout(StringIO()) as out):
            self.assertEqual(stage.main(["--source-sha",GOOD_SHA]),0)
        src.assert_called_once_with(GOOD_SHA)
        source.assert_called_once()
        infra.assert_called_once()
        roles.assert_called_once()
        users.assert_called_once()
        metadata.assert_called_once()
        deployment.assert_called_once()
        self.assertEqual(pg.call_count,2)
        self.assertEqual(caddy.call_count,2)
        cleanup.assert_called_once()
        self.assertIn("DB_R31_11_4H_COMBINED_READONLY_SECURITY=PASS",
                      out.getvalue())
        self.assertIn("DB_R31_11_4H_REAL_FIREBASE_SESSION_E2E=EVIDENCE_NOT_PROVIDED",
                      out.getvalue())
        self.assertIn("DB_R31_11_4H_EXTERNAL_HTTPS_MTLS=NOT_TESTED",
                      out.getvalue())

    def test_caddy_baseline_mismatch_blocks_release(self):
        patches,_=self._checks(fingerprint="0"*64)
        with (patches[0],patches[1],patches[2],patches[3],patches[4],
              patches[5],patches[6],patches[7],patches[8],
              patches[9] as cleanup,redirect_stdout(StringIO()) as out):
            self.assertEqual(stage.main(["--source-sha",GOOD_SHA]),2)
        cleanup.assert_not_called()
        self.assertIn("STOP=DB_R31_11_4H_COMBINED_READONLY_REVIEW_REQUIRED",
                      out.getvalue())
        self.assertNotIn("COMBINED_READONLY_SECURITY=PASS",out.getvalue())

    def test_missing_or_duplicate_owners_block_and_do_not_claim_pass(self):
        for users in ([],[USERS[0],USERS[0]],[USERS[0]]):
            patches,_=self._checks(users=users)
            with (patches[0],patches[1],patches[2],patches[3],
                  patches[4],patches[5],patches[6],patches[7],
                  patches[8],patches[9],redirect_stdout(StringIO()) as out):
                self.assertEqual(stage.main(["--source-sha",GOOD_SHA]),2)
            self.assertIn("PRODUCTION_RELEASE=BLOCKED",out.getvalue())
            self.assertNotIn("COMBINED_READONLY_SECURITY=PASS",out.getvalue())

    def test_sensitive_exception_is_never_printed(self):
        with (patch.object(stage,"check_repo_and_scope",
                           side_effect=Exception("PRIVATE_FIREBASE_TOKEN_SECRET")),
              redirect_stdout(StringIO()) as out):
            self.assertEqual(stage.main(["--source-sha",GOOD_SHA]),2)
        self.assertNotIn("PRIVATE_FIREBASE_TOKEN_SECRET",out.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",out.getvalue())

    def test_sha_guard_fails_closed(self):
        with patch.object(stage.g,"check_source") as source:
            with self.assertRaises(stage.CombinedBlocked):
                stage.check_repo_and_scope("unsafe")
            source.assert_not_called()
            with self.assertRaises(stage.CombinedBlocked):
                stage.check_repo_and_scope("deadbeef"*5)
            source.assert_not_called()


if __name__=="__main__":
    unittest.main()
