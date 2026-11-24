"""Static safety contracts for the QA-only owner-scoped SHA transaction.

Live PostgreSQL behavior is NOT proven by these tests; use the combined AWS
runner to verify the SQL, rollback and inherited immutable evidence triggers.
"""
import unittest
from pathlib import Path
BASE=Path(__file__).parent
SQL=(BASE/'db_r31_owner_scope_qa_tx.sql').read_text(encoding='utf-8')
RUN=(BASE/'db_r31_owner_scope_qa.sh').read_text(encoding='utf-8')

class OwnerScopeQAContracts(unittest.TestCase):
    def test_isolated_database_guard_and_rollback(self):
        self.assertIn("current_database() <> 'sbi_ft04g_clean_0e858f93'",SQL)
        self.assertTrue(SQL.rstrip().endswith(
            "SELECT 'DB_R31_OWNER_SCOPE_QA_TRANSACTION=ROLLED_BACK';"))
        self.assertIn("\nROLLBACK;\n",SQL)
        self.assertNotIn("\nCOMMIT;\n",SQL)
    def test_both_owner_scoped_and_legacy_unique(self):
        self.assertIn('CREATE UNIQUE INDEX ux_r31_qa_owned_source_sha',SQL)
        self.assertIn('(owner_uid,source_system,source_kind,source_sha256)',SQL)
        self.assertIn('WHERE owner_uid IS NOT NULL',SQL)
        self.assertIn('CREATE UNIQUE INDEX ux_r31_qa_legacy_source_sha',SQL)
        self.assertIn('WHERE owner_uid IS NULL',SQL)
        self.assertIn('DB_R31_LEGACY_GLOBAL_SHA_CONSTRAINT_NOT_EXACTLY_ONE',SQL)
    def test_legacy_not_reclassified_and_new_owner_required(self):
        self.assertIn('NOT VALID;',SQL)
        self.assertIn('source_receipt_id IS NOT NULL',SQL)
        self.assertIn('source_sheet_name IS NOT NULL',SQL)
        self.assertIn('source_parser_version IS NOT NULL',SQL)
        self.assertIn('DB_R31_UNOWNED_NEW_PAYMENT_NOT_REJECTED',SQL)
    def test_source_status_and_credit_not_allocated(self):
        self.assertIn('EXCLUDED_INVALID_SOURCE',SQL)
        self.assertIn('HOLD_SOL_MASTER',SQL)
        self.assertIn('QA_MASTER_NOT_VERIFIED',SQL)
        self.assertIn('NOT_CALCULATED',SQL)
        self.assertIn('001505',SQL)
        self.assertNotIn('sbi.allocations',SQL)
    def test_runner_must_validate_isolation_and_no_persistence(self):
        for marker in ('network[\'Internal\'] is True',
                       "DB_R31_PRODUCTION_DB_IN_QA_INSTANCE=ABSENT",
                       "DB_R31_GLOBAL_SHA_UNIQUE=STILL_PRESENT_AFTER_ROLLBACK",
                       "DB_R31_QA_FINANCIAL_ROWS_AND_SCHEMA_UNCHANGED=PASS"):
            self.assertIn(marker,RUN)
        self.assertIn('DB_R31_QA_OWNER_SCOPE_TRANSACTION=PASS_ROLLED_BACK',RUN)
    def test_no_production_financial_writes_or_table_replacement(self):
        for forbidden in ('sbi_reconciliation_main\';\nCOMMIT;', 
                          'TRUNCATE', 'DROP TABLE sbi.payments',
                          'DELETE FROM sbi.payments',
                          'UPDATE sbi.payments SET',
                          'SET ROLE sbi_pr129_report_login'):
            self.assertNotIn(forbidden,SQL)
if __name__=='__main__':
    unittest.main(verbosity=2)
