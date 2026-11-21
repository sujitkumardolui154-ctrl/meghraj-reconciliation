"""Offline combined selected-invoice export QA. No database or remote calls."""
import csv
import io
import json
import unittest
import zipfile

from openpyxl import load_workbook

from bulk_report_selection import build_selection_zip
from bulk_report_excel import combined_excel_from_report_zip
from invoice_number_selection import Selection


def matched(number, kind="ok", review=False):
    values = [""] * 53
    values[12] = number
    values[20] = "100" if kind == "ok" else ""
    return {"invoice_no": number, "values": values, "payment_kind": kind,
            "balance_review": review}


class SelectedBulkReportTests(unittest.TestCase):
    def test_random_requested_order_missing_and_review(self):
        request = Selection(
            ("MXP21658", "MXP99999", "MXP21569"),
            ((5, "MXP21658", "DUPLICATE_REQUESTED_INVOICE"),),
        )
        backend = {
            "version": "invoice-selection-v1",
            "source_kind": "VERIFIED_READ_ONLY_REPORT_SOURCE",
            "dataset": "synthetic-dataset",
            "financial_writes": False,
            "database_updated": False,
            "reconciliation_executed": False,
            "requested_count": 3,
            "matched_count": 2,
            "review_count": 1,
            "matches": [matched("MXP21569", "unpaid"),
                        matched("MXP21658", "ok", review=True)],
            "review": [{"invoice_no": "MXP99999",
                        "reason": "NOT_FOUND_IN_VERIFIED_REPORT_SOURCE"}],
        }
        bundle, manifest = build_selection_zip(request, backend, "a"*64)
        self.assertEqual(manifest["counts"]["matched"], 2)
        self.assertEqual(manifest["counts"]["lookup_review"], 1)
        self.assertFalse(manifest["financial_writes"])
        self.assertFalse(manifest["database_updated"])

        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            rows = list(csv.reader(io.StringIO(zf.read("all-invoices.csv")
                                      .decode("utf-8-sig"))))
            self.assertEqual([row[12] for row in rows[1:]],
                             ["MXP21658", "MXP21569"])
            self.assertIn("lookup-review.csv", zf.namelist())

        xlsx = combined_excel_from_report_zip(bundle)
        book = load_workbook(io.BytesIO(xlsx), read_only=True)
        self.addCleanup(book.close)
        self.assertEqual(book.sheetnames, [
            "All Invoices", "Unpaid", "OK Payment Value", "Error Value",
            "Balance Review", "Validation Review", "Lookup Review",
        ])
        self.assertEqual(book["All Invoices"]["M2"].value, "MXP21658")
        self.assertEqual(book["All Invoices"]["M3"].value, "MXP21569")
        self.assertEqual(book["Lookup Review"]["A2"].value, "MXP99999")
        self.assertEqual(book["Validation Review"]["B2"].value, "MXP21658")

    def test_reject_unaccounted_or_wrong_data(self):
        request = Selection(("MXP1",), ())
        payload = {
            "version": "invoice-selection-v1",
            "source_kind": "VERIFIED_READ_ONLY_REPORT_SOURCE",
            "dataset": "synthetic",
            "financial_writes": False, "database_updated": False,
            "reconciliation_executed": False, "requested_count": 1,
            "matched_count": 0, "review_count": 0,
            "matches": [], "review": [],
        }
        with self.assertRaises(ValueError):
            build_selection_zip(request, payload, "b"*64)

        payload["financial_writes"] = True
        with self.assertRaises(ValueError):
            build_selection_zip(request, payload, "b"*64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
