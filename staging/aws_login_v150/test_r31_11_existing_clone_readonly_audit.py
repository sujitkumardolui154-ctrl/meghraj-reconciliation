"""Offline regression tests for R31.11 existing clone READ-ONLY resume."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PATH = ROOT/"r31_11_existing_clone_readonly_audit.py"
SOURCE = PATH.read_text("utf-8")

from r31_11_existing_clone_readonly_audit import (
    ROLES, POLICIES, SOURCE_TABLES, catalog_complete, known_fixture,
    checked_role_result,
)

def valid_catalog():
    policies = []
    for table, name in POLICIES:
        policies.append({
            "table":table,"name":name,"cmd":"SELECT",
            "permissive":"PERMISSIVE","roles":sorted(ROLES),
            "qual":"owner_uid = r311_auth.current_tenant_uid()",
            "with_check":None,
        })
    return {
        "database":"sbi_r31_11_tenant_clone_20261125",
        "tables":[{"table":t,"rls":True,"forced":True} for t in SOURCE_TABLES],
        "policies":policies,
        "view_exists":True,
        "invoker_view":True,
        "shared_view_select":False,
        "map_exists":True,
        "function_secure":True,
        "roles":[{"role":r,"login":False,"inherit":False,
                  "super":False,"bypass":False} for r in ROLES],
    }

def valid_fixture():
    return {k:2 for k in (
        "batches","source_rows","payments","status","expected_batches",
        "expected_rows","expected_payments","expected_status","map_rows",
        "map_exact"
    )}

def valid_role(role):
    return {
        "database":"sbi_r31_11_tenant_clone_20261125","role":role,
        "uid_ok":True,"all_rls":True,"batches":1,"source_rows":1,
        "payments":1,"statuses":1,"view_rows":1,"foreign_batches":0,
    }

class ExistingCloneAuditSafetyTests(unittest.TestCase):
    def test_file_syntax(self):
        ast.parse(SOURCE)

    def test_catalog_accepts_only_exact_safe_shape(self):
        self.assertTrue(catalog_complete(valid_catalog()))
        for change in (
            lambda d: d.update(database="sbi_reconciliation_main"),
            lambda d: d["tables"][0].update(forced=False),
            lambda d: d["policies"][0].update(cmd="ALL"),
            lambda d: d["policies"][0].update(roles=["public"]),
            lambda d: d["policies"][0].update(qual="true"),
            lambda d: d["roles"][0].update(login=True),
            lambda d: d["roles"][0].update(bypass=True),
            lambda d: d.update(shared_view_select=True),
            lambda d: d.update(invoker_view=False),
            lambda d: d.update(function_secure=False),
            lambda d: d.update(map_exists=False),
        ):
            data=valid_catalog()
            change(data)
            self.assertFalse(catalog_complete(data))

    def test_no_extra_or_missing_policies(self):
        data=valid_catalog()
        data["policies"].append(data["policies"][0].copy())
        self.assertFalse(catalog_complete(data))
        data=valid_catalog()
        data["tables"].pop()
        self.assertFalse(catalog_complete(data))

    def test_exact_fixture_requires_all_expected_rows(self):
        self.assertTrue(known_fixture(valid_fixture()))
        for key in valid_fixture():
            data=valid_fixture()
            data[key]=1
            self.assertFalse(known_fixture(data))

    def test_readonly_role_results_must_be_bidirectionally_scoped(self):
        for role in ROLES:
            self.assertTrue(checked_role_result(valid_role(role), role))
            for field,bad in (
                ("foreign_batches",1),("all_rls",False),("payments",2),
                ("view_rows",2),("uid_ok",False),
                ("database","sbi_reconciliation_main"),
            ):
                data=valid_role(role)
                data[field]=bad
                self.assertFalse(checked_role_result(data,role))

    def test_host_contract_is_readonly_and_non_destructive(self):
        for dangerous in (
            '"createdb"', '"pg_dump"', '"pg_restore"', '"dropdb"',
            '"run"', '"build"', '"network","connect"',
            '"DELETE FROM"', '"INSERT INTO"', '"ALTER TABLE"',
            '"DROP TABLE"', '"CREATE ROLE"', '"UPDATE sbi."',
            "password=", "FIREBASE_WEB_API_KEY",
        ):
            self.assertNotIn(dangerous,SOURCE)
        self.assertIn("BEGIN READ ONLY",SOURCE)
        self.assertIn("DB_R31_11_EXISTING_CLONE=FOUND_READONLY",SOURCE)
        self.assertIn("NO_CREATION",SOURCE)
        self.assertIn("NOT_CONNECTED",SOURCE)
        self.assertIn("SECURITY_QA_ONLY_PRODUCTION_BLOCKED",SOURCE)

if __name__=="__main__":
    unittest.main()
