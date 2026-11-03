"""Synthetic end-to-end Excel import tests for the approved 35-column header.

Tests only parse in memory; no cloud credentials, database, or deployment.
"""
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))

import openpyxl
from invoice_excel_parser import parse_excel
from invoice_source_schema import HEADERS_34, HEADERS_35, HEADERS_53, row_layout


def synthetic_values(headers):
    values = [""] * len(headers)
    if headers == HEADERS_35:
        values[6] = "001234"
        values[8] = "009999"
        values[10] = "INV-0001"
        values[18] = "CREDIT NOTE"
        values[25] = "0"
    else:
        invoice_index = 9 if headers == HEADERS_34 else 12
        values[invoice_index] = "INV-0001"
    return values


class Approved35ExcelParserTests(unittest.TestCase):
    def make_xlsx(self, headers, values=None, sheet="Invoice Details."):
        book = openpyxl.Workbook()
        tab = book.active
        tab.title = sheet
        tab.append(headers)
        tab.append(values if values is not None else synthetic_values(headers))
        data = io.BytesIO()
        book.save(data)
        return data.getvalue()

    def test_xlsx_preserves_original_35_values_and_duplicate_code(self):
        result = parse_excel("synthetic.xlsx", self.make_xlsx(HEADERS_35))
        self.assertEqual(result["headers"], HEADERS_35)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rejected"], [])
        row = result["rows"][0]
        self.assertEqual(row_layout(row)[:4], (35, 10, 18, 25))
        self.assertEqual(row["original_values"][6], "001234")
        self.assertEqual(row["original_values"][8], "009999")
        self.assertEqual(row["original_values"][10], "INV-0001")

    def test_old_34_and_53_schemas_still_parse(self):
        for headers, size in [(HEADERS_34, 34), (HEADERS_53, 53)]:
            with self.subTest(size=size):
                result = parse_excel("synthetic.xlsx", self.make_xlsx(headers))
                self.assertEqual(len(result["rows"]), 1)
                self.assertEqual(len(result["rows"][0]["original_values"]), size)
                self.assertEqual(result["rejected"], [])

    def test_rejects_header_drift_without_fallback(self):
        headers = HEADERS_35.copy()
        headers[8] = "Branch Code Renamed"
        with self.assertRaises(ValueError):
            parse_excel("synthetic.xlsx", self.make_xlsx(headers))

    def test_wrong_sheet_rejected(self):
        with self.assertRaises(ValueError):
            parse_excel("synthetic.xlsx", self.make_xlsx(HEADERS_35, sheet="Wrong name"))

    def test_numeric_invoice_is_rejected(self):
        values = synthetic_values(HEADERS_35)
        values[10] = 123
        result = parse_excel("synthetic.xlsx", self.make_xlsx(HEADERS_35, values))
        self.assertEqual(len(result["rows"]), 0)
        self.assertEqual(result["rejected"][0]["reasons"], ["INVOICE_NUMBER_MUST_BE_TEXT"])

    def test_legacy_xls_preserves_duplicate_branch_codes(self):
        import xlwt
        data = io.BytesIO()
        book = xlwt.Workbook()
        tab = book.add_sheet("Invoice Details.")
        values = synthetic_values(HEADERS_35)
        for col, header in enumerate(HEADERS_35):
            tab.write(0, col, header)
        for col, value in enumerate(values):
            tab.write(1, col, value)
        book.save(data)
        result = parse_excel("synthetic.xls", data.getvalue())
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["original_values"][6], "001234")
        self.assertEqual(result["rows"][0]["original_values"][8], "009999")
        self.assertEqual(result["rejected"], [])


if __name__ == "__main__":
    unittest.main()
