"""Independent synthetic-only A08 report parity and GST exception checks."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_financial_report_parity", ROOT / "tools" / "sbi_financial_report_parity.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def synthetic(invoice, taxable="100.00", cgst="9.00", sgst="9.00", gross="118.00"):
    data = [""] * 53
    data[6] = "00123"
    data[7] = "SYNTHETIC ONLY"
    data[10] = "99999"
    data[12] = invoice
    data[13], data[14], data[15], data[16] = taxable, cgst, sgst, gross
    return data


def masked(row):
    return [audit._export_cell(v) for v in row]


class FinancialReportParityTests(unittest.TestCase):
    def test_full_rowset_and_exact_values_partition_is_provisional(self):
        a = synthetic("TEST-001")
        b = synthetic("TEST-002")
        c = synthetic("TEST-003")
        before = [list(r) for r in (a, b, c)]
        result = audit.evaluate([a, b, c], {
            "unpaid": [masked(a)], "ok": [masked(b)],
            "error-value": [masked(c)], "balance-review": [masked(b)]
        })
        self.assertEqual(result["source_rows"], 3)
        self.assertEqual(result["partition_report_rows"], 3)
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["result"], "PARTITION_MATCH_SOURCE_APPROVAL_PENDING")
        self.assertFalse(result["external_independent_provenance_verified"])
        self.assertFalse(result["settlement_or_tds_recalculation"])
        self.assertFalse(result["original_values_mutated"])
        self.assertEqual([a, b, c], before)

    def test_missing_row_or_cross_category_double_count_blocks(self):
        a = synthetic("TEST-001")
        b = synthetic("TEST-002")
        missing = audit.evaluate([a, b], {
            "unpaid": [masked(a)], "ok": [], "error-value": []
        })
        self.assertIn("PRIMARY_REPORT_TOTAL_OR_ROWSET_MISMATCH", missing["blockers"])
        duplicated = audit.evaluate([a, b], {
            "unpaid": [masked(a)], "ok": [masked(a)], "error-value": [masked(b)]
        })
        self.assertIn("PRIMARY_REPORT_TOTAL_OR_ROWSET_MISMATCH", duplicated["blockers"])

    def test_changed_one_original_column_blocks_export(self):
        a = synthetic("TEST-001")
        observed = masked(a)
        observed[7] = "WRONG CLIENT"
        result = audit.evaluate([a], {
            "unpaid": [observed], "ok": [], "error-value": []
        })
        self.assertIn("SOURCE_TO_UNPAID_REPORT_MISMATCH", result["blockers"])

    def test_duplicate_invoice_is_review_not_auto_collapse(self):
        a = synthetic("DUP-001")
        b = synthetic("DUP-001", taxable="200", cgst="18", sgst="18", gross="236")
        result = audit.evaluate([a, b], {
            "unpaid": [masked(a)], "ok": [masked(b)], "error-value": []
        })
        self.assertEqual(result["duplicate_invoice_groups"], 1)
        self.assertIn("DUPLICATE_INVOICE_GROUPS_REQUIRE_REVIEW", result["blockers"])

    def test_independent_gst_arithmetic_never_rewrites_amounts(self):
        a = synthetic("TEST-001", taxable="100.00", cgst="9.00",
                      sgst="9.00", gross="119.00")
        original = list(a)
        result = audit.evaluate([a], {
            "unpaid": [masked(a)], "ok": [], "error-value": []
        })
        self.assertEqual(a, original)
        self.assertEqual(result["gst_arithmetic_mismatch_rows"], 1)
        self.assertIn("GST_SOURCE_ARITHMETIC_EXCEPTIONS_REQUIRE_REVIEW", result["blockers"])

    def test_empty_or_nonfinancial_values_are_not_falsely_verified(self):
        a = synthetic("TEST-001", taxable="CREDIT NOTE")
        result = audit.evaluate([a], {
            "unpaid": [masked(a)], "ok": [], "error-value": []
        })
        self.assertEqual(result["gst_arithmetic_unverifiable_rows"], 1)
        self.assertIn("GST_SOURCE_VALUES_NOT_ALL_NUMERIC", result["blockers"])

    def test_only_expected_reports_allowed(self):
        with self.assertRaises(audit.ParityBlocked):
            audit.evaluate([], {"unpaid": []})
        with self.assertRaises(audit.ParityBlocked):
            audit.evaluate([], {"unpaid": [], "ok": [],
                                "error-value": [], "suspense": []})

    def test_independent_sha_required_and_mutation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "source.csv"
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(audit.SOURCE_HEADERS)
            writer.writerow(synthetic("TEST-001"))
            raw = output.getvalue().encode("utf-8-sig")
            filename.write_bytes(raw)
            real = hashlib.sha256(raw).hexdigest()
            self.assertEqual(len(audit._load_verified_csv(filename, real)), 1)
            with self.assertRaisesRegex(audit.ParityBlocked, "SHA256_MISMATCH"):
                audit._load_verified_csv(filename, "0" * 64)
            with self.assertRaisesRegex(audit.ParityBlocked, "DIGEST_REQUIRED"):
                audit._load_verified_csv(filename, "")

    def test_csv_embedded_newlines_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "source.csv"
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(audit.SOURCE_HEADERS)
            row = synthetic("TEST-001")
            row[30] = "Synthetic\nprivate note"
            writer.writerow(row)
            raw = output.getvalue().encode("utf-8-sig")
            filename.write_bytes(raw)
            self.assertEqual(audit._load_verified_csv(
                filename, hashlib.sha256(raw).hexdigest()
            )[0][30], "Synthetic\nprivate note")

    def test_private_no_cloud_access(self):
        source = (ROOT / "tools" / "sbi_financial_report_parity.py").read_text()
        for term in ("firestore.Client(", "firebase_admin", ".commit(",
                     "gcloud run deploy", "requests.get(", "requests.post("):
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
