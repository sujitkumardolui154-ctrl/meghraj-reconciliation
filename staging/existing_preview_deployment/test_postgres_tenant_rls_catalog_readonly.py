"""Narrow, offline, no-DB unit tests for R31 QA-only tenant catalog preflight."""
import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("r31_rls_audit",
    HERE/"verify_postgres_tenant_rls_catalog_readonly.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def secure_catalog():
    return {
      "db":mod.DB,"pg16":True,
      "login_roles":2,"member_pairs":2,"all_member_links":2,
      "mappings":2,"mapped_distinct":2,"forced_tables":4,
      "select_policies":4,"other_policies":0,"invoker_view":1,
      "mapping_readers":0,"writer_roles":0,"data_rows":0
    }

class CatalogTests(unittest.TestCase):
    def test_source_scope_is_exactly_dedicated_qa(self):
        self.assertEqual(mod.DB,"sbi_r31_11_4_auth_qa_20261126")
        self.assertEqual(mod.PG,"sbi-r3114-private-postgres")
        self.assertEqual(mod.NET,"sbi-r3114-private-isolated")
        self.assertTrue(mod.TARGET.endswith("/login"))
        self.assertNotIn("sbi_reconciliation_main",mod.QUERY)

    def test_sql_audits_are_transaction_read_only(self):
        self.assertIn("BEGIN READ ONLY;",mod.QUERY)
        self.assertIn("COMMIT;",mod.QUERY)
        for forbidden in ("INSERT INTO","UPDATE sbi.","DELETE FROM","CREATE ROLE",
                          "ALTER ROLE","CREATE TABLE","DROP TABLE","SET ROLE"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden,mod.QUERY)

    def test_pass_only_exact_restricted_catalog(self):
        self.assertEqual(mod.classify(secure_catalog()),
                         "PASS_RESTRICTED_CATALOG_ONLY")

    def test_rejects_any_weakened_rls_mapping_or_db_state(self):
        good=secure_catalog()
        for k in good:
            changed=deepcopy(good)
            expected=good[k]
            # Mutate every field to a genuinely different value. In the
            # original test invoker_view=1 was replaced by 1 (no change),
            # causing a false failure of the test, not the RLS checker.
            if type(expected) is str:
                changed[k]="wrong"
            elif type(expected) is bool:
                changed[k]=not expected
            else:
                changed[k]=expected - 1 if expected > 0 else 1
            self.assertNotEqual(changed[k],expected)
            with self.subTest(field=k):
                self.assertEqual(mod.classify(changed),"REVIEW_REQUIRED")

    def test_rejects_missing_or_bad_type_fields(self):
        for key in secure_catalog():
            q=secure_catalog()
            del q[key]
            with self.subTest(key=key):
                self.assertEqual(mod.classify(q),"REVIEW_REQUIRED")

    def test_isolated_topology(self):
        good={"State":{"Running":True},"HostConfig":{"Privileged":False,
             "PortBindings":{}},"NetworkSettings":{"Networks":{mod.NET:{}}}}
        net={"Internal":True,"Attachable":False}
        self.assertTrue(mod.topology(good,net))
        cases=[
          ({"HostConfig":{"Privileged":True}},net),
          ({"HostConfig":{"PortBindings":{"5432/tcp":[{}]}}},net),
          (good,{"Internal":False,"Attachable":False}),
          (good,{"Internal":True,"Attachable":True}),
          ({"NetworkSettings":{"Networks":{"public":{}}}},net),
        ]
        for updates,n in cases:
            changed=deepcopy(good)
            changed.update(updates)
            with self.subTest(updates=updates,n=n):
                self.assertFalse(mod.topology(changed,n))

if __name__=="__main__":
    unittest.main()
