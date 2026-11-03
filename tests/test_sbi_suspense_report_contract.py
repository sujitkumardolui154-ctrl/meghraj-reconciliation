"""Synthetic-only tests for approved status-only SUSPENSE report."""
from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_suspense_contract", ROOT / "backend_source" / "suspense_report_contract.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def row(status="SUSPENSE", credit="113.84", narration="TEST CREDIT"):
    values = [""] * len(audit.PAYMENT_HEADERS)
    values[4] = narration
    values[5] = "00123"
    values[8] = credit
    values[12] = status
    values[13] = "Independent evidence required"
    return values


class SuspenseContractTests(unittest.TestCase):
    def check(self, data, approved=None, observed=None):
        approved = list(audit.PAYMENT_HEADERS) if approved is None else approved
        observed = list(audit.PAYMENT_HEADERS) if observed is None else observed
        return audit.audit_existing_payment_statuses(
            data, observed_headers=observed, approved_headers=approved
        )

    def test_only_existing_status_m_drives_classification(self):
        inputs = [
            row("OK", "100", "SUSPENSE in BANK narration"),
            row("SUSPENSE", "100", "PAID in narration"),
            row("SUSPENSE", "0", "ANOTHER"),
            row("Duplicate Payment", "100", "DUPLICATE"),
        ]
        before = [list(v) for v in inputs]
        groups, report = self.check(inputs)
        self.assertEqual(inputs, before)
        self.assertEqual(report["status_counts"], {
            "OK": 1, "SUSPENSE": 2, "Duplicate Payment": 1
        })
        self.assertEqual(groups["SUSPENSE"][0][8], "100")
        self.assertEqual(report["credit_diagnostics"]["SUSPENSE"]["ZERO"], 1)
        self.assertEqual(report["credit_diagnostics"]["OK"]["POSITIVE"], 1)
        self.assertFalse(report["source_or_settlement_independently_verified"])
        self.assertEqual(report["source_records_modified"], 0)
        self.assertFalse(report["production_release"])

    def test_benchmark_count_not_required(self):
        _, report = self.check([row("SUSPENSE")] * 4)
        self.assertEqual(report["status_counts"]["SUSPENSE"], 4)
        self.assertNotEqual(report["status_counts"]["SUSPENSE"], 163)

    def test_no_blank_or_misspelled_model_status(self):
        for value in ("", "SUSPENCE", "OK with remarks", "PENDING", "Duplicate"):
            with self.subTest(value=value):
                with self.assertRaises(audit.SuspenseReportBlocked):
                    self.check([row(value)])

    def test_approved_headers_and_source_cell_types_required(self):
        with self.assertRaises(audit.SuspenseReportBlocked):
            self.check([row()], approved=[])
        wrong = list(audit.PAYMENT_HEADERS)
        wrong[8] = "Debit"
        with self.assertRaises(audit.SuspenseReportBlocked):
            self.check([row()], observed=wrong)
        with self.assertRaises(audit.SuspenseReportBlocked):
            self.check([row()[:22]])
        corrupted = row()
        corrupted[8] = 123.1
        with self.assertRaises(audit.SuspenseReportBlocked):
            self.check([corrupted])

    def test_credit_i_only_not_h_or_j(self):
        source = row("SUSPENSE", "")
        source[7] = "999.00"
        source[9] = "500.00"
        _, report = self.check([source])
        self.assertEqual(report["credit_diagnostics"]["SUSPENSE"]["BLANK"], 1)

    def test_private_csv_order_unchanged_and_formula_escaped(self):
        source = row("SUSPENSE", "113.84", "=HYPERLINK(bad)")
        original = list(source)
        groups, _ = self.check([source])
        data = audit.suspense_report_csv(groups["SUSPENSE"])
        output = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(output[0], audit.PAYMENT_HEADERS)
        self.assertEqual(output[1][4], "'=HYPERLINK(bad)")
        self.assertEqual(output[1][8], "113.84")
        self.assertEqual(source, original)

    def test_cannot_export_ok_as_suspense(self):
        with self.assertRaises(audit.SuspenseReportBlocked):
            audit.suspense_report_csv([row("OK")])

    def test_no_engine_or_financial_writes(self):
        text = (ROOT / "backend_source" / "suspense_report_contract.py").read_text()
        for token in ("firestore.Client(", "firebase_admin", ".commit(",
                      "gcloud run deploy", "settle_invoice", "allocate_credit("):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
