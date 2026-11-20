"""D-022 synthetic combined review: no financial data, no network, no writes."""
import copy
import importlib.util
from pathlib import Path
import unittest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("offline_review", root / "offline_review.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from invoice_source_schema import HEADERS_53, HEADERS_34


def source(number="MXP-SYNTH-001", *, payment="123.00",
           marker_s="", credit_note=False, headers=None):
    headers = list(headers or HEADERS_53)
    width = len(headers)
    values = [""] * width
    invoice_i, payment_i = (12, 20) if width == 53 else (9, 17)
    values[invoice_i] = number
    values[payment_i] = "CREDIT NOTE" if credit_note else payment
    values[18] = marker_s
    return {
        "source_sheet": "Invoice Details.",
        "original_headers": headers,
        "original_values": values,
        "original_cell_types": ["s"] * width,
    }


def bank(credit="123.00"):
    row = [""] * 12
    row[8] = credit
    return row


class D022CombinedOffline(unittest.TestCase):
    def test_valid_sources_never_auto_allocate(self):
        invoices, payments = [source()], [bank()]
        original = copy.deepcopy([invoices, payments])
        out = module.combined_offline_review(invoices, payments)
        self.assertEqual(out["status"], "REVIEW_REQUIRED")
        self.assertEqual(out["payment_allocation"], "NOT_EXECUTED")
        self.assertEqual(out["bank_credit_classification"]["VALID_CREDIT"], 1)
        self.assertFalse(out["approved_for_settlement"])
        self.assertFalse(out["financial_write_performed"])
        self.assertEqual([invoices, payments], original)

    def test_duplicate_source_invoice_both_held(self):
        out = module.combined_offline_review([source(), source()], [bank()])
        self.assertEqual(out["duplicate_source_invoice_groups"], 1)
        self.assertEqual(out["invoice_review_counts"]["DUPLICATE_INVOICE"], 2)

    def test_s_marker_excluded_not_allocated(self):
        out = module.combined_offline_review([source(marker_s="PROTECTED")], [bank()])
        self.assertEqual(out["invoice_review_counts"]["COLUMN_S_EXCLUDED"], 1)
        self.assertEqual(out["payment_allocation"], "NOT_EXECUTED")

    def test_credit_note_token_held(self):
        out = module.combined_offline_review([source(credit_note=True)], [bank()])
        self.assertEqual(out["credit_note_tagged_for_review"], 1)
        self.assertEqual(out["invoice_review_counts"]["CREDIT_NOTE_REVIEW_REQUIRED"], 1)

    def test_bad_credit_never_treated_positive(self):
        for invalid in ("-5", "NaN", "=10", "abc"):
            with self.subTest(invalid=invalid):
                out = module.combined_offline_review([source()], [bank(invalid)])
                self.assertEqual(out["bank_credit_classification"]["INVALID_CREDIT"], 1)

    def test_credit_in_column_i_not_another_column(self):
        p = bank("")
        p[7] = "999999"
        out = module.combined_offline_review([source()], [p])
        self.assertEqual(out["bank_credit_classification"]["NO_CREDIT"], 1)

    def test_34_column_credit_note_not_claimed_verified(self):
        out = module.combined_offline_review([source(headers=HEADERS_34)], [bank()])
        self.assertEqual(out["invoice_review_counts"]["CREDIT_NOTE_34_COLUMN_ADAPTER_NOT_VERIFIED"], 1)

    def test_bad_invoice_sheet_denied(self):
        row = source()
        row["source_sheet"] = "Other"
        with self.assertRaises(module.ReviewInputError):
            module.combined_offline_review([row], [bank()])

    def test_bad_header_denied(self):
        row = source()
        row["original_headers"] = ["WRONG"] * 53
        with self.assertRaises((ValueError, module.ReviewInputError)):
            module.combined_offline_review([row], [bank()])

    def test_invalid_bank_source_schema_denied(self):
        with self.assertRaises(module.ReviewInputError):
            module.combined_offline_review([source()], [[""] * 11])

    def test_missing_source_denied(self):
        with self.assertRaises(module.ReviewInputError):
            module.combined_offline_review([source()], [])

    def test_gst_input_triplet_denied(self):
        with self.assertRaises(module.ReviewInputError):
            module.combined_offline_review([source()], [bank()], gst_sources=[])

    def test_empty_gst_triplet_never_certifies_parity(self):
        out = module.combined_offline_review(
            [source()], [bank()], gst_sources=[], gst_master=[], original_gst_records=[])
        self.assertEqual(out["gst_status"], "PRIVATE_ORIGINAL_PARITY_NOT_VERIFIED")
        self.assertEqual(out["source_independent_parity"], "NOT_VERIFIED")
        self.assertFalse(out["aws_deployment_performed"])

if __name__ == "__main__":
    unittest.main()
