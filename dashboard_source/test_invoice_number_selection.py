"""Synthetic-only regression for arbitrary-order invoice number selection."""
import io
import unittest

from openpyxl import Workbook

from invoice_number_selection import parse_selection


def workbook(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "Requested Invoices"
    for row in rows:
        sheet.append(row if isinstance(row, list) else [row])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


class InvoiceNumberSelectionTests(unittest.TestCase):
    def test_any_order_duplicate_and_leading_zero(self):
        result = parse_selection(workbook([
            "Invoice No", "MXP21658", "000123", "MXP21569",
            "MXP21658", None, " MXP21574 ",
        ]))
        self.assertEqual(result.invoice_numbers, (
            "MXP21658", "000123", "MXP21569", "MXP21574"
        ))
        self.assertEqual(result.review, (
            (5, "MXP21658", "DUPLICATE_REQUESTED_INVOICE"),
        ))

    def test_no_header_accepted(self):
        result = parse_selection(workbook(["MXP1001", "MXP1002"]))
        self.assertEqual(result.invoice_numbers, ("MXP1001", "MXP1002"))

    def test_numeric_invoice_rejected_without_guessing_zeros(self):
        result = parse_selection(workbook(["Invoice No", 12345, "MXP1003"]))
        self.assertEqual(result.invoice_numbers, ("MXP1003",))
        self.assertEqual(result.review[0][2], "INVALID_INVOICE_NUMBER")

    def test_formula_rejected(self):
        result = parse_selection(workbook([
            "Invoice No", '=HYPERLINK("https://example.invalid","x")',
            "MXP1003",
        ]))
        self.assertEqual(result.invoice_numbers, ("MXP1003",))
        self.assertEqual(result.review[0][2], "INVALID_INVOICE_NUMBER")

    def test_multiple_columns_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one column"):
            parse_selection(workbook([["Invoice No", "Branch"], ["MXP1001", "X"]]))

    def test_only_invalid_rows_rejected(self):
        with self.assertRaisesRegex(ValueError, "No valid invoice numbers"):
            parse_selection(workbook(["Invoice No", 12345]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
