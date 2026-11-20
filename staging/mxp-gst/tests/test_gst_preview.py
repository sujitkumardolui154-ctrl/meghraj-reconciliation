"""Synthetic GST preview regression; no real invoice data."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gst_preview import gst_preview

MASTER = [{"Official Branch Name": "TEST BRANCH", "SOL ID": "01234", "Search Aliases": "TEST ALIAS"}]
CHECKS = {k: True for k in (
    "invoice_number", "invoice_branch", "client_identity", "service_month",
    "invoice_date", "taxable_amount", "cgst", "sgst", "source_gross",
)}

def source():
    return {
        "fy": "2026-27", "original_branch_name": "TEST ALIAS",
        "invoice_branch": "TEST INVOICE ORIGIN", "invoice_no": "MXPTEST001",
        "service_month": "October 2026", "invoice_date": "2026-11-01",
        "verified_client_class": "SBI_BANK",
        "taxable": "100.00", "cgst": "9.00", "sgst": "9.00", "source_gross": "118.00",
        "independent_source_checks": dict(CHECKS),
    }

def original(record):
    return {**record, "source_ref": "private-original/test-only",
            "source_sha256": "a" * 64}

class PreviewTests(unittest.TestCase):
    def test_verified_preview_16_positional_and_non_mutating(self):
        record = source()
        before = repr(record)
        out = gst_preview(record, MASTER, original_record=original(record))
        self.assertEqual(out["status"], "READY_FOR_REVIEW")
        self.assertEqual(len(out["values"]), 16)
        self.assertEqual(out["values"][5], "01234")
        self.assertEqual(out["values"][7], "01234")
        self.assertEqual(out["values"][8], "19AAACS8577K3ZK")
        self.assertEqual(out["values"][13], "118.00")
        self.assertEqual(out["values"][15], "TEST ALIAS")
        self.assertEqual(repr(record), before)
        self.assertFalse(out["financial_write_performed"])
        self.assertFalse(out["approved_for_posting"])

    def test_missing_independent_check_never_ready(self):
        record = source()
        record["independent_source_checks"]["source_gross"] = False
        out = gst_preview(record, MASTER, original_record=original(record))
        self.assertEqual(out["status"], "REVIEW_REQUIRED")
        self.assertIn("ORIGINAL_SOURCE_VERIFICATION_INCOMPLETE", out["flags"])

    def test_duplicate_and_gross_mismatch_both_flagged(self):
        record = source()
        record["source_gross"] = "119.00"
        out = gst_preview(record, MASTER, seen_invoices={"MXPTEST001"})
        self.assertIn("DUPLICATE_INVOICE", out["flags"])
        self.assertIn("GROSS_MISMATCH", out["flags"])

    def test_unknown_sol_does_not_fake_client(self):
        record = source()
        record["original_branch_name"] = "UNKNOWN"
        out = gst_preview(record, MASTER)
        self.assertEqual(out["values"][5], "")
        self.assertEqual(out["values"][6], "")
        self.assertEqual(out["status"], "REVIEW_REQUIRED")

    def test_unverified_classification_has_no_gstin(self):
        record = source()
        record["verified_client_class"] = "OTHER"
        out = gst_preview(record, MASTER)
        self.assertEqual(out["values"][8], "")
        self.assertIn("GSTIN_CLASS_REVIEW_REQUIRED", out["flags"])

    def test_money_nan_and_float_rejected(self):
        for value in ("NaN", "Infinity", "-1.00", "1.234", 1.2):
            record = source()
            record["taxable"] = value
            out = gst_preview(record, MASTER)
            self.assertIn("INVALID_TAXABLE", out["flags"])

    def test_generation_location_blank_without_evidence(self):
        record = source()
        record["verified_generation_location"] = "TEST LOCATION"
        out = gst_preview(record, MASTER)
        self.assertEqual(out["values"][2], "")
        record["generation_location_verified"] = True
        self.assertEqual(gst_preview(record, MASTER)["values"][2], "TEST LOCATION")

if __name__ == "__main__":
    unittest.main()
