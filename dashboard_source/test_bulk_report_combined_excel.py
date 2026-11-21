"""Offline, synthetic-only QA for the single combined Bulk Report workbook."""
import io
import unittest
import zipfile

from openpyxl import Workbook, load_workbook
from invoice_source_schema import HEADERS_34
from bulk_reports import _build
from bulk_report_excel import combined_excel_from_report_zip, _excel_money

class CombinedExcelTest(unittest.TestCase):
    def test_money_conversion_preserves_precision_and_non_numeric_labels(self):
        from bulk_report_excel import _excel_date
        self.assertEqual(_excel_date("2023-10-17T00:00:00").strftime("%d/%m/%Y"), "17/10/2023")
        self.assertEqual(_excel_date("2023-09-01").strftime("%Y-%m-%d"), "2023-09-01")
        self.assertIsNone(_excel_date("CANCLED"))
        self.assertIsNone(_excel_date("31/12/2023"))
        self.assertIsNone(_excel_date("Mar-May 2026"))
        self.assertEqual(_excel_money("2.4299999999999997"), 2.43)
        self.assertEqual(_excel_money("43.739999999999995"), 43.74)
        self.assertEqual(_excel_money("608.8800000000001"), 608.88)
        self.assertEqual(_excel_money("1,234.56"), 1234.56)
        self.assertEqual(_excel_money("-12.50"), -12.5)
        self.assertEqual(_excel_money("1.005"), 1.005)
        for token in ("CANCLED", "CREDIT NOTE", "'=1+2", "2023-10-17T00:00:00",
                      "", "NaN", "Infinity", "99999999999999999.99"):
            self.assertIsNone(_excel_money(token), token)

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

        first_row = row("00000001", "", 118)
        first_row[10:14] = [27, 2.4299999999999997, 2.4299999999999997, 31.86]
        first_row[4] = "2026-10-01T00:00:00"
        first_row[18] = "2026-10-17T00:00:00"
        first_row[20] = "2026-11-03T00:00:00"
        sheet.append(first_row)
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
        # Amounts must be native numeric cells, not Excel text. Tiny
        # source float artifacts normalize to cents for an accurate display.
        self.assertEqual(first.cell(2, 14).data_type, "n")  # Taxable
        self.assertEqual(first.cell(2, 14).value, 27)
        self.assertEqual(first.cell(2, 15).data_type, "n")  # CGST
        self.assertAlmostEqual(first.cell(2, 15).value, 2.43)
        self.assertEqual(first.cell(2, 16).data_type, "n")  # SGST
        self.assertAlmostEqual(first.cell(2, 16).value, 2.43)
        self.assertEqual(first.cell(2, 15).number_format,
                         '#,##0.00;[Red](#,##0.00);0.00')
        self.assertEqual(first.cell(3, 21).data_type, "n")  # Payment
        self.assertEqual(first.cell(3, 21).value, 118)
        self.assertEqual(first.cell(4, 21).data_type, "s")  # INVALID
        self.assertEqual(first.cell(4, 21).value, "INVALID")
        self.assertEqual(first.cell(2, 7).data_type, "s")  # SOL ID
        self.assertEqual(first.cell(2, 5).data_type, "d")  # Month
        self.assertEqual(first.cell(2, 5).number_format, "mmmm yyyy")
        self.assertEqual(first.cell(2, 5).value.strftime("%Y-%m-%d"), "2026-10-01")
        self.assertEqual(first.cell(2, 6).data_type, "d")  # Invoice date
        self.assertEqual(first.cell(2, 6).number_format, "dd/mm/yyyy")
        self.assertEqual(first.cell(2, 6).value.strftime("%Y-%m-%d"), "2026-10-31")
        self.assertEqual(first.cell(2, 22).data_type, "d")  # Payment date
        self.assertEqual(first.cell(2, 22).value.strftime("%Y-%m-%d"), "2026-10-17")
        self.assertEqual(first.cell(2, 24).data_type, "d")  # GST payment date
        self.assertEqual(first.cell(2, 24).value.strftime("%Y-%m-%d"), "2026-11-03")
        self.assertEqual(first.cell(2, 30).data_type, "s")
        # The upstream csv_bytes() intentionally prefixes an apostrophe to
        # any Excel-like formula. The combined exporter must retain that
        # neutralized literal, NOT strip the apostrophe or execute the formula.
        self.assertTrue(first.cell(2, 30).value.startswith("'=HYPERLINK"))
        self.assertEqual(len(next(iter(first.values))), 53)
        self.assertEqual(len(next(iter(report["Validation Review"].values))), 3)

if __name__ == "__main__":
    unittest.main(verbosity=2)
