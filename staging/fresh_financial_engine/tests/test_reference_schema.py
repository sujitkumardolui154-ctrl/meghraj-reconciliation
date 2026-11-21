"""Synthetic header-only regression: zero bank/invoice row data, no workbook I/O."""
import unittest
from sbi_engine.reference_schema import (
    PAYMENT_SHEET, INVOICE_SHEET, PAYMENT_HEADERS, INVOICE_HEADERS,
    validate_reference_headers,
)

class SBIReferenceSchemaTests(unittest.TestCase):
    def test_payment_header_coordinates(self):
        m = validate_reference_headers(PAYMENT_SHEET, list(PAYMENT_HEADERS))
        self.assertEqual(m["description"], 4)
        self.assertEqual(m["sol_id"], 5)
        self.assertEqual(m["credit"], 8)
        self.assertEqual(m["value_date"], 3)

    def test_invoice_header_coordinates(self):
        m = validate_reference_headers(INVOICE_SHEET, list(INVOICE_HEADERS))
        self.assertEqual(m["sol_id"], 6)
        self.assertEqual(m["client_name"], 7)
        self.assertEqual(m["invoice_no"], 10)
        self.assertEqual(m["paid_marker"], 18)

    def test_header_whitespace_normalization_does_not_modify_source(self):
        original = list(PAYMENT_HEADERS)
        original[7] = "        Debit"
        before = original.copy()
        self.assertEqual(validate_reference_headers(PAYMENT_SHEET, original)["debit"], 7)
        self.assertEqual(original, before)

    def test_wrong_spelling_or_column_position_denied(self):
        row = list(PAYMENT_HEADERS)
        row[8] = "Amount"
        with self.assertRaisesRegex(ValueError, "WRONG_INPUT_HEADER_COLUMN_9"):
            validate_reference_headers(PAYMENT_SHEET, row)
        row = list(INVOICE_HEADERS)
        row[6], row[7] = row[7], row[6]
        with self.assertRaisesRegex(ValueError, "WRONG_INPUT_HEADER_COLUMN_7"):
            validate_reference_headers(INVOICE_SHEET, row)

    def test_no_wrong_sheet_or_incomplete_header(self):
        with self.assertRaisesRegex(ValueError,"WRONG_INPUT_SHEET"):
            validate_reference_headers("PAYMENT", list(PAYMENT_HEADERS))
        with self.assertRaisesRegex(ValueError,"WRONG_INPUT_HEADERS"):
            validate_reference_headers(INVOICE_SHEET, list(INVOICE_HEADERS)[:7])

    def test_no_ambiguity_from_duplicate_source_headers(self):
        # Source has duplicate 'Client Name' (A/H) and 'Branch Code' (G/I).
        # H is the intended client identity, G is the intended SOL; neither
        # is inferred by first-match lookup of duplicate header names.
        self.assertEqual(INVOICE_HEADERS[0], INVOICE_HEADERS[7])
        self.assertEqual(INVOICE_HEADERS[6], INVOICE_HEADERS[8])
        m = validate_reference_headers(INVOICE_SHEET, list(INVOICE_HEADERS))
        self.assertEqual((m["sol_id"], m["client_name"]), (6, 7))

if __name__ == "__main__":
    unittest.main()
