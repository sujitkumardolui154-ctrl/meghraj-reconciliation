"""Read-only all-payment-report parity tests for approved 35-column input."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))
from invoice_source_schema import HEADERS_35, HEADERS_53, export_values_53
from payment_report_rules import payment_report_kind


class Approved35PaymentReportParityTests(unittest.TestCase):
    def make_row(self, payment, cell_type="n", balance_valid=True):
        values = [""] * 35
        values[6] = "000123"
        values[8] = "000456"
        values[10] = "MXP-TEST-001"
        values[18] = payment
        values[25] = "100.00" if balance_valid else "#VALUE!"
        types = ["s"] * 35
        types[18] = cell_type
        return {
            "original_headers": HEADERS_35,
            "original_values": values,
            "original_cell_types": types,
            "balance_valid": balance_valid,
        }

    def test_unpaid_ok_error_and_balance_review(self):
        cases = [
            ("", "s", True, "unpaid"),
            ("0", "n", True, "unpaid"),
            ("125.50", "n", True, "ok"),
            ("#VALUE!", "e", False, "error-value"),
            ("-1", "n", False, "error-value"),
        ]
        for payment, cell_type, balance_valid, expected in cases:
            with self.subTest(payment=payment):
                row = self.make_row(payment, cell_type, balance_valid)
                self.assertEqual(payment_report_kind(row), expected)
                exported = export_values_53(row)
                self.assertEqual(len(exported), len(HEADERS_53))
                self.assertEqual(exported[6], "000123")
                self.assertEqual(exported[10], "000456")
                self.assertEqual(exported[12], "MXP-TEST-001")
                self.assertEqual(exported[20], payment)
                self.assertEqual(exported[27], row["original_values"][25])
                self.assertEqual(row["balance_valid"] is False, not balance_valid)

    def test_reject_missing_source_cell_types(self):
        row = self.make_row("100")
        del row["original_cell_types"]
        with self.assertRaises(ValueError):
            payment_report_kind(row)

    def test_reject_source_header_drift(self):
        row = self.make_row("100")
        row["original_headers"] = list(HEADERS_35)
        row["original_headers"][10] = "Wrong Invoice Header"
        with self.assertRaises(ValueError):
            export_values_53(row)


if __name__ == "__main__":
    unittest.main()
