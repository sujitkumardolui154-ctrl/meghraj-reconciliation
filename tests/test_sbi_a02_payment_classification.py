"""A02 read-only report grouping tests. Synthetic payments only."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_source"
sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location(
    "sbi_payment_report_rules", BACKEND / "payment_report_rules.py"
)
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)

from invoice_source_schema import HEADERS_53, HEADERS_34


class PaymentClassifierTests(unittest.TestCase):
    def test_empty_or_exact_zero_unpaid(self):
        for original, cell_type in (
            ("", "s"), ("  ", "str"), ("0", "n"),
            ("0.00", "n"), ("-0.00", "n"), ("0E-9", "n"),
            ("+0.00", "inlineStr"),
        ):
            with self.subTest(value=original, kind=cell_type):
                self.assertEqual(rules.classify_payment(original, cell_type), "unpaid")

    def test_positive_numbers_only_are_ok(self):
        for original, cell_type in (
            ("1", "n"), ("200.50", "n"), ("1.00", "s"),
            ("1e3", "n"), ("0.01", "inlineStr"),
        ):
            with self.subTest(original=original, kind=cell_type):
                self.assertEqual(rules.classify_payment(original, cell_type), "ok")

    def test_negative_sources_go_to_review_never_ok(self):
        for original, cell_type in (
            ("-1", "n"), ("-0.01", "n"), ("-23.50", "s"),
            ("-1e3", "n"), ("-0.0001", "inlineStr"),
        ):
            with self.subTest(original=original, kind=cell_type):
                self.assertEqual(rules.classify_payment(original, cell_type), "error-value")

    def test_nonnumeric_credit_note_or_excel_error_stays_nonsettled(self):
        values = [
            ("CREDIT NOTE @ 30/11/2024", "s"),
            ("CREDIT NORTE", "s"),
            ("SUSPENSE", "s"),
            ("PAID", "s"),
            ("12-12-2026", "s"),
            ("100,000", "s"),
            ("1e3", "s"),
            ("NaN", "n"),
            ("Infinity", "n"),
            ("#VALUE!", "e"),
            ("100", "e"),
            ("100", "b"),
            ("=A1", "f"),
        ]
        for value, kind in values:
            with self.subTest(value=value, kind=kind):
                self.assertEqual(rules.classify_payment(value, kind), "error-value")

    def test_nonstring_source_raises_instead_of_coercing(self):
        for value in (None, 10, True, [], {}):
            with self.subTest(value=str(value)):
                with self.assertRaises(ValueError):
                    rules.classify_payment(value, "n")

    def test_53_and_34_positional_payment_field_without_mutation(self):
        for headers, payment_index in ((HEADERS_53, 20), (HEADERS_34, 17)):
            original = [""] * len(headers)
            original[payment_index] = "-0.05"
            values = {
                "original_values": original,
                "original_headers": list(headers),
                "original_cell_types": ["s"] * len(headers),
            }
            frozen = deepcopy(values)
            self.assertEqual(rules.payment_report_kind(values), "error-value")
            self.assertEqual(values, frozen)
            values["original_values"][payment_index] = "25.10"
            self.assertEqual(rules.payment_report_kind(values), "ok")

    def test_missing_cell_type_metadata_rejected(self):
        row = {
            "original_values": [""] * len(HEADERS_53),
            "original_headers": list(HEADERS_53),
        }
        with self.assertRaises(ValueError):
            rules.payment_report_kind(row)

    def test_source_does_not_imply_suspense_or_trigger_financial_engine(self):
        source = (BACKEND / "payment_report_rules.py").read_text(encoding="utf-8")
        for forbidden in ("settle_payment(", "firestore.Client(", ".commit(",
                          "docker ", "gcloud run deploy", "approved_for_settlement=True"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn('return "suspense"', source)


if __name__ == "__main__":
    unittest.main()
