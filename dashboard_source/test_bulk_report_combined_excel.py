"""Offline, synthetic-only QA for the single combined Bulk Report workbook."""
import io
import unittest
import zipfile

from openpyxl import Workbook, load_workbook
from invoice_source_schema import HEADERS_34
from bulk_reports import _build
from bulk_report_excel import combined_excel_from_report_zip

class CombinedExcelTest(unittest.TestCase):
    def test_combined_xlsx_source_only(self):
        source = Workbook()
        sheet = source.active
        sheet.title = "Invoice Details."
        sheet.append(HEADERS_34)

        def row(invoice, payment, balance):
            values = [""] * 34
            values[0] = "SYNTHETIC TEST CUSTOMER"
            values[1] = "2026-2027"
            values[2] = "TEST BRANCH"
            values[3] = "TEST LOCATION"
            values[4] = "October 2026"
            values[5] = "2026-10-31"
            values[6] = "00001"
            values[7] = "SYNTHETIC TEST CUSTOMER"
            values[9] = invoice
            values[10:14] = [100, 9, 9, 118]
            values[17] = payment
            values[24] = balance
            values[26] = "=HYPERLINK(\"https://invalid.example\",\"click\")"
            return values

        sheet.append(row("00000001", "", 118))
        sheet.append(row("TEST-0002", 118, 0))
        sheet.append(row("TEST-0003", "INVALID", 118))
        sheet.append(row("TEST-0004", 50, ""))
        buf = io.BytesIO()
        source.save(buf)
        csv_zip, manifest = _build(buf.getvalue())
        self.assertEqual(manifest["counts"]["accepted_unique_invoice_rows"], 4)
        self.assertFalse(manifest["financial_writes"])
        self.assertFalse(manifest["reconciliation_executed"])
        self.assertFalse(manifest["database_updated"])

        xlsx = combined_excel_from_report_zip(csv_zip)
        with zipfile.ZipFile(io.BytesIO(xlsx)) as archive:
            self.assertIsNone(archive.testzip())

        report = load_workbook(io.BytesIO(xlsx), read_only=True, data_only=False)
        self.addCleanup(report.close)
        expected = {
            "All Invoices": 4,
            "Unpaid": 1,
            "OK Payment Value": 2,
            "Error Value": 1,
            "Balance Review": 1,
            "Validation Review": 0,
        }
        self.assertEqual(report.sheetnames, list(expected))
        # openpyxl's write-only serializer does not always emit worksheet
        # dimension metadata; read-only .max_row/.max_column may be None.
        # Validate actual streamed contents rather than guessed dimensions.
        for name, count in expected.items():
            values = list(report[name].values)
            self.assertEqual(len(values), count + 1, name)
            self.assertEqual(len(values[0]), 3 if name == "Validation Review" else 53, name)
        first = report["All Invoices"]
        self.assertEqual(first.cell(2, 13).value, "00000001")
        self.assertEqual(first.cell(2, 13).data_type, "s")
        self.assertEqual(first.cell(2, 7).value, "00001")
        self.assertEqual(first.cell(2, 30).data_type, "s")
        self.assertTrue(first.cell(2, 30).value.startswith("=HYPERLINK"))
        self.assertEqual(len(next(iter(first.values))), 53)
        self.assertEqual(len(next(iter(report["Validation Review"].values))), 3)

if __name__ == "__main__":
    unittest.main(verbosity=2)
