"""DB-R31.1 synthetic metadata only; no AWS/database connection."""
import unittest
from db_r31_catalog_contract import catalog_to_contract

SAMPLE = """DB_R31_CATALOG_BEGIN|sbi_reconciliation_main
COLUMN|import_batches|1|id|uuid|NULLABLE=NO|DEFAULT=NONE
COLUMN|import_batches|2|source_system|text|NULLABLE=NO|DEFAULT=NONE
COLUMN|import_batches|3|source_kind|text|NULLABLE=NO|DEFAULT=NONE
COLUMN|import_batches|4|source_sha256|text|NULLABLE=NO|DEFAULT=NONE
COLUMN|payment_source_rows|1|id|uuid|NULLABLE=NO|DEFAULT=NONE
COLUMN|payment_source_rows|2|batch_id|uuid|NULLABLE=NO|DEFAULT=NONE
COLUMN|payment_source_rows|3|source_row_number|int4|NULLABLE=NO|DEFAULT=NONE
COLUMN|payment_source_rows|4|original_values|jsonb|NULLABLE=NO|DEFAULT=NONE
COLUMN|payment_source_rows|5|row_sha256|text|NULLABLE=NO|DEFAULT=NONE
COLUMN|payments|1|id|uuid|NULLABLE=NO|DEFAULT=NONE
COLUMN|payments|2|source_row_id|uuid|NULLABLE=NO|DEFAULT=NONE
COLUMN|payments|3|description|text|NULLABLE=NO|DEFAULT=NONE
COLUMN|payments|4|sol_id|text|NULLABLE=YES|DEFAULT=NONE
COLUMN|payments|5|credit_paise|int8|NULLABLE=NO|DEFAULT=NONE
OWNER_FIELD|import_batches|owner_uid=MISSING|tenant_id=MISSING
GLOBAL_FILE_SHA_UNIQUE|PRESENT_REVIEW_REQUIRED_FOR_MULTITENANT
REPORT_ROLE|payments|SELECT=true|INSERT=false|UPDATE=false|DELETE=false
DB_R31_CATALOG_END|READ_ONLY"""

class ContractTests(unittest.TestCase):
    def test_base_contract(self):
        result=catalog_to_contract(SAMPLE)
        self.assertFalse(result["production_financial_writes"])
        self.assertTrue(result["no_new_primary_db"])
        self.assertTrue(result["global_file_sha_unique_observed"])
    def test_owner_scope_missing(self):
        self.assertFalse(catalog_to_contract(SAMPLE)["owner_scoped_batch_column_observed"])
    def test_owner_column_observed(self):
        source=SAMPLE.replace("owner_uid=MISSING","owner_uid=PRESENT")
        self.assertTrue(catalog_to_contract(source)["owner_scoped_batch_column_observed"])
    def test_report_write_grant_danger(self):
        source=SAMPLE.replace("INSERT=false","INSERT=true")
        self.assertEqual(catalog_to_contract(source)["report_role_write_grants"],["payments"])
    def test_wrong_database_rejected(self):
        with self.assertRaises(ValueError):
            catalog_to_contract(SAMPLE.replace("sbi_reconciliation_main","postgres"))
    def test_incomplete_catalog_rejected(self):
        with self.assertRaises(ValueError):
            catalog_to_contract(SAMPLE.replace("DB_R31_CATALOG_END|READ_ONLY",""))
    def test_missing_target_column(self):
        source="\n".join(x for x in SAMPLE.splitlines() if "|credit_paise|" not in x)
        self.assertIn("credit_paise",catalog_to_contract(source)["missing_required_source_columns"]["payments"])

if __name__=="__main__":
    unittest.main(verbosity=2)
