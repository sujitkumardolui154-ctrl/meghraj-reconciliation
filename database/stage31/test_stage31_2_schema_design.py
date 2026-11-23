"""Stage 31.2 synthetic read-only metadata mapping regression tests."""
import unittest
from stage31_2_schema_design import (
 SOURCE_COLUMNS,HEADERS,TARGET_CANDIDATES, METADATA_CANDIDATES,
 catalog_to_mapping,render_summary,assert_safe_report
)

def catalog():
    return {
        "database":"sbi_reconciliation_main",
        "tables":{
            "invoices":[
                {"name":"invoice_no","data_type":"text","nullable":"NO"},
                {"name":"invoice_branch","data_type":"text","nullable":"YES"},
                {"name":"branch_code","data_type":"text","nullable":"YES"},
                {"name":"taxable_amount","data_type":"numeric","nullable":"YES"},
                {"name":"cgst","data_type":"numeric","nullable":"YES"},
                {"name":"sgst","data_type":"numeric","nullable":"YES"},
                {"name":"source_row","data_type":"integer","nullable":"YES"},
            ],
            "payments":[
                {"name":"description","data_type":"text","nullable":"YES"},
                {"name":"sol_id","data_type":"text","nullable":"YES"},
                {"name":"credit_amount","data_type":"numeric","nullable":"YES"},
            ],
        },
        "indexes":[
            {"table":"invoices","index":"invoices_unique_invoice_no",
             "unique":True,
             "definition":"CREATE UNIQUE INDEX invoices_unique_invoice_no ON sbi.invoices USING btree (invoice_no)"}
        ],
    }

class SourceAndMappingContract(unittest.TestCase):
    def test_all_approved_invoice_widths_maintained(self):
        self.assertEqual(tuple(sorted(SOURCE_COLUMNS)),(34,35,53))
        for width,keys in SOURCE_COLUMNS.items():
            self.assertEqual(len(HEADERS[width]),width)
            self.assertEqual(HEADERS[width][keys["invoice_no"]],"Invoice No")
    def test_35_second_branch_code_position(self):
        self.assertEqual(SOURCE_COLUMNS[35]["branch_code_secondary"],8)
        self.assertEqual(HEADERS[35][8],"Branch Code")
    def test_53_secondary_branch_code_not_model_sol(self):
        self.assertEqual(SOURCE_COLUMNS[53]["branch_code_secondary"],10)
        self.assertNotEqual(SOURCE_COLUMNS[53]["branch_code_secondary"],8)
        self.assertEqual(HEADERS[53][8],"Model SOL ID")
    def test_amount_header_positions_34_35_53(self):
        for width in (34,35,53):
            for name,header in (("taxable_amount","Taxable Amount"),
                                ("cgst","CGST"),("sgst","SGST"),
                                ("total_bill_amount","Total Bill Amount")):
                self.assertEqual(HEADERS[width][SOURCE_COLUMNS[width][name]],header)
    def test_sample_catalog_requiring_human_review(self):
        report=catalog_to_mapping(catalog())
        self.assertEqual(report["status"],"REVIEW_REQUIRED_NO_WRITE_AUTHORITY")
        self.assertTrue(assert_safe_report(report))
        self.assertIn("invoices",report["table_names"])
    def test_candidate_mapping_never_approves_itself(self):
        report=catalog_to_mapping(catalog())
        invoice=next(r for r in report["invoice_source_ordinals"]["34"]
                     if r["logical_field"]=="invoice_no")
        self.assertEqual(invoice["database_candidates"][0]["target_name"],"invoice_no")
        self.assertEqual(invoice["binding_state"],"UNAPPROVED_REVIEW_REQUIRED")
    def test_bank_identity_not_fabricated(self):
        report=catalog_to_mapping(catalog())
        self.assertEqual(report["payment_3_field_template"],"PREVIEW_ONLY_NO_BANK_TRANSACTION_ID")
        self.assertTrue(any("BANK_PAYMNENT" in r for r in report["required_reviews"]))
    def test_reject_wrong_db(self):
        data=catalog();data["database"]="other_database"
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_DATABASE"):
            catalog_to_mapping(data)
    def test_reject_missing_payments_table(self):
        data=catalog();data["tables"].pop("payments")
        with self.assertRaisesRegex(ValueError,"REQUIRED_FINANCIAL_TABLES_MISSING"):
            catalog_to_mapping(data)
    def test_no_unique_index_does_not_claim_readiness(self):
        data=catalog();data["indexes"]=[]
        report=catalog_to_mapping(data)
        self.assertEqual(report["invoice_unique_indexes_needing_review"],[])
        self.assertIn("NO_UNIQUE_INVOICE_INDEX_VISIBLE_REVIEW_SCHEMA_CONSTRAINTS",report["required_reviews"])
    def test_report_cannot_authorize_financial_write(self):
        report=catalog_to_mapping(catalog())
        report["production_database_writes_authorized"]=True
        with self.assertRaisesRegex(ValueError,"REPORT_CANNOT_AUTHORIZE_WRITES"):
            assert_safe_report(report)
    def test_report_cannot_enable_reconciliation(self):
        report=catalog_to_mapping(catalog())
        report["financial_engine_enabled"]=True
        with self.assertRaisesRegex(ValueError,"FINANCIAL_ENGINE_MUST_STAY_OFF"):
            assert_safe_report(report)
    def test_duplicate_column_names_fail(self):
        data=catalog()
        data["tables"]["invoices"].append(
            {"name":"invoice_no","data_type":"numeric","nullable":"YES"})
        with self.assertRaisesRegex(ValueError,"INVALID_OR_DUPLICATED_INVOICE_COLUMN"):
            catalog_to_mapping(data)
    def test_mapping_summary_contains_only_schema_metadata(self):
        summary=render_summary(catalog_to_mapping(catalog()))
        self.assertIn("STAGE31_2_FIELD_MAP_APPROVAL=REVIEW_REQUIRED",summary)
        self.assertNotIn("113.84",summary)
        self.assertNotIn("MXP21569",summary)
    def test_no_automatic_client_name_binding(self):
        self.assertNotIn("client_name",TARGET_CANDIDATES)
        for width in (34,35,53):
            self.assertEqual(HEADERS[width].count("Client Name"),2)

if __name__=="__main__":
    unittest.main(verbosity=2)
