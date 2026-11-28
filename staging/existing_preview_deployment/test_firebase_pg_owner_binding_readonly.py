"""Offline-only tests for exact Firebase email->UID->Postgres binding logic."""
import importlib.util
from copy import deepcopy
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("binding",HERE/"verify_firebase_pg_owner_binding_readonly.py")
binding=importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)

def records():
    return [
        {"db_role":"r3113_login_a","uid":"synthetic_uid_alpha","email":"qa-alpha@example.invalid"},
        {"db_role":"r3113_login_b","uid":"synthetic_uid_beta","email":"qa-beta@example.invalid"},
    ]

class BindingTests(unittest.TestCase):
    def test_two_properly_mapped_accounts(self):
        self.assertEqual(binding.compare_records(records(),
             ["qa-beta@example.invalid","qa-alpha@example.invalid"],
             {"r3113_login_a":"synthetic_uid_alpha","r3113_login_b":"synthetic_uid_beta"}),
             "PASS_APPROVED_PAIR_MATCHES_PROTECTED_DB_MAP")

    def test_unapproved_https_employee_refused(self):
        self.assertEqual(binding.compare_records(records(),
             ["qa-alpha@example.invalid","other@example.invalid"],
             {"r3113_login_a":"synthetic_uid_alpha","r3113_login_b":"synthetic_uid_beta"}),
             "QA_HTTPS_EMPLOYEE_PAIR_NOT_IN_APPROVAL_RECORD")

    def test_database_uid_swap_refused(self):
        self.assertEqual(binding.compare_records(records(),
             ["qa-alpha@example.invalid","qa-beta@example.invalid"],
             {"r3113_login_a":"synthetic_uid_beta","r3113_login_b":"synthetic_uid_alpha"}),
             "QA_DB_OWNER_MAPPING_MISMATCH")

    def test_duplicate_uid_refused(self):
        r=records()
        r[1]["uid"]="synthetic_uid_alpha"
        self.assertEqual(binding.compare_records(r,
             ["qa-alpha@example.invalid","qa-beta@example.invalid"],
             {"r3113_login_a":"synthetic_uid_alpha","r3113_login_b":"synthetic_uid_alpha"}),
             "REVIEW_REQUIRED")

    def test_missing_wrong_unexpected_role_refused(self):
        for change in ("r3113_login_z","r3113_login_a"):
            r=records()
            r[1]["db_role"]=change
            with self.subTest(change=change):
                self.assertEqual(binding.compare_records(r,
                     ["qa-alpha@example.invalid","qa-beta@example.invalid"],
                     {"r3113_login_a":"synthetic_uid_alpha","r3113_login_b":"synthetic_uid_beta"}),
                     "REVIEW_REQUIRED")

    def test_database_output_cannot_be_synthetic_or_omitted(self):
        mapping={"r3113_login_a":"synthetic_uid_alpha"}
        self.assertEqual(binding.compare_records(records(),
             ["qa-alpha@example.invalid","qa-beta@example.invalid"],mapping),
             "QA_DB_OWNER_MAPPING_MISMATCH")

    def test_production_db_not_target(self):
        self.assertEqual(binding.catalog.DB,"sbi_r31_11_4_auth_qa_20261126")
        self.assertEqual(binding.catalog.PG,"sbi-r3114-private-postgres")
        self.assertTrue(binding.catalog.TARGET.endswith("/login"))

if __name__=="__main__":
    unittest.main()
