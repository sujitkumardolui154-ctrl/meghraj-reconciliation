"""R15: synthetic-only, no bank data, no DB and no financial mutations."""
import hashlib
import io
import sys
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))
from sbi_r15_financial_source_preflight import (
    inspect_original_workbook, SourceContractError,
)


def fixture(*, include_payment=True, include_invoice=True):
    w = Workbook()
    default = w.active
    w.remove(default)
    if include_invoice:
        i = w.create_sheet("Invoice Details.")
        for n in range(1, 35):
            i.cell(1, n, f"ORIGINAL_{n}")
        i.cell(2, 19, None)      # blank S is candidate only, not OK
        i.cell(2, 34, "preserved")
        i.cell(3, 19, "PAID")    # nonblank S must exclude
        i.cell(3, 34, "preserved")
        i.cell(4, 19, 0)         # nonblank numeric zero also excludes
        i.cell(4, 34, "preserved")
    if include_payment:
        p = w.create_sheet("PAYMNENT")
        p["A1"] = "Description"
        p["H1"] = "Debit"
        p["I1"] = "Credit"
        p["J1"] = "Balance"
        p["K1"] = "Record For Me"
        p["H2"] = 9000
        p["I2"] = 113.84
        p["I3"] = 0
        p["I4"] = -1
        p["I5"] = "not numeric"
        p["I6"] = "=5+5"
    result = io.BytesIO()
    w.save(result)
    return w, result.getvalue()


def encode(w):
    stream = io.BytesIO()
    w.save(stream)
    return stream.getvalue()


class OriginalWorkbookPreflight(unittest.TestCase):
    def test_01_normal_source_is_diagnostic_only(self):
        _, raw = fixture()
        report = inspect_original_workbook(raw)
        self.assertEqual(report["payment_credit_source"], "PAYMNENT!I")
        self.assertEqual(report["bank_credit_evidence_counts"], {
            "positive_unallocated": 1, "zero": 1, "blank": 0,
            "negative_review": 1, "review": 2,
        })
        self.assertEqual(report["invoice_s_blank_candidate_rows"], 1)
        self.assertEqual(report["invoice_s_nonblank_excluded_rows"], 2)
        self.assertEqual(report["financial_allocation_executed"], False)
        self.assertEqual(report["financial_database_connected"], False)
        self.assertEqual(report["financial_apply_locked"], True)
        self.assertEqual(report["safe_for_automatic_settlement"], False)

    def test_02_no_fresh_workbook_is_refused(self):
        with self.assertRaisesRegex(SourceContractError, "NEW_XLSX_SOURCE_REQUIRED"):
            inspect_original_workbook(b"")

    def test_03_non_xlsx_bytes_are_refused(self):
        with self.assertRaisesRegex(SourceContractError, "NOT_A_VALID_XLSX_ARCHIVE"):
            inspect_original_workbook(b"not an xlsx")

    def test_04_wrong_sheet_is_refused(self):
        _, raw = fixture(include_payment=False)
        with self.assertRaisesRegex(SourceContractError, "WRONG_INPUT"):
            inspect_original_workbook(raw)

    def test_05_wrong_invoice_sheet_is_refused(self):
        _, raw = fixture(include_invoice=False)
        with self.assertRaisesRegex(SourceContractError, "WRONG_INPUT"):
            inspect_original_workbook(raw)

    def test_06_exact_credit_I_header_locked(self):
        w, _ = fixture()
        w["PAYMNENT"]["I1"] = "Debit"
        with self.assertRaisesRegex(SourceContractError, "H_TO_K_HEADER_MISMATCH"):
            inspect_original_workbook(encode(w))

    def test_07_original_L_must_remain_blank_header(self):
        w, _ = fixture()
        w["PAYMNENT"]["L1"] = "New Model"
        with self.assertRaisesRegex(SourceContractError, "L_HEADER_NOT_BLANK"):
            inspect_original_workbook(encode(w))

    def test_08_invoice_must_have_thirty_four_original_columns(self):
        w, _ = fixture()
        i = w["Invoice Details."]
        i.delete_cols(34)
        with self.assertRaisesRegex(SourceContractError, "A_TO_AH_MISSING"):
            inspect_original_workbook(encode(w))

    def test_09_source_hash_not_silently_changed(self):
        _, raw = fixture()
        before = hashlib.sha256(raw).hexdigest()
        report = inspect_original_workbook(raw, expected_sha256=before)
        self.assertEqual(report["source_sha256"], before)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), before)

    def test_10_wrong_expected_digest_refused(self):
        _, raw = fixture()
        with self.assertRaisesRegex(SourceContractError, "SOURCE_SHA256_MISMATCH"):
            inspect_original_workbook(raw, expected_sha256="0" * 64)

    def test_11_H_debit_does_not_turn_into_credit(self):
        w, _ = fixture()
        w["PAYMNENT"]["I2"] = None
        report = inspect_original_workbook(encode(w))
        self.assertEqual(report["bank_credit_evidence_counts"]["positive_unallocated"], 0)
        self.assertEqual(report["bank_credit_evidence_counts"]["blank"], 1)

    def test_12_formula_credit_is_review_not_amount(self):
        w, _ = fixture()
        w["PAYMNENT"]["I2"] = "=SUM(A2:A3)"
        report = inspect_original_workbook(encode(w))
        self.assertEqual(report["bank_credit_evidence_counts"]["review"], 3)

    def test_13_original_invoice_S_numeric_zero_is_still_protected(self):
        w, _ = fixture()
        w["Invoice Details."]["S4"] = 0
        report = inspect_original_workbook(encode(w))
        self.assertEqual(report["invoice_s_nonblank_excluded_rows"], 2)

    def test_14_extra_original_sheet_is_retained_and_not_written(self):
        w, _ = fixture()
        w.create_sheet("OTHER ORIGINAL")
        raw = encode(w)
        report = inspect_original_workbook(raw)
        self.assertTrue(report["original_sheet_order_preserved"])
        self.assertEqual(report["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(w.sheetnames, ["Invoice Details.", "PAYMNENT", "OTHER ORIGINAL"])

    def test_15_three_column_convenience_receipt_not_authoritative(self):
        w = Workbook()
        p = w.active
        p.title = "PAYMENT EVIDENCE"
        p.append(["Description", "SOL ID", "Credit Amount"])
        p.append(["SYNTHETIC", "0001", 100])
        with self.assertRaisesRegex(SourceContractError, "WRONG_INPUT"):
            inspect_original_workbook(encode(w))

    def test_16_original_file_never_assigned_reconciliation_status(self):
        _, raw = fixture()
        report = inspect_original_workbook(raw)
        self.assertNotIn("OK", str(report))
        self.assertNotIn("SUSPENSE", str(report))
        self.assertNotIn("Duplicate Payment", str(report))
        self.assertFalse(report["financial_statuses_written"])


if __name__ == "__main__":
    unittest.main()
