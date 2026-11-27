"""Read-only PostgreSQL source-discovery QA, synthetic invoice_qa ONLY."""
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/sbi_credit_note_history_catalog_preflight.py"
spec = importlib.util.spec_from_file_location("cn_history_catalog", SOURCE)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class ReadOnlyHistoryCatalogContract(unittest.TestCase):
    def test_empty_source_never_authorizes_issue(self):
        s = catalog.candidate_review(
            ["invoice_no", "invoice_date"], write_granted=False
        )
        self.assertIn("gstin", s["canonical_fields_missing"])
        self.assertFalse(s["source_approved_for_credit_note_issue"])
        self.assertFalse(s["role_can_modify_relation"])

    def test_full_columns_still_need_duplicate_credit_tax_controls(self):
        columns = catalog.CANONICAL_FIELDS | catalog.ATTESTED_FIELDS
        s = catalog.candidate_review(list(columns),write_granted=False)
        self.assertEqual(s["canonical_fields_missing"],[])
        self.assertEqual(s["attested_fields_missing"],[])
        self.assertFalse(s["source_approved_for_credit_note_issue"])

    def test_writable_role_flagged_not_treated_as_readonly(self):
        s = catalog.candidate_review(
            ["invoice_no","taxable"],write_granted=True
        )
        self.assertTrue(s["role_can_modify_relation"])
        self.assertFalse(s["source_approved_for_credit_note_issue"])

    def test_probe_rejects_missing_connection(self):
        with self.assertRaises(catalog.HistorySourceProbeError):
            catalog.run_schema_probe("")


@unittest.skipUnless(os.environ.get("SBI_INVOICE_GST_TEST_DSN"),
                     "Isolated PostgreSQL 16 not configured")
class IsolatedHistoryCatalogPostgres(unittest.TestCase):
    def test_qa_database_catalog_readonly_and_never_authorized(self):
        r=catalog.run_schema_probe(
            os.environ["SBI_INVOICE_GST_TEST_DSN"],
            allow_isolated_qa=True
        )
        self.assertEqual(r["database"],"invoice_qa")
        self.assertTrue(r["read_only_transaction"])
        self.assertEqual(r["query_scope"],"SCHEMA_METADATA_ONLY_NO_FINANCIAL_ROWS")
        self.assertFalse(r["financial_writes"])
        self.assertFalse(r["credit_note_history_issuance_allowed"])
        self.assertFalse(r["authoritative_invoice_relation_verified"])
        self.assertEqual(len(r["catalog_sha256"]),64)

    def test_same_database_is_rejected_outside_qa_gate(self):
        with self.assertRaises(catalog.HistorySourceProbeError):
            catalog.run_schema_probe(os.environ["SBI_INVOICE_GST_TEST_DSN"])
