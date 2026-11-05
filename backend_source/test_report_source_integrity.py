"""Synthetic source-integrity tests; no cloud services or financial writes."""
import unittest

from report_source_integrity import (
    validate_receipt_source_positions,
    validate_completed_receipt_source_sheet,
)


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



class CompletedReceiptSheetTest(unittest.TestCase):
    def test_exact_approved_sheet_passes(self):
        receipt = {"source_sheet": "Invoice Details."}
        entries = [("invoice-a", {"source_sheet": "Invoice Details."})]
        self.assertEqual(validate_completed_receipt_source_sheet(receipt, entries), 1)

    def test_receipt_sheet_rejected_if_wrong(self):
        for value in ("Sheet1", "Invoice Details", "invoice details.", "", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "unapproved source sheet"):
                    validate_completed_receipt_source_sheet(
                        {"source_sheet": value},
                        [("invoice-a", {"source_sheet": "Invoice Details."})],
                    )

    def test_row_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unapproved source sheet"):
            validate_completed_receipt_source_sheet(
                {"source_sheet": "Invoice Details."},
                [("invoice-a", {"source_sheet": "Other Worksheet"})],
            )

    def test_missing_receipt_and_missing_row_fail_closed(self):
        with self.assertRaises(ValueError):
            validate_completed_receipt_source_sheet({}, [])
        with self.assertRaises(ValueError):
            validate_completed_receipt_source_sheet(
                {"source_sheet": "Invoice Details."}, [("invoice-a", {})]
            )


if __name__ == "__main__":
    unittest.main()
