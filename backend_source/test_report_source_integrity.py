"""Synthetic source-integrity tests; no cloud services or financial writes."""
import unittest

from report_source_integrity import validate_receipt_source_positions


class CompletedReceiptPositionsTest(unittest.TestCase):
    def test_distinct_positions(self):
        self.assertEqual(
            validate_receipt_source_positions([
                ("invoice-a", {"source_row": 2}),
                ("invoice-b", {"source_row": 3}),
            ]),
            2,
        )

    def test_duplicate_position_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate source rows"):
            validate_receipt_source_positions([
                ("invoice-a", {"source_row": 2}),
                ("invoice-b", {"source_row": 2}),
            ])

    def test_boolean_is_not_a_row_number(self):
        with self.assertRaisesRegex(ValueError, "invalid source row"):
            validate_receipt_source_positions([("invoice-a", {"source_row": True})])

    def test_missing_and_string_positions_are_rejected(self):
        for row in ({}, {"source_row": "2"}, {"source_row": 1}):
            with self.subTest(row=row):
                with self.assertRaisesRegex(ValueError, "invalid source row"):
                    validate_receipt_source_positions([("invoice-a", row)])

    def test_empty_receipt(self):
        self.assertEqual(validate_receipt_source_positions([]), 0)


if __name__ == "__main__":
    unittest.main()
