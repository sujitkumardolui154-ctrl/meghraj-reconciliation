"""D-001 independent original-source comparison and batch uniqueness tests.

Synthetic records only. Real-source provenance must be established by private adapter.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gst_preview import gst_preview
from gst_batch_preview import gst_batch_preview

MASTER = [{"Official Branch Name":"TEST BRANCH","SOL ID":"01234","Search Aliases":"TEST ALIAS"}]
CHECKS = {k: True for k in (
    "invoice_number","invoice_branch","client_identity","service_month",
    "invoice_date","taxable_amount","cgst","sgst","source_gross",
)}

def invoice(no="MXPTEST001"):
    return {"fy":"2026-27","original_branch_name":"TEST ALIAS",
            "invoice_branch":"TEST ORIGIN","invoice_no":no,
            "service_month":"October 2026","invoice_date":"2026-11-01",
            "verified_client_class":"SBI_BANK","taxable":"100.00",
            "cgst":"9.00","sgst":"9.00","source_gross":"118.00",
            "independent_source_checks":dict(CHECKS)}

def original(row):
    return {**row,"source_ref":"private-originals/test-fixture","source_sha256":"a"*64}

class ManualRectificationD001(unittest.TestCase):
    def test_fabricated_true_checks_cannot_verify_original(self):
        out = gst_preview(invoice(),MASTER)
        self.assertEqual(out["status"],"REVIEW_REQUIRED")
        self.assertIn("ORIGINAL_SOURCE_VERIFICATION_INCOMPLETE",out["flags"])
        self.assertEqual(out["values"][8],"") # GSTIN withheld until verified

    def test_independently_matched_source_is_review_preview_not_posting(self):
        row=invoice()
        out=gst_preview(row,MASTER,original_record=original(row))
        self.assertEqual(out["status"],"READY_FOR_REVIEW")
        self.assertEqual((out["values"][5],out["values"][7]),("01234","01234"))
        self.assertEqual(out["values"][13],"118.00")
        self.assertFalse(out["approved_for_posting"])
        self.assertFalse(out["financial_write_performed"])

    def test_wrong_service_month_is_blocked(self):
        row=invoice()
        actual=original(row)
        row["service_month"]="November 2026"
        self.assertIn("ORIGINAL_SOURCE_VERIFICATION_INCOMPLETE",
            gst_preview(row,MASTER,original_record=actual)["flags"])

    def test_amount_mismatch_is_blocked(self):
        row=invoice()
        actual=original(row)
        row["taxable"]="101.00"
        self.assertIn("ORIGINAL_SOURCE_VERIFICATION_INCOMPLETE",
            gst_preview(row,MASTER,original_record=actual)["flags"])

    def test_duplicate_in_input_flags_both_rows(self):
        a,b=invoice(),invoice()
        out=gst_batch_preview([a,b],MASTER,[original(a)])
        self.assertEqual(out["review_required"],2)
        self.assertTrue(all("DUPLICATE_INVOICE" in v["flags"] for v in out["rows"]))

    def test_duplicate_original_evidence_flags_row(self):
        a=invoice()
        out=gst_batch_preview([a],MASTER,[original(a),original(a)])
        self.assertIn("DUPLICATE_INVOICE",out["rows"][0]["flags"])
        self.assertEqual(out["review_required"],1)

    def test_missing_original_never_ready(self):
        out=gst_batch_preview([invoice()],MASTER,[])
        self.assertIn("ORIGINAL_SOURCE_VERIFICATION_INCOMPLETE",out["rows"][0]["flags"])

    def test_two_unique_invoices_pass_source_comparison(self):
        a,b=invoice("MXP001"),invoice("MXP002")
        out=gst_batch_preview([a,b],MASTER,[original(a),original(b)])
        self.assertEqual((out["row_count"],out["review_required"]),(2,0))

    def test_digest_metadata_must_be_64_hex(self):
        row=invoice()
        o=original(row);o["source_sha256"]="not-a-sha"
        self.assertEqual(gst_preview(row,MASTER,original_record=o)["status"],"REVIEW_REQUIRED")

    def test_no_mutation_of_either_source(self):
        a=invoice()
        o=original(a)
        before=(repr(a),repr(o))
        out=gst_batch_preview([a],MASTER,[o])
        self.assertEqual((repr(a),repr(o)),before)
        self.assertFalse(out["financial_write_performed"])

if __name__ == "__main__":
    unittest.main()
