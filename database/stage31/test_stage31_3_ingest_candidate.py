"""Stage 31.3 synthetic data QA. Never connects to production database."""
import unittest
from invoice_source_schema import HEADERS_34, HEADERS_35, HEADERS_53
from stage31_2_schema_design import SOURCE_COLUMNS
from stage31_3_ingest_candidate import (
    build_invoice_review_candidate, preview_invoice_batch, rupees_to_paise
)
SHA = "a" * 64
SHEET = "Invoice Details."
HEADERS = {34:HEADERS_34,35:HEADERS_35,53:HEADERS_53}

def row(width=34, number="STAGE31-TEST-1", startrow=2):
    values=[""]*width
    lookup=SOURCE_COLUMNS[width]
    values[0]=values[7]="TEST BRANCH CUSTOMER"
    values[lookup["invoice_no"]]=number
    values[lookup["invoice_branch"]]="TEST CENTRE"
    values[lookup["month"]]="Mar-May 2026"
    values[lookup["invoice_date"]]="2026-07-11"
    values[lookup["branch_code_primary"]]="001505"
    if "branch_code_secondary" in lookup:
        values[lookup["branch_code_secondary"]]="001505"
    values[lookup["taxable_amount"]]="1000.00"
    values[lookup["cgst"]]="90.00"
    values[lookup["sgst"]]="90.00"
    values[lookup["total_bill_amount"]]="1180.00"
    return {"source_row":startrow,
            "original_values":values,
            "original_headers":list(HEADERS[width])}

def candidate(r):
    return build_invoice_review_candidate(r,SHA,SHEET,r["source_row"])

class ExactConversion(unittest.TestCase):
    def test_decimal_paise_no_float_rounding(self):
        self.assertEqual(rupees_to_paise("113.84"),11384)
        self.assertEqual(rupees_to_paise("0.01"),1)
        self.assertEqual(rupees_to_paise("1.2"),120)
        self.assertEqual(rupees_to_paise("1"),100)
    def test_zero_is_valid_for_zero_tax_component(self):
        self.assertEqual(rupees_to_paise("0"),0)
    def test_negative_excess_precision_float_and_grouping_rejected(self):
        for x in ("-1","1.234",1.23,"1,000.00"," 1.00","1e3","NaN",".75"):
            with self.subTest(value=x):
                with self.assertRaises(ValueError):rupees_to_paise(x)
    def test_unreasonable_precision_range(self):
        with self.assertRaises(ValueError):rupees_to_paise("100000000000000.00")

