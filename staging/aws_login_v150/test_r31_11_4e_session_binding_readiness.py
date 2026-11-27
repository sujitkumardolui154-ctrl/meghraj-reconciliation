"""Offline-only regressions for R31.11.4E private read-only readiness.

These tests NEVER reach AWS, the real Firebase project or PostgreSQL.
"""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import r31_11_4e_session_binding_readiness as stage


class R3114EReadinessTests(unittest.TestCase):
    def test_requires_exact_private_qa_catalog(self):
        with (patch.object(stage.readiness, "_inspect", return_value={}),
              patch.object(stage.readiness, "_docker",
                           return_value=json.dumps([{}])),
              patch.object(stage.readiness, "_candidate_isolated", return_value=True),
              patch.object(stage.readiness, "_public_route_absent"),
              patch.object(stage.readiness, "_safe_catalog_state",
                           return_value={"new_db":1,"forbidden_dbs":0}),
              patch.object(stage.readiness, "_rls_schema_present", return_value=True),
              patch.object(stage.readiness, "_restricted_role_state", return_value={}),
              patch.object(stage.readiness, "_restricted_roles_complete", return_value=True),
              patch.object(stage.roles, "_catalog_counts", return_value={
                  "db":stage.roles.DB,"role_count":2,"group_count":2,
                  "maps":2,"data_rows":0,"policy_count":4,"forced_rls":4,
              })):
            stage._read_only_qa_catalog()
            with patch.object(stage.roles, "_catalog_counts", return_value={
                "db":stage.roles.DB,"role_count":2,"group_count":2,
                "maps":2,"data_rows":1,"policy_count":4,"forced_rls":4,
            }):
                with self.assertRaises(stage.ReadinessBlocked):
                    stage._read_only_qa_catalog()
            with patch.object(stage.readiness,"_restricted_roles_complete",return_value=False):
                with self.assertRaises(stage.ReadinessBlocked):
                    stage._read_only_qa_catalog()

    def test_private_metadata_uses_privileged_stat_without_reading(self):
        valid = "\n".join([
            "700 10001 10001 4096 directory",
            "600 10001 10001 155 regular file",
            "600 10001 10001 155 regular file",
            "600 10001 10001 500 regular file",
        ]) + "\n"
        success=SimpleNamespace(returncode=0,stdout=valid,stderr="")
        with patch.object(stage.subprocess,"run",return_value=success) as run:
            stage._secure_metadata()
            command=run.call_args.args[0]
            self.assertEqual(command[:6],
                             ["sudo","-n","stat","-c","%a %u %g %s %F","--"])
            self.assertEqual(len(command),10)
            self.assertNotIn("-L",command)
            self.assertEqual(run.call_args.kwargs["capture_output"],True)
        for broken in (
            valid.replace("700 10001","755 10001",1),
            valid.replace("600 10001","644 10001",1),
            valid.replace("10001 10001","0 0",1),
            valid.replace("155 regular file","155 symbolic link",1),
            valid.replace("500 regular file","0 regular file",1),
            valid.replace("500 regular file","8193 regular file",1),
        ):
            with patch.object(stage.subprocess,"run",
                              return_value=SimpleNamespace(returncode=0,
                                                           stdout=broken,stderr="")):
                with self.assertRaises(stage.ReadinessBlocked):
                    stage._secure_metadata()
        with patch.object(stage.subprocess,"run",
                          return_value=SimpleNamespace(returncode=1,stdout="",
                                                       stderr="PRIVATE_AWS_KEY_SENTINEL")):
            with self.assertRaises(stage.ReadinessBlocked) as reason:
                stage._secure_metadata()
            self.assertNotIn("PRIVATE_AWS_KEY_SENTINEL",str(reason.exception))

    def test_sensitive_metadata_error_does_not_leak(self):
        with (patch.object(stage,"_candidate_source_guards",
                           side_effect=stage.ReadinessBlocked(
                               "QA_SECRET_METADATA_INSPECTION_UNAVAILABLE")),
              redirect_stdout(StringIO()) as capture):
            self.assertEqual(stage.main(),2)
        self.assertIn("DB_R31_11_4E_BLOCK_REASON=QA_SECRET_METADATA_INSPECTION_UNAVAILABLE",
                      capture.getvalue())
        with (patch.object(stage,"_candidate_source_guards",
                           side_effect=stage.ReadinessBlocked("SECRET_SENTINEL=123")),
              redirect_stdout(StringIO()) as capture):
            self.assertEqual(stage.main(),2)
        self.assertNotIn("SECRET_SENTINEL",capture.getvalue())
        self.assertIn("BLOCK_REASON=UNCLASSIFIED_READINESS_FAILURE",capture.getvalue())

    def test_blocks_public_private_candidate_and_observes_no_launch(self):
        allowed=SimpleNamespace(returncode=0,stdout="sbi-r3114-private-postgres\n")
        denied=SimpleNamespace(returncode=0,stdout="sbi-r3114-private-postgres\nsbi-r3114-private-api\n")
        with patch.object(stage.subprocess,"run",return_value=allowed) as run:
            stage._no_private_qa_runtime_deployment()
            self.assertIn("docker",run.call_args.args[0])
            self.assertIn("ps",run.call_args.args[0])
        with patch.object(stage.subprocess,"run",return_value=denied):
            with self.assertRaises(stage.ReadinessBlocked):
                stage._no_private_qa_runtime_deployment()

    def test_no_approval_or_write_action_reaches_any_runtime(self):
        with (patch.object(stage,"_candidate_source_guards"),
              patch.object(stage.infra,"preflight"),
              patch.object(stage,"_read_only_qa_catalog"),
              patch.object(stage.roles,"_approved_users",return_value=[
                  {"uid":"test-ci-owner-a"},{"uid":"test-ci-owner-b"}]),
              patch.object(stage,"_secure_metadata"),
              patch.object(stage,"_no_private_qa_runtime_deployment"),
              redirect_stdout(StringIO()) as capture):
            self.assertEqual(stage.main(),0)
        result=capture.getvalue()
        self.assertIn("DB_R31_11_4E_PRIVATE_PG16_RLS=PASS_READONLY",result)
        self.assertIn("DB_R31_11_4E_TWO_REAL_FIREBASE_USERS=PASS_ADMIN_READONLY",result)
        self.assertIn("DB_R31_11_4E_REAL_SESSION_E2E=NOT_TESTED",result)
        self.assertIn("DB_R31_11_4E_RELEASE=PRODUCTION_BLOCKED",result)

    def test_sensitive_exception_message_never_printed(self):
        with (patch.object(stage,"_candidate_source_guards",
                           side_effect=RuntimeError("SECRET_COOKIE_TOKEN_SENTINEL")),
              redirect_stdout(StringIO()) as capture):
            self.assertEqual(stage.main(),2)
        self.assertNotIn("SECRET_COOKIE_TOKEN_SENTINEL",capture.getvalue())
        self.assertIn("STOP=DB_R31_11_4E_PRIVATE_ACCEPTANCE_REVIEW_REQUIRED",
                      capture.getvalue())
        self.assertIn("DB_R31_11_4E_FINANCIAL_APPLY=LOCKED",capture.getvalue())


if __name__ == "__main__":
    unittest.main()
