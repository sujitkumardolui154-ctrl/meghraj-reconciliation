"""Synthetic exact-header A03 audit; no private or live report data."""
from __future__ import annotations

import csv
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_report_headers_audit", ROOT / "tools" / "sbi_report_headers_audit.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
SOURCE = json.loads(
    (ROOT / "backend_source" / "invoice_import_contract.json").read_text(encoding="utf-8")
)["headers"]
V218 = ["Invoice No", "Branch Code", "Payment Received", "Reconciliation Status"]


class HeaderAuditTests(unittest.TestCase):
    def test_correct_order_requires_manual_release_review(self):
        result = audit.audit(SOURCE[:], V218[:], V218[:], SOURCE[:])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["result"], "HEADER_LAYOUT_MATCH_CANDIDATE_REVIEW_REQUIRED")
        self.assertEqual(result["source_53_columns"], 53)
        self.assertEqual(result["approved_v218_columns"], 4)
        self.assertTrue(result["checked_original_53_export"])
        self.assertFalse(result["independent_reference_authenticity_verified"])
        self.assertFalse(result["financial_values_compared"])
        self.assertFalse(result["financial_production_release"])
        self.assertEqual(result["source_rows_modified"], 0)

    def test_swapped_original_position_rejected(self):
        shifted = SOURCE[:]
        shifted[6], shifted[12] = shifted[12], shifted[6]
        result = audit.audit(shifted, V218, V218)
        self.assertIn("ORIGINAL_53_APPROVED_POSITIONS_MISMATCH", result["blockers"])

    def test_duplicate_heading_position_cannot_be_collapsed(self):
        collapsed = list(dict.fromkeys(SOURCE))
        self.assertLess(len(collapsed), 53)
        with self.assertRaises(audit.ReportHeaderReviewRequired):
            audit.audit(collapsed, V218, V218)

    def test_changed_output_order_rejected(self):
        observed = V218[:]
        observed[0], observed[1] = observed[1], observed[0]
        result = audit.audit(SOURCE, V218, observed)
        self.assertIn("V218_OUTPUT_HEADER_POSITIONS_MISMATCH", result["blockers"])

    def test_fabricated_observed_source_header_rejected(self):
        observed = SOURCE[:]
        observed[7] = "Changed Client Name"
        result = audit.audit(SOURCE, V218, V218, observed)
        self.assertIn("ORIGINAL_53_EXPORT_HEADER_POSITIONS_MISMATCH", result["blockers"])

    def test_real_csv_reader_requires_exact_row_width_and_keeps_private_values_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(V218)
                writer.writerow(["SYNTHETIC-INVOICE", "00123", "100", "OK"])
            original = path.read_bytes()
            headers, rows = audit._csv_stats(path)
            self.assertEqual(headers, V218)
            self.assertEqual(rows, 1)
            self.assertEqual(path.read_bytes(), original)
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(V218)
                writer.writerow(["TOO", "FEW", "FIELDS"])
            with self.assertRaisesRegex(audit.ReportHeaderReviewRequired, "ROW_WIDTH"):
                audit._csv_stats(path)

    def test_invalid_references_and_missing_csv_fail_closed(self):
        for data in (None, {}, [], ["", "x"], ["valid", 1]):
            with self.subTest(data=str(data)):
                with self.assertRaises(audit.ReportHeaderReviewRequired):
                    audit._exact_headers(data)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(audit.ReportHeaderReviewRequired):
                audit._csv_stats(Path(tmp) / "missing.csv")

    def test_no_financial_or_remote_side_effects(self):
        text = (ROOT / "tools" / "sbi_report_headers_audit.py").read_text()
        for banned in ("firestore.Client(", "docker ", "gcloud run deploy",
                       "requests.post", "requests.get", "firebase_admin",
                       ".commit(", "openpyxl.load_workbook"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
