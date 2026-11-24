"""Offline safety tests for persistent isolated R31 QA installer."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
MIGRATION=(ROOT/"db_r31_owner_persistent_qa.sql").read_text()
INSTALLER=(ROOT/"db_r31_owner_qa_combined.py").read_text()
RUNTIME=(ROOT/"db_r31_owner_qa_runtime.py").read_text()


class PersistentQAContract(unittest.TestCase):
    def test_hard_locked_isolated_database(self):
        self.assertIn("current_database() <> 'sbi_r31_owner_qa_20261125'",MIGRATION)
        self.assertIn('DB="sbi_r31_owner_qa_20261125"',INSTALLER)
        self.assertIn('PRODUCTION_DATABASE_VISIBLE_IN_TEST_INSTANCE',INSTALLER)
        self.assertIn("SOURCE=\"sbi_ft04g_clean_0e858f93\"",INSTALLER)
    def test_schema_only_clone(self):
        self.assertIn('"--schema-only"',INSTALLER)
        self.assertIn('"--no-owner"',INSTALLER)
        self.assertIn('"--no-acl"',INSTALLER)
        self.assertIn("QA_NETWORK_ISOLATION_FAILED",INSTALLER)
        self.assertIn('"Internal"',INSTALLER)
    def test_no_primary_database_changes(self):
        self.assertNotIn("DROP DATABASE",INSTALLER.upper())
        self.assertNotIn("sbi_reconciliation_main",MIGRATION)
        self.assertNotIn("TRUNCATE",MIGRATION.upper())
        self.assertNotIn("DELETE FROM sbi.payments",MIGRATION)
    def test_owner_and_legacy_unique(self):
        self.assertIn("ux_r31_qa_owned_source_sha",MIGRATION)
        self.assertIn("ux_r31_qa_legacy_source_sha",MIGRATION)
        self.assertIn("WHERE owner_uid IS NULL",MIGRATION)
        self.assertIn("WHERE owner_uid IS NOT NULL",MIGRATION)
        self.assertIn("ck_r31_qa_new_payment_owner_evidence",MIGRATION)
        self.assertTrue(MIGRATION.rstrip().endswith(
            "SELECT 'DB_R31_OWNER_QA_SCHEMA_PERSISTED|PASS';"))
    def test_runtime_uses_real_existing_parser_and_no_allocation(self):
        self.assertIn("import payment_evidence_upload as original",RUNTIME)
        self.assertIn("original._parse(data)",RUNTIME)
        self.assertIn("persist_qa_source(conn,plan)",RUNTIME)
        self.assertIn('HOLD_SOL_MASTER',RUNTIME)
        self.assertIn("NOT_CALCULATED",RUNTIME)
        self.assertNotIn("sbi.allocations",RUNTIME)
    def test_no_application_deployment(self):
        self.assertIn('"--read-only"',INSTALLER)
        self.assertIn('"--cap-drop=ALL"',INSTALLER)
        self.assertIn('"--security-opt","no-new-privileges"',INSTALLER)
        self.assertIn('DB_R31_REAL_FIREBASE_AUTH=NOT_TESTED',INSTALLER)

if __name__=="__main__":
    unittest.main()
