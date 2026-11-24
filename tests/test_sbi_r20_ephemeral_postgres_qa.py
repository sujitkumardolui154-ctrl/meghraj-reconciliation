"""R20 disposable localhost Postgres connection and financial isolation tests."""
import os
import unittest
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"/"ci"))
from sbi_r20_ephemeral_postgres_qa import (
    run_ephemeral_pg_probe, _require_disposable_dsn, PostgreSQLIsolationRefusal,
)

class R20EphemeralSQLTests(unittest.TestCase):
    def test_01_production_database_name_denied(self):
        with self.assertRaisesRegex(PostgreSQLIsolationRefusal,"NON_DISPOSABLE_POSTGRESQL_TARGET_REFUSED"):
            _require_disposable_dsn("postgresql://postgres:somepass@127.0.0.1:5432/sbi_reconciliation_main")

    def test_02_remote_database_host_denied(self):
        with self.assertRaisesRegex(PostgreSQLIsolationRefusal,"NON_DISPOSABLE_POSTGRESQL_TARGET_REFUSED"):
            _require_disposable_dsn("postgresql://postgres:somepass@db.example.net:5432/sbi_r20_synthetic_qa")

    def test_03_wrong_port_denied(self):
        with self.assertRaisesRegex(PostgreSQLIsolationRefusal,"NON_DISPOSABLE_POSTGRESQL_TARGET_REFUSED"):
            _require_disposable_dsn("postgresql://postgres:somepass@127.0.0.1:5433/sbi_r20_synthetic_qa")

    def test_04_ephemeral_db_actual_readonly_rollback_and_capacity(self):
        dsn=os.environ.get("SBI_R20_DISPOSABLE_DSN")
        if not dsn:
            self.skipTest("Only GitHub isolated postgres service can run database integration")
        report=run_ephemeral_pg_probe(dsn)
        for key in (
            "postgresql_schema_created_in_disposable_ci_only",
            "readonly_transaction_write_denied",
            "readonly_role_write_denied",
            "duplicate_reservation_rejected",
            "credit_capacity_violation_rejected",
            "invoice_capacity_violation_rejected",
            "protected_invoice_rejected",
            "cross_sol_rejected",
            "rolled_back_all_synthetic_reservations",
            "disposable_schema_dropped",
            "fin_apply_locked",
        ):
            with self.subTest(key=key):
                self.assertTrue(report[key])
        self.assertFalse(report["real_financial_database_connected"])
        self.assertEqual(report["production_database_mutations"], 0)

    def test_05_report_discloses_no_bank_details(self):
        dsn=os.environ.get("SBI_R20_DISPOSABLE_DSN")
        if not dsn:
            self.skipTest("Only GitHub isolated postgres service can run database integration")
        report=run_ephemeral_pg_probe(dsn)
        self.assertNotIn("SYN-MXP-001",repr(report))
        self.assertNotIn("SYN-PAY-001",repr(report))
        self.assertNotIn("SYNTHETIC ALPHA",repr(report))

if __name__=="__main__":
    unittest.main()
