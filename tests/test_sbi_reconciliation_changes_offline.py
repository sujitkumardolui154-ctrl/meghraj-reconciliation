"""Synthetic no-write reconciliation change report contract tests."""
from __future__ import annotations

from copy import deepcopy
import csv
import importlib.util
import io
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_reconciliation_changes_offline",
    ROOT / "backend_source" / "reconciliation_changes_offline.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(invoice="TEST-01", payment="", status="UNPAID"):
    return {
        "invoice_no": invoice, "payment_received": payment,
        "reconciliation_status": status,
    }


class OfflineChangeReportTests(unittest.TestCase):
    def test_all_six_categories_and_source_immutability(self):
        old = [
            row("UNCHANGED", "100.00", "OK"),
            row("ADDED", "", "UNPAID"),
            row("CHANGED", "10.00", "BALANCE REVIEW"),
            row("CLEARED", "50.00", "OK"),
            row("MISSING", "30.00", "OK"),
            row("DUPLICATE", "10", "OK"),
            row("DUPLICATE", "30", "OK"),
        ]
        new = [
            row("NEW", "", "UNPAID"),
            row("UNCHANGED", "100", "OK"),
            row("ADDED", "120.00", "OK"),
            row("CHANGED", "15.00", "BALANCE REVIEW"),
            row("CLEARED", "0.00", "REVIEW"),
            row("DUPLICATE", "10", "OK"),
        ]
        old_copy, new_copy = deepcopy(old), deepcopy(new)
        report, summary = mod.make_reconciliation_change_report(old, new)
        self.assertEqual(old, old_copy)
        self.assertEqual(new, new_copy)
        by_invoice = {record["invoice_no"]: record for record in report}
        self.assertEqual({key: val["category"] for key, val in by_invoice.items()}, {
            "UNCHANGED": "UNCHANGED",
            "ADDED": "PAYMENT_ADDED",
            "CHANGED": "PAYMENT_CHANGED",
            "CLEARED": "PAYMENT_CLEARED_REVIEW",
            "MISSING": "CONFLICT",
            "DUPLICATE": "CONFLICT",
            "NEW": "NEW",
        })
        self.assertEqual(by_invoice["CLEARED"]["old_payment"], "50.00")
        self.assertEqual(by_invoice["CLEARED"]["new_payment"], "0.00")
        self.assertEqual(summary["total_invoice_groups"], 7)
        self.assertEqual(sum(summary["categories"].values()), 7)
        self.assertTrue(summary["review_required"])
        self.assertFalse(summary["approved_for_settlement"])
        self.assertFalse(summary["source_snapshot_certified"])
        self.assertFalse(summary["source_rows_mutated"])

    def test_changed_status_without_money_change_requires_review(self):
        result, _ = mod.make_reconciliation_change_report(
            [row(payment="100", status="OK")],
            [row(payment="100.00", status="SUSPENSE")],
        )
        self.assertEqual(result[0]["category"], "CONFLICT")
        self.assertEqual(result[0]["review_reason"], "STATUS_CHANGED_WITHOUT_PAYMENT_CHANGE")

    def test_malformed_new_payment_description_fails_closed(self):
        result, summary = mod.make_reconciliation_change_report(
            [], [row(payment="CREDIT NOTE", status="REVIEW")]
        )
        self.assertEqual(result[0]["category"], "CONFLICT")
        self.assertTrue(summary["review_required"])

    def test_negative_or_nonfinite_payments_are_not_settled(self):
        for value in ("-2", "NaN", "Infinity", "CREDIT NORTE", "1,000.00"):
            with self.subTest(value=value):
                result, _ = mod.make_reconciliation_change_report(
                    [row(payment="0")], [row(payment=value)]
                )
                self.assertEqual(result[0]["category"], "CONFLICT")

    def test_nonzero_payment_new_and_blank_source(self):
        report, _ = mod.make_reconciliation_change_report([], [row(payment="14.25")])
        self.assertEqual(report[0]["category"], "NEW")
        self.assertEqual(report[0]["new_payment"], "14.25")

    def test_duplicate_in_new_snapshot_fails_closed(self):
        report, _ = mod.make_reconciliation_change_report(
            [row(payment="10")],
            [row(payment="10"), row(payment="11")],
        )
        self.assertEqual(report[0]["category"], "CONFLICT")
        self.assertEqual(report[0]["review_reason"], "DUPLICATE_INVOICE_NUMBER")
        self.assertEqual(report[0]["new_count"], 2)

    def test_missing_id_or_schema_rejected(self):
        for bad in ([row(invoice="")], [{"invoice_no": "X"}], [None], "not a list"):
            with self.subTest(bad=str(bad)):
                with self.assertRaises(ValueError):
                    mod.make_reconciliation_change_report([], bad)

    def test_private_csv_retains_headers_and_escapes_injection(self):
        report, summary = mod.make_reconciliation_change_report(
            [row("TEST-01", "100", "OK")],
            [row("TEST-01", "120", "=HYPERLINK(fake)")],
        )
        self.assertEqual(report[0]["category"], "PAYMENT_CHANGED")
        data = mod.change_report_csv(report)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        parsed = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(parsed[0], list(mod.CSV_HEADERS))
        self.assertEqual(parsed[1][5], "'=HYPERLINK(fake)")
        self.assertEqual(parsed[1][2], "100")
        self.assertEqual(summary["categories"]["PAYMENT_CHANGED"], 1)

    def test_no_cloud_mutation_or_financial_settlement_api(self):
        source = (ROOT / "backend_source" / "reconciliation_changes_offline.py").read_text()
        for forbidden in ("firestore.Client(", "firebase_admin", ".commit(",
                          "docker compose up", "gcloud run deploy", "google.cloud"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
