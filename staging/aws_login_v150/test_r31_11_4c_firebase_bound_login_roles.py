"""R31.11.4C essential local safety checks — no AWS or real Firebase calls."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import r31_11_4c_firebase_bound_login_roles as stage


def _fake_user(uid, email, *, approved=True, admin=False, verified=True):
    return SimpleNamespace(
        uid=uid, email=email, disabled=False, email_verified=verified,
        custom_claims={"dil_dashboard":approved,"dil_admin":admin},
    )


class FakeAuth:
    def __init__(self):
        self.users={
          "user-a@example.invalid":_fake_user("firebase-user-a","user-a@example.invalid"),
          "user-b@example.invalid":_fake_user("firebase-user-b","user-b@example.invalid"),
        }
    def get_user_by_email(self,email,app=None):
        return self.users[email]
    def get_user(self,uid,app=None):
        return next(v for v in self.users.values() if v.uid==uid)


def records():
    return [
      {"db_role":"r3113_login_a","uid":"firebase-user-a","email":"user-a@example.invalid"},
      {"db_role":"r3113_login_b","uid":"firebase-user-b","email":"user-b@example.invalid"},
    ]


class PrivateFirebaseRoleTests(unittest.TestCase):
    def test_identity_validation_blocks_admin_disabled_unverified_and_one_user(self):
        admin=FakeAuth()
        self.assertEqual(len(stage._verify_admin_pair(records(),api=(admin,object()))),2)
        for changes in (
            ("admin",True),("approved",False),("verified",False),
        ):
            old=admin.users["user-b@example.invalid"]
            admin.users["user-b@example.invalid"] = _fake_user(
                old.uid,old.email,
                approved=changes[1] if changes[0]=="approved" else True,
                admin=changes[1] if changes[0]=="admin" else False,
                verified=changes[1] if changes[0]=="verified" else True)
            with self.assertRaises(stage.ProvisionBlocked):
                stage._verify_admin_pair(records(),api=(admin,object()))
            admin.users["user-b@example.invalid"]=old
        duplicate=records()
        duplicate[1]=dict(duplicate[1],uid="firebase-user-a")
        with self.assertRaises(stage.ProvisionBlocked):
            stage._verify_admin_pair(duplicate,api=(admin,object()))

    def test_source_uid_and_password_sql_generation_is_bounded(self):
        rec=records()
        passwords=("C"*64,"D"*64)
        sql=stage.build_provision_sql(rec,passwords)
        self.assertIn("current_database()<>'sbi_r31_11_4_auth_qa_20261126'",sql)
        self.assertIn("GRANT r311_qa_tenant_a TO r3113_login_a",sql)
        self.assertIn("INHERIT TRUE, SET FALSE, ADMIN FALSE",sql)
        self.assertIn("REVOKE CONNECT ON DATABASE postgres,template1 FROM PUBLIC",sql)
        self.assertIn("PASSWORD 'SCRAM-SHA-256$4096:",sql)
        self.assertNotIn("C"*64,sql)
        self.assertNotIn("D"*64,sql)
        self.assertIn("COMMIT;",sql)
        self.assertNotIn("sbi_reconciliation_main",sql)
        self.assertNotIn("SET ROLE",sql)
        self.assertNotIn("GRANT INSERT",sql)
        with self.assertRaises(stage.ProvisionBlocked):
            stage.build_provision_sql(rec,("x'bad","D"*64))
        with self.assertRaises(stage.ProvisionBlocked):
            stage.build_provision_sql(rec,("C"*64,)*2)
        malformed=records()
        malformed[0]["uid"]="bad uid'; DROP ROLE postgres; --"
        with self.assertRaises(stage.ProvisionBlocked):
            stage.build_provision_sql(malformed,passwords)

    def test_schema_gate_unchanged_and_readonly_missing_firebase_is_expected(self):
        ready={"db":stage.DB,"role_count":0,"group_count":2,
               "maps":0,"data_rows":0,"policy_count":4,"forced_rls":4}
        self.assertTrue(stage._schema_is_ready(ready))
        for field in ("role_count","maps","data_rows","policy_count","forced_rls"):
            val=dict(ready);val[field]+=1
            self.assertFalse(stage._schema_is_ready(val))
        with (patch.object(stage.schema,"_guarded_preflight",return_value="caddyhash"),
              patch.object(stage.schema,"_state",return_value={"x":"state"}),
              patch.object(stage.schema,"_is_schema_only",return_value=True),
              patch.object(stage.schema,"_all_new_source_tables_empty",return_value=True),
              patch.object(stage,"_catalog_counts",return_value=ready),
              patch.object(stage,"MANIFEST",Path("/nonexistent/test-r3114c.json")),
              patch.object(stage,"_db_apply") as apply,
              redirect_stdout(StringIO()) as output):
            self.assertEqual(stage.main([]),0)
            self.assertEqual(stage.main(["--apply","--approve",stage.APPROVE]),2)
            apply.assert_not_called()
        self.assertIn("TWO_APPROVED_FIREBASE_USERS=PENDING_LOCAL_VERIFICATION",
                      output.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",output.getvalue())

    def test_unauthorized_apply_fails_without_role_creation(self):
        ready={"db":stage.DB,"role_count":0,"group_count":2,
               "maps":0,"data_rows":0,"policy_count":4,"forced_rls":4}
        with (patch.object(stage.schema,"_guarded_preflight",return_value="caddyhash"),
              patch.object(stage.schema,"_state"),
              patch.object(stage.schema,"_is_schema_only",return_value=True),
              patch.object(stage.schema,"_all_new_source_tables_empty",return_value=True),
              patch.object(stage,"_catalog_counts",return_value=ready),
              patch.object(stage,"MANIFEST",Path("/tmp/r3114c-fake-exists")),
              patch.object(stage,"_approved_users",return_value=records()),
              patch.object(stage,"apply_roles") as apply,
              redirect_stdout(StringIO()) as output):
            Path("/tmp/r3114c-fake-exists").touch(exist_ok=True)
            try:
                self.assertEqual(stage.main(["--apply"]),2)
            finally:
                Path("/tmp/r3114c-fake-exists").unlink(missing_ok=True)
            apply.assert_not_called()
        self.assertIn("STOP=",output.getvalue())

    def test_provisioning_secret_files_match_runtime_and_have_no_duplicate_ids(self):
        with TemporaryDirectory() as root:
            folder=Path(root)/"private"
            with patch.object(stage,"SECRET_DIR",folder):
                paths=stage._secret_bundle(records(),("C"*64,"D"*64))
                self.assertEqual(len(paths),3)
                self.assertEqual({x.name for x in paths},{
                    "r3114-owner-a.env","r3114-owner-b.env",
                    "r3114-tenant-bindings.json",
                })
                for p in paths:
                    self.assertEqual(p.stat().st_mode & 0o777,0o600)
                self.assertEqual(folder.stat().st_mode & 0o777,0o700)
                manifest=json.loads(paths[2].read_text())
                self.assertEqual(len(manifest["bindings"]),2)
                self.assertEqual(manifest["bindings"][0]["firebase_uid"],
                                 "firebase-user-a")
                self.assertEqual(manifest["bindings"][0]["secret_path"],
                                 "/run/secrets/r3114-owner-a.env")
                with self.assertRaises(stage.ProvisionBlocked):
                    stage._secret_bundle(records(),("C"*64,"D"*64))

    def test_private_approved_users_file_permissions_and_project(self):
        with TemporaryDirectory() as root:
            approvals=Path(root)/"approvals"
            approvals.mkdir(mode=0o700)
            manifest=approvals/"two-approved-accounts.json"
            doc={"version":1,"project":stage.PROJECT,"test_users":records()}
            manifest.write_text(json.dumps(doc))
            manifest.chmod(0o600)
            with (patch.object(stage,"MANIFEST",manifest),
                  patch.object(stage,"_verify_admin_pair") as verify):
                self.assertEqual(stage._approved_users(),records())
                verify.assert_called_once()
                manifest.chmod(0o644)
                with self.assertRaises(stage.ProvisionBlocked):
                    stage._approved_users()
                manifest.chmod(0o600)
                doc["project"]="unapproved-project"
                manifest.write_text(json.dumps(doc))
                with self.assertRaises(stage.ProvisionBlocked):
                    stage._approved_users()

    def test_prepare_users_only_reads_admin_and_writes_private_local_receipt(self):
        api=(FakeAuth(),object())
        with TemporaryDirectory() as root:
            directory=Path(root)/"approved"
            manifest=directory/"two-approved-accounts.json"
            with (patch.object(stage,"MANIFEST_DIR",directory),
                  patch.object(stage,"MANIFEST",manifest),
                  redirect_stdout(StringIO()) as output):
                stage.prepare_users(emails=(
                    "user-a@example.invalid","user-b@example.invalid"),api=api)
                self.assertTrue(manifest.is_file())
                self.assertEqual(manifest.stat().st_mode & 0o777,0o600)
                self.assertEqual(directory.stat().st_mode & 0o777,0o700)
                with self.assertRaises(stage.ProvisionBlocked):
                    stage.prepare_users(emails=(
                        "user-a@example.invalid","user-b@example.invalid"),api=api)
        self.assertIn("TWO_DISTINCT_TEST_USERS=PASS_ADMIN_READONLY",
                      output.getvalue())

    def test_no_financial_unlock_and_no_existing_qa_mutation(self):
        src=Path(stage.__file__).read_text("utf-8")
        self.assertIn("FINANCIAL_APPLY=LOCKED",src)
        self.assertIn("R3112_FINANCIAL_INTEGRATION=QUARANTINED",src)
        self.assertNotIn("auth.create_user",src)
        self.assertNotIn("set_custom_user_claims",src)
        self.assertNotIn("caddy reload",src)
        self.assertNotIn("sbi_r31_owner_qa_20261125",src)


if __name__=="__main__":
    unittest.main()
