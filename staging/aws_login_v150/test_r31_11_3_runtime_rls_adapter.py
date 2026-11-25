"""R31.11.3 essential runtime tenant security tests (offline, no AWS)."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
from types import SimpleNamespace
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import r31_11_3_runtime_rls_adapter as a


class FakeCursor:
    def __init__(self, uid="r3113-firebase-a", role="r3113_login_a", rows=None,
                 security=None):
        self.uid=uid
        self.role=role
        self.sql=[]
        self.rows=[(uid,2,"001505","PENDING_RECONCILIATION",11800)] if rows is None else rows
        self.security = security

    def execute(self, sql, args=None):
        self.sql.append((sql,args))

    def fetchone(self):
        if self.security is not None:
            return self.security
        return (a.QA_DB,self.role,self.role,"on",self.uid,True,
                False,False,False,False,
                True,True,True,True,
                False,False,False,False,False,False)

    def fetchall(self):
        return self.rows

    def __enter__(self): return self
    def __exit__(self,*args): return False


class FakeConnection:
    def __init__(self, cur): self.cur=cur
    def cursor(self): return self.cur
    def __enter__(self): return self
    def __exit__(self,*args): return False


class TestRuntimeRLS(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{"SBI_R31_11_3_RUNTIME_ENABLED":a.ENABLE_FLAG})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def user(self,uid="r3113-firebase-a"):
        return SimpleNamespace(uid=uid, custom_claims={"dil_dashboard":True})

    def test_exact_secure_binding_config_and_no_unverified_uid(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"bindings.json"
            p.write_text(json.dumps({
                "version":1,"database":a.QA_DB,
                "bindings":[
                    {"firebase_uid":"r3113-firebase-a",
                     "pg_login_role":"r3113_login_a",
                     "secret_path":"/run/secrets/r3113-owner-a.env"},
                    {"firebase_uid":"r3113-firebase-b",
                     "pg_login_role":"r3113_login_b",
                     "secret_path":"/run/secrets/r3113-owner-b.env"},
                ]}),encoding="utf-8")
            p.chmod(0o600)
            role,secret=a._binding_for_uid("r3113-firebase-a",path=p)
            self.assertEqual(role,"r3113_login_a")
            self.assertEqual(str(secret),"/run/secrets/r3113-owner-a.env")
            with self.assertRaises(a.RuntimeRLSBlocked):
                a._binding_for_uid("r3113-firebase-unknown",path=p)
            p.chmod(0o644)
            with self.assertRaises(a.RuntimeRLSBlocked):
                a._binding_for_uid("r3113-firebase-a",path=p)
            p.chmod(0o600)
            p.write_text(json.dumps({
                "version":1,"database":a.QA_DB,
                "bindings":[
                    {"firebase_uid":"r3113-firebase-a",
                     "pg_login_role":"r3113_login_a",
                     "secret_path":"/run/secrets/r3113-owner-a.env"},
                    {"firebase_uid":"r3113-firebase-b",
                     "pg_login_role":"r3113_login_a",
                     "secret_path":"/run/secrets/r3113-owner-b.env"},
                ]}))
            with self.assertRaises(a.RuntimeRLSBlocked):
                a._binding_for_uid("r3113-firebase-a",path=p)

    def test_login_secret_rejects_wrong_db_and_role(self):
        with patch.object(a,"_secure_file",return_value=(
            "PGHOST="+a.QA_HOST+"\nPGPORT=5432\nPGDATABASE="+a.QA_DB+
            "\nPGUSER=r3113_login_a\nPGPASSWORD="+("x"*24)+"\n")):
            self.assertEqual(a._login_secret(Path("/run/secrets/r3113-owner-a.env"),
                                              "r3113_login_a"),"x"*24)
            with self.assertRaises(a.RuntimeRLSBlocked):
                a._login_secret(Path("/run/secrets/r3113-owner-a.env"),
                                "r3113_login_b")
        with patch.object(a,"_secure_file",return_value=(
            "PGHOST=prod.example\nPGPORT=5432\nPGDATABASE="+a.QA_DB+
            "\nPGUSER=r3113_login_a\nPGPASSWORD="+("x"*24))):
            with self.assertRaises(a.RuntimeRLSBlocked):
                a._login_secret(Path("/run/secrets/r3113-owner-a.env"),
                                "r3113_login_a")

    def _read(self,cur,user=None):
        config={}
        def connect(**kwargs):
            config.update(kwargs)
            return FakeConnection(cur)
        with (patch.object(a,"_binding_for_uid",return_value=(
                "r3113_login_a",Path("/run/secrets/r3113-owner-a.env"))),
              patch.object(a,"_login_secret",return_value="only-test-password")):
            rows=a.read_tenant_source_only(user or self.user(),
                                           connect=connect, limit=10)
        return rows,config

    def test_authentic_user_database_login_and_readonly_sql(self):
        cur=FakeCursor()
        rows,config=self._read(cur)
        self.assertEqual(rows,[{"source_row_number":2,"raw_sol":"001505",
                                "source_status":"PENDING_RECONCILIATION",
                                "credit_paise":11800}])
        self.assertEqual(config["user"],"r3113_login_a")
        self.assertEqual(config["dbname"],a.QA_DB)
        self.assertEqual(config["host"],a.QA_HOST)
        self.assertIn("default_transaction_read_only=on",config["options"])
        self.assertEqual(cur.sql[0][0],"SET TRANSACTION READ ONLY")
        self.assertEqual(cur.sql[-1][1],(10,))
        self.assertNotIn("WHERE owner_uid",a.READ_SQL)
        self.assertIn("row_security_active",a.SECURITY_SQL)

    def test_role_uid_security_and_no_writes(self):
        for changes in [
            (0,"sbi_reconciliation_main"),(1,"postgres"),(2,"postgres"),
            (3,"off"),(4,"r3113-firebase-b"),(5,False),(6,True),
            (7,True),(8,True),(9,True),(10,False),(11,False),
            (12,False),(13,False),(14,True),(19,True)
        ]:
            base=FakeCursor().fetchone()
            row=list(base);row[changes[0]]=changes[1]
            with self.subTest(change=changes):
                with self.assertRaises(a.RuntimeRLSBlocked):
                    self._read(FakeCursor(security=tuple(row)))
        with self.assertRaises(a.RuntimeRLSBlocked):
            self._read(FakeCursor(rows=[(
                "r3113-firebase-b",2,"001506","PENDING_RECONCILIATION",35700
            )]))

    def test_never_attempts_database_on_absent_claim_or_disabled_flag(self):
        with patch.object(a,"_binding_for_uid") as mapping:
            with self.assertRaises(a.RuntimeRLSBlocked):
                a.read_tenant_source_only(SimpleNamespace(
                    uid="r3113-firebase-a",custom_claims={"dil_dashboard":False}))
            mapping.assert_not_called()
        with patch.dict(os.environ,{"SBI_R31_11_3_RUNTIME_ENABLED":"OFF"}):
            with self.assertRaises(a.RuntimeRLSBlocked):
                a.read_tenant_source_only(self.user())

if __name__=="__main__":
    unittest.main()
