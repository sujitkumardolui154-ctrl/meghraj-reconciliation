"""Stage 31: offline regression of existing invoice layout + new payment preview."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from invoice_source_schema import (
    HEADERS_34,HEADERS_35,HEADERS_53,row_layout,
    sheet_layout,invoice_number,export_values_53
)
from invoice_import_rules import classify_rows
from payment_evidence_contract import (
    preview_payment_rows,validate_evidence_headers,FIXED_PAYMENT_HEADERS
)

def invoice_row(headers, invoice_no="MXP21569", width=None):
    width=width or len(headers)
    values=[""]*width
    idx={34:9,35:10,53:12}[width]
    values[idx]=invoice_no
    return {"source_row":2,
            "original_headers":list(headers),
            "original_values":values,
            "original_cell_types":["s"]*width}

class InvoiceContractTests(unittest.TestCase):
    def test_exact_approved_header_widths(self):
        self.assertEqual((len(HEADERS_34),len(HEADERS_35),len(HEADERS_53)),(34,35,53))
        self.assertEqual(sheet_layout("Invoice Details.",list(HEADERS_34)),(34,9))
        self.assertEqual(sheet_layout("Invoice Details.",list(HEADERS_35)),(35,10))
        self.assertEqual(sheet_layout("Original snapshot",list(HEADERS_53)),(53,12))
        self.assertIsNone(sheet_layout("PAYMNENT.",list(HEADERS_34)))
        self.assertIsNone(sheet_layout("Invoice Details.",list(reversed(HEADERS_34))))
    def test_invoice_number_and_full_source_value_preservation(self):
        for headers in (HEADERS_34,HEADERS_35,HEADERS_53):
            with self.subTest(width=len(headers)):
                r=invoice_row(headers)
                self.assertEqual(invoice_number(r),"MXP21569")
                self.assertEqual(row_layout(r)[0],len(headers))
                self.assertEqual(len(export_values_53(r)),53)
                self.assertEqual(export_values_53(r)[12],"MXP21569")
    def test_second_branch_code_is_preserved(self):
        r=invoice_row(HEADERS_35)
        r["original_values"][8]="99922"
        self.assertEqual(export_values_53(r)[10],"99922")
    def test_duplicate_in_single_upload_rejected_for_both_rows(self):
        r1=invoice_row(HEADERS_34)
        r2=invoice_row(HEADERS_34)
        r2["source_row"]=3
        result=classify_rows([r1,r2],set())
        self.assertFalse(result["accepted"])
        self.assertEqual(len(result["rejected"]),2)
        self.assertTrue(all("DUPLICATE_IN_UPLOADED_FILE" in x["reasons"] for x in result["rejected"]))
    def test_existing_invoice_rejected(self):
        result=classify_rows([invoice_row(HEADERS_34)],{"MXP21569"})
        self.assertFalse(result["accepted"])
        self.assertIn("INVOICE_ALREADY_EXISTS",result["rejected"][0]["reasons"])
    def test_invoice_whitespace_rejected(self):
        result=classify_rows([invoice_row(HEADERS_34," MXP21569")],set())
        self.assertIn("INVOICE_NUMBER_HAS_SURROUNDING_SPACES",
                      result["rejected"][0]["reasons"])
    def test_missing_invoice_rejected(self):
        result=classify_rows([invoice_row(HEADERS_34,"")],set())
        self.assertIn("MISSING_OR_INVALID_INVOICE_NUMBER",
                      result["rejected"][0]["reasons"])
    def test_wrong_row_header_rejected(self):
        r=invoice_row(HEADERS_34)
        r["original_headers"]=["unapproved"]*34
        result=classify_rows([r],set())
        self.assertIn("INVALID_SOURCE_COLUMN_ROW",result["rejected"][0]["reasons"])

class PaymentContractTests(unittest.TestCase):
    def test_exact_payment_headers(self):
        self.assertTrue(validate_evidence_headers(FIXED_PAYMENT_HEADERS))
        with self.assertRaisesRegex(ValueError,"PAYMENT_HEADER_MISMATCH"):
            validate_evidence_headers(("Description","Credit Amount","SOL ID"))
    def test_payment_accepts_leading_zero_sol_but_never_financial_apply(self):
        result=preview_payment_rows(FIXED_PAYMENT_HEADERS,[("Aug 2026 postage","001505","113.84")])
        self.assertEqual(result["ready_for_source_review"],1)
        self.assertFalse(result["database_changed"])
        self.assertFalse(result["financial_engine_enabled"])
        self.assertEqual(result["results"][0]["status"],"READY_FOR_SOURCE_REVIEW")
    def test_payment_duplicate_requires_bank_row_identity(self):
        result=preview_payment_rows(FIXED_PAYMENT_HEADERS,
                                    [("AUG-26 posting","1505","113.84")]*2)
        self.assertEqual(result["ready_for_source_review"],0)
        self.assertEqual(result["rejected"],2)
    def test_payment_invalid_negative_zero_or_excess_precision(self):
        result=preview_payment_rows(FIXED_PAYMENT_HEADERS,
                                    [("A","1505","-1"),("B","1505","0"),
                                     ("C","1505","1.234")])
        self.assertEqual(result["rejected"],3)
    def test_payment_blanks_or_numeric_sol_not_silently_accepted(self):
        result=preview_payment_rows(FIXED_PAYMENT_HEADERS,
                                    [("","1505","113.84"),("A",1505,"113.84"),
                                     ("B","","113.84")])
        self.assertEqual(result["rejected"],3)
    def test_payment_limit(self):
        with self.assertRaisesRegex(ValueError,"PAYMENT_ROW_LIMIT_EXCEEDED"):
            preview_payment_rows(FIXED_PAYMENT_HEADERS,[("A","1","1")]*20001)

if __name__=="__main__":
    unittest.main(verbosity=2)
