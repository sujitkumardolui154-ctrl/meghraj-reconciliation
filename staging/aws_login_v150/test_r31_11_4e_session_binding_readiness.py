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

    def test_private_secret_metadata_rejects_symlink_and_bad_mode(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"secrets"
            root.mkdir(mode=0o700)
            for name in stage.FILES:
                (root/name).write_text("test-only")
                (root/name).chmod(0o600)
            stage._secure_metadata  # no real secret reads
            with (patch.object(stage,"SECRET_DIR",root),
                  patch.object(stage,"APP_UID",root.stat().st_uid),
                  patch.object(stage,"APP_GID",root.stat().st_gid)):
                stage._secure_metadata()
                (root/stage.FILES[0]).chmod(0o644)
                with self.assertRaises(stage.ReadinessBlocked):
                    stage._secure_metadata()
                (root/stage.FILES[0]).unlink()
                (root/stage.FILES[0]).symlink_to(root/stage.FILES[1])
                with self.assertRaises(stage.ReadinessBlocked):
                    stage._secure_metadata()

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
