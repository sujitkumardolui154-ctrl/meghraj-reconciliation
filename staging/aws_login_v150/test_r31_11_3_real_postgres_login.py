"""R31.11.3 disposable real PostgreSQL LOGIN-role integration test.

Runs ONLY in GitHub ephemeral PostgreSQL service with the explicit disposable
two-role CI SQL; no real user, bank row, AWS or production endpoint.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import psycopg
import r31_11_3_runtime_rls_adapter as a

CI_HOST="127.0.0.1"

class RealPostgresCI(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("R3113_DISPOSABLE_POSTGRES_CI")=="YES",
        "Not in disposable PostgreSQL CI"
    )
    def test_two_distinct_real_database_login_sessions(self):
        records=[
            ("r3113-firebase-a","r3113_login_a",
             "ci-r3113-A-disposable-password",11800),
            ("r3113-firebase-b","r3113_login_b",
             "ci-r3113-B-disposable-password",35700),
        ]
        # The actual connection must use password-authenticated Postgres role.
        # pg_hba in PostgreSQL CI service accepts password over loopback.
        def loopback(**kwargs):
            self.assertEqual(kwargs.pop("host"),a.QA_HOST)
            self.assertEqual(kwargs.pop("dbname"),a.QA_DB)
            self.assertEqual(kwargs.pop("port"),5432)
            return psycopg.connect(host=CI_HOST,dbname=a.QA_DB,port=5432,
                                   **kwargs)
        for uid,role,password,expected_paise in records:
            with self.subTest(role=role), (
                patch.dict(os.environ,{"SBI_R31_11_3_RUNTIME_ENABLED":a.ENABLE_FLAG}),
                patch.object(a,"_binding_for_uid",return_value=(
                    role,Path("/run/secrets/r3113-disposable-ci.env"))),
                patch.object(a,"_login_secret",return_value=password)
            ):
                data=a.read_tenant_source_only(
                    SimpleNamespace(uid=uid,custom_claims={"dil_dashboard":True}),
                    limit=10,connect=loopback)
                self.assertEqual(len(data),1)
                self.assertEqual(data[0]["credit_paise"],expected_paise)
                self.assertEqual(data[0]["source_status"],"PENDING_RECONCILIATION")
                self.assertEqual(data[0]["source_row_number"],2)

        # Database-enforced: role A cannot see B, not even via a crafted SQL WHERE.
        with psycopg.connect(host=CI_HOST,port=5432,dbname=a.QA_DB,
                             user="r3113_login_a",
                             password="ci-r3113-A-disposable-password") as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SELECT count(*) FROM sbi.import_batches WHERE owner_uid=%s",
                            ("r3113-firebase-b",))
                self.assertEqual(cur.fetchone()[0],0)
                cur.execute("SELECT current_user,r311_auth.current_tenant_uid()")
                self.assertEqual(cur.fetchone(),("r3113_login_a","r3113-firebase-a"))

if __name__=="__main__":
    unittest.main()