class CandidateSafety(unittest.TestCase):
    def test_34_35_53_invoice_source_to_paise_candidate(self):
        for width in (34,35,53):
            with self.subTest(width=width):
                c=candidate(row(width))
                self.assertEqual(c["source_column_count"],width)
                self.assertEqual(c["candidate_fields"]["gross_paise"],118000)
                self.assertEqual(c["candidate_fields"]["taxable_paise"],100000)
                self.assertEqual(c["candidate_fields"]["cgst_paise"],9000)
                self.assertEqual(c["candidate_fields"]["sgst_paise"],9000)
                self.assertEqual(c["candidate_fields"]["invoice_date"],"2026-07-11")
                self.assertEqual(c["candidate_fields"]["service_period_original"],"Mar-May 2026")
                self.assertEqual(c["candidate_fields"]["sol_id"],"001505")
                self.assertFalse(c["production_write_authorized"])
    def test_duplicate_client_columns_are_not_automatically_resolved(self):
        c=candidate(row())
        self.assertIn("BRANCH_ID_AND_VERIFIED_CLIENT_NAME_MAPPING_NOT_APPROVED",c["review_flags"])
    def test_source_receipt_foreign_key_required(self):
        self.assertIn("SOURCE_ROW_FOREIGN_KEY_RECEIPT_NOT_INTEGRATED",candidate(row())["review_flags"])
    def test_inconsistent_gross_not_silently_repaired(self):
        r=row()
        r["original_values"][SOURCE_COLUMNS[34]["total_bill_amount"]]="1100.00"
        self.assertIn("GROSS_NOT_EQUAL_TAXABLE_PLUS_GST_REQUIRE_SOURCE_REVIEW",candidate(r)["review_flags"])
        self.assertEqual(candidate(r)["candidate_fields"]["gross_paise"],110000)
    def test_zero_or_missing_sol_flagged_not_invented(self):
        r=row()
        r["original_values"][SOURCE_COLUMNS[34]["branch_code_primary"]]=""
        c=candidate(r)
        self.assertIsNone(c["candidate_fields"]["sol_id"])
        self.assertIn("SOL_SOURCE_NOT_VERIFIED",c["review_flags"])
    def test_conflicting_branch_codes_rejected_for_review(self):
        for width in (35,53):
            r=row(width)
            r["original_values"][SOURCE_COLUMNS[width]["branch_code_secondary"]]="00999"
            self.assertIn("CONFLICTING_OR_SECONDARY_ORIGINAL_BRANCH_CODE_REVIEW",
                          candidate(r)["review_flags"])
    def test_duplicate_existing_invoice_cannot_overwrite(self):
        with self.assertRaisesRegex(ValueError,"EXISTING_INVOICE"):
            build_invoice_review_candidate(row(),SHA,SHEET,2,{"STAGE31-TEST-1"})
    def test_missing_source_checksum_denied(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_WORKBOOK_SHA"):
            build_invoice_review_candidate(row(),"",SHEET,2)
    def test_original_source_row_mismatch_denied(self):
        with self.assertRaisesRegex(ValueError,"ORIGINAL_SOURCE_ROW_MISMATCH"):
            build_invoice_review_candidate(row(),SHA,SHEET,99)
    def test_unapproved_sheet_denied(self):
        with self.assertRaisesRegex(ValueError,"VERIFIED_ORIGINAL_INVOICE_SHEET"):
            build_invoice_review_candidate(row(),SHA,"PAYMNENT.",2)
    def test_ambiguous_date_requires_review(self):
        r=row()
        r["original_values"][SOURCE_COLUMNS[34]["invoice_date"]]="07/11/26"
        c=candidate(r)
        self.assertIsNone(c["candidate_fields"]["invoice_date"])
        self.assertIn("INVOICE_DATE_REVIEW_REQUIRED",c["review_flags"])
    def test_valid_indian_date_parsed_exactly(self):
        r=row()
        r["original_values"][SOURCE_COLUMNS[34]["invoice_date"]]="11/07/2026"
        self.assertEqual(candidate(r)["candidate_fields"]["invoice_date"],"2026-07-11")
    def test_source_fingerprint_unique_by_row_and_file(self):
        a=candidate(row(34,startrow=2))["source_identity_fingerprint"]
        b=candidate(row(34,startrow=3))["source_identity_fingerprint"]
        self.assertNotEqual(a,b)
        self.assertEqual(a,candidate(row(34,startrow=2))["source_identity_fingerprint"])
        c=build_invoice_review_candidate(row(), "b"*64,SHEET,2)
        self.assertNotEqual(a,c["source_identity_fingerprint"])
    def test_batch_duplicate_rejects_whole_batch(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_IN_UPLOADED"):
            preview_invoice_batch([row(startrow=2),row(startrow=3)],SHA,SHEET)
    def test_payment_source_values_never_imported_as_payment(self):
        r=row(53)
        r["original_values"][20]="FAKE PAYMENT RECEIVED"
        c=candidate(r)
        self.assertNotIn("payment_received",c["candidate_fields"])
        self.assertNotIn("credit_paise",c["candidate_fields"])
        self.assertFalse(c["financial_engine_enabled"])
    def test_invalid_money_does_not_produce_hidden_zero(self):
        r=row()
        r["original_values"][SOURCE_COLUMNS[34]["cgst"]]="1.234"
        c=candidate(r)
        self.assertIsNone(c["candidate_fields"]["cgst_paise"])
        self.assertIn("UNVERIFIED_CGST",c["review_flags"])
    def test_unapproved_column_width_rejected(self):
        r=row()
        r["original_values"].append("x")
        with self.assertRaises(ValueError):candidate(r)
    def test_valid_batch_is_still_not_authorized(self):
        result=preview_invoice_batch([row(startrow=2),row(number="STAGE31-TEST-2",startrow=3)],SHA,SHEET)
        self.assertEqual(result["total"],2)
        self.assertFalse(result["production_write_authorized"])
        self.assertEqual(result["status"],"REVIEW_REQUIRED_NO_PRODUCTION_WRITES")

if __name__=="__main__":
    unittest.main(verbosity=2)
