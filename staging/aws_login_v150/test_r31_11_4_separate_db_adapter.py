"""R31.11.4 separate target adapter tests. No live accounts or credentials."""
from __future__ import annotations
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import r31_11_4_runtime_rls_adapter as a
import r31_11_3_runtime_rls_adapter as previous
import r31_11_4_private_runtime_readiness as gate


class FakeCursor:
    def __init__(self, owner, role):
        self.owner=owner
        self.role=role
        self.calls=[]
        self.force_old_database=False

    def execute(self, sql, args=None):
        self.calls.append((sql,args))

    def fetchone(self):
        return (
            previous.QA_DB if self.force_old_database else a.QA_DB,
            self.role,self.role,"on",self.owner,
            True,False,False,False,False,
            True,True,True,True,
            False,False,False,False,False,False,
        )

    def fetchall(self):
        return [(self.owner,2,"001505","PENDING_RECONCILIATION",11800)]

    def __enter__(self): return self
    def __exit__(self,*args): return False


class FakeConnection:
    def __init__(self,cur): self.cur=cur
    def cursor(self): return self.cur
    def __enter__(self): return self
    def __exit__(self,*args): return False


class SeparateAdapterTests(unittest.TestCase):
    def test_target_is_distinct_and_pinned_to_private_candidate(self):
        self.assertEqual(a.QA_DB,gate.NEW_DB)
        self.assertEqual(a.QA_HOST,gate.NEW_PG)
        self.assertNotEqual(a.QA_DB,previous.QA_DB)
        self.assertNotEqual(a.QA_HOST,previous.QA_HOST)
        self.assertEqual(a.MAP_PATH.as_posix(),
                         "/run/secrets/r3114-tenant-bindings.json")
        self.assertTrue(a.SECRET_RE.fullmatch(
            "/run/secrets/r3114-owner-a.env"))
        self.assertFalse(a.SECRET_RE.fullmatch(
            "/run/secrets/r3113-owner-a.env"))

    def test_binding_requires_exact_private_new_db_and_unique_roles(self):
        doc={
          "version":1,"database":a.QA_DB,
          "bindings":[
            {"firebase_uid":"synthetic-firebase-a",
             "pg_login_role":"r3113_login_a",
             "secret_path":"/run/secrets/r3114-owner-a.env"},
            {"firebase_uid":"synthetic-firebase-b",
             "pg_login_role":"r3113_login_b",
             "secret_path":"/run/secrets/r3114-owner-b.env"},
          ],
        }
        with patch.object(a,"_secure_file",return_value=json.dumps(doc)):
            self.assertEqual(
                a._binding_for_uid("synthetic-firebase-a"),
                ("r3113_login_a",Path("/run/secrets/r3114-owner-a.env")))
            with self.assertRaises(a.RuntimeRLSBlocked):
                a._binding_for_uid("unknown-user")
        doc["database"]=previous.QA_DB
        with patch.object(a,"_secure_file",return_value=json.dumps(doc)):
            with self.assertRaises(a.RuntimeRLSBlocked):
                a._binding_for_uid("synthetic-firebase-a")

    def test_secure_login_refuses_existing_clone_or_pg_host(self):
        secret=(
            "PGHOST="+a.QA_HOST+"\nPGPORT=5432\nPGDATABASE="+a.QA_DB+
            "\nPGUSER=r3113_login_a\nPGPASSWORD="+("x"*32)+"\n"
        )
        with patch.object(a,"_secure_file",return_value=secret):
            self.assertEqual(a._login_secret(Path("/run/secrets/r3114-owner-a.env"),
                                              "r3113_login_a"),"x"*32)
        for change in (previous.QA_HOST,previous.QA_DB):
            bad=secret.replace(a.QA_HOST,change) if change==previous.QA_HOST \
                else secret.replace(a.QA_DB,change)
            with patch.object(a,"_secure_file",return_value=bad):
                with self.assertRaises(a.RuntimeRLSBlocked):
                    a._login_secret(Path("/run/secrets/r3114-owner-a.env"),
                                    "r3113_login_a")

    def test_actual_sql_execution_is_readonly_and_db_bound(self):
        owner="synthetic-firebase-a"
        role="r3113_login_a"
        user=SimpleNamespace(uid=owner,custom_claims={"dil_dashboard":True})
        cur=FakeCursor(owner,role)
        supplied={}
        def connect(**kwargs):
            supplied.update(kwargs)
            return FakeConnection(cur)
        with (patch.dict(os.environ,{"SBI_R31_11_4_RUNTIME_ENABLED":a.ENABLE_FLAG}),
              patch.object(a,"_binding_for_uid",return_value=(
                  role,Path("/run/secrets/r3114-owner-a.env"))),
              patch.object(a,"_login_secret",return_value="fake-test-only")):
            results=a.read_tenant_source_only(user,connect=connect,limit=3)
            self.assertEqual(results[0]["credit_paise"],11800)
            self.assertEqual(supplied["dbname"],gate.NEW_DB)
            self.assertEqual(supplied["host"],gate.NEW_PG)
            self.assertEqual(supplied["user"],role)
            self.assertIn("default_transaction_read_only=on",supplied["options"])
            self.assertEqual(cur.calls[0][0],"SET TRANSACTION READ ONLY")
            self.assertNotIn("WHERE owner_uid",a.READ_SQL)
            cur.force_old_database=True
            with self.assertRaises(a.RuntimeRLSBlocked):
                a.read_tenant_source_only(user,connect=connect,limit=3)

    def test_disabled_or_unclaimed_user_never_reads_db(self):
        user=SimpleNamespace(uid="synthetic-firebase-a",
                             custom_claims={"dil_dashboard":False})
        with patch.object(a,"_binding_for_uid") as mapper:
            with self.assertRaises(a.RuntimeRLSBlocked):
                a.read_tenant_source_only(user)
            mapper.assert_not_called()
            with patch.dict(os.environ,{
                "SBI_R31_11_4_RUNTIME_ENABLED":a.ENABLE_FLAG
            }):
                with self.assertRaises(a.RuntimeRLSBlocked):
                    a.read_tenant_source_only(user)
                mapper.assert_not_called()


if __name__=="__main__":
    unittest.main()
