"""Synthetic-only independent Credit Note value and provenance tests."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/sbi_credit_note_value_parity.py"
SPEC = importlib.util.spec_from_file_location("independent_cn_values", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def source(invoice="SYNTH-001", *, narration="", gross="118.00"):
    values = [""] * 53
    values[1] = "2026-27"
    values[6] = "00123"  # SOL stays text
    values[7] = "SYNTHETIC CLIENT"
    values[11] = "TEST-GST"
    values[12] = invoice
    values[13:17] = ["100.00", "9.00", "9.00", gross]
    values[17:21] = ["2.00", "116.00", "98.00", narration]
    return values


def projected(values):
    return list(audit._expected_credit_note(values))


def csv_bytes(headers, rows):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(headers)
    writer.writerows(rows)
    return text.getvalue().encode("utf-8-sig")


class IndependentCreditNoteValueAudit(unittest.TestCase):
    def test_header_positions_and_public_output_contract_locked(self):
        self.assertEqual(len(audit.SOURCE_HEADERS), 53)
        self.assertEqual(len(audit.CREDIT_NOTE_HEADERS), 18)
        self.assertEqual(audit.SOURCE_POSITIONS,
            (1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20))
        self.assertEqual(audit.CREDIT_NOTE_HEADERS[8], "Invoice No")
        self.assertEqual(audit.CREDIT_NOTE_HEADERS[12], "Total Bill Amount")
        self.assertEqual(audit.CREDIT_NOTE_HEADERS[17], "Credi note")
        self.assertEqual(audit.SOURCE_HEADERS[12], "Invoice No")
        self.assertEqual(audit.SOURCE_HEADERS[20],
            "Payment Received ( If With GST or Excluding GST)")

    def test_exact_values_match_but_no_financial_approval(self):
        a, b = source("SYNTH-001"), source("SYNTH-002", narration="CREDIT NOTE")
        before = [list(a), list(b)]
        result = audit.evaluate([a, b], [projected(b), projected(a)], baseline_rows=2)
        self.assertEqual(result["status"], "VALUE_PARITY_MATCH_SOURCE_APPROVAL_PENDING")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["credit_note_flagged_report_rows"], 1)
        self.assertFalse(result["production_release_approved"])
        self.assertFalse(result["bank_payment_values_independently_certified"])
        self.assertEqual(result["financial_writes"], 0)
        self.assertEqual([a, b], before)

    def test_all_monetary_positions_are_exact_source_value_checks(self):
        original = source()
        for position in range(9, 17):
            with self.subTest(position=position):
                report = projected(original)
                report[position] = "9999.99"
                outcome = audit.evaluate([original], [report], baseline_rows=1)
                self.assertEqual(outcome["status"], "REVIEW_REQUIRED")
                self.assertIn("CREDIT_NOTE_SOURCE_VALUE_MISMATCH", outcome["blockers"])
                self.assertIn(f"{position + 1:02}", outcome["field_discrepancies"])

    def test_invoice_sol_gst_and_client_field_swap_detected(self):
        original = source()
        for position in (5, 6, 7, 8):
            with self.subTest(position=position):
                report = projected(original)
                report[position] = "ALTERED"
                outcome = audit.evaluate([original], [report], baseline_rows=1)
                self.assertIn("CREDIT_NOTE_SOURCE_VALUE_MISMATCH", outcome["blockers"])

    def test_credit_note_flag_is_derived_from_source_narration(self):
        a = source(narration="bank txn CREDIT NORTE ref")
        b = source("SYNTH-002", narration="CREDIT NOTEBOOK")
        report = [projected(a), projected(b)]
        self.assertEqual(report[0][17], "CREDIT NOTE")
        self.assertEqual(report[1][17], "")
        report[1][17] = "CREDIT NOTE"
        result = audit.evaluate([a, b], report, baseline_rows=2)
        self.assertEqual(result["source_only_projected_records"], 0)
        self.assertIn("CREDIT_NOTE_FULL_ROW_OR_FLAG_MISMATCH", result["blockers"])

    def test_invalid_credit_note_label_is_rejected(self):
        a = source()
        report = projected(a)
        report[17] = "OTHER STATUS"
        result = audit.evaluate([a], [report], baseline_rows=1)
        self.assertIn("UNAPPROVED_CREDIT_NOTE_LABEL", result["blockers"])

    def test_duplicate_invoice_and_credit_note_conflict_require_review(self):
        a = source("DUPLICATE", narration="CREDIT NOTE")
        b = source("DUPLICATE", narration="")
        result = audit.evaluate([a, b], [projected(a), projected(b)], baseline_rows=2)
        self.assertEqual(result["duplicate_invoice_groups"], 1)
        self.assertEqual(result["credit_note_conflict_groups"], 1)
        self.assertIn("DUPLICATE_INVOICE_GROUPS_REQUIRE_REVIEW", result["blockers"])
        self.assertIn("CREDIT_NOTE_CONFLICT_GROUPS_REQUIRE_REVIEW", result["blockers"])
        self.assertEqual(result["source_only_complete_records"], 0)

    def test_identical_duplicate_rows_are_not_collapsed(self):
        a = source("DUPLICATE")
        result = audit.evaluate([a, list(a)], [projected(a), projected(a)], baseline_rows=2)
        self.assertEqual(result["duplicate_invoice_groups"], 1)
        self.assertEqual(result["credit_note_conflict_groups"], 0)
        self.assertEqual(result["credit_note_rows"], 2)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_row_count_and_missing_invoice_block(self):
        a, b = source(""), source("SYNTH-002")
        result = audit.evaluate([a, b], [projected(a)], baseline_rows=2)
        self.assertIn("INVOICE_NUMBER_MISSING_REVIEW", result["blockers"])
        self.assertIn("REPORT_ROW_COUNT_MISMATCH", result["blockers"])

    def test_historical_baseline_is_required(self):
        a = source()
        outcome = audit.evaluate([a], [projected(a)])
        self.assertEqual(outcome["expected_baseline_rows"], 14374)
        self.assertIn("BASELINE_SOURCE_ROW_COUNT_MISMATCH", outcome["blockers"])

    def test_formula_injection_protection_expected(self):
        a = source(narration="=CREDIT NOTE")
        # Cash entry could contain formula-looking text; do not execute it.
        a[13] = "=123"
        expected = projected(a)
        self.assertEqual(expected[9], "'=123")
        outcome = audit.evaluate([a], [expected], baseline_rows=1)
        self.assertEqual(outcome["blockers"], [])
        raw = projected(a)
        raw[9] = "=123"
        outcome = audit.evaluate([a], [raw], baseline_rows=1)
        self.assertIn("CREDIT_NOTE_SOURCE_VALUE_MISMATCH", outcome["blockers"])

    def test_sha_provenance_strict_and_header_preservation(self):
        a = source()
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "private-synthetic.csv"
            data = csv_bytes(audit.SOURCE_HEADERS, [a])
            file.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.assertEqual(len(audit._read_verified_csv(
                file, digest, audit.SOURCE_HEADERS)), 1)
            with self.assertRaises(audit.AuditBlocked):
                audit._read_verified_csv(file, "0" * 64, audit.SOURCE_HEADERS)
            with self.assertRaises(audit.AuditBlocked):
                audit._read_verified_csv(file, "", audit.SOURCE_HEADERS)
            with self.assertRaises(audit.AuditBlocked):
                audit._read_verified_csv(file, digest, audit.CREDIT_NOTE_HEADERS)

    def test_private_actual_data_is_never_uploaded(self):
        script = SCRIPT.read_text()
        for forbidden in ("firebase_admin", "firestore.Client(", "requests.get(",
                          "requests.post(", ".commit(", "gcloud run deploy",
                          "subprocess.run(", "google.cloud"):
            self.assertNotIn(forbidden, script)
        self.assertNotIn("source_rows", audit.evaluate(
            [source()], [projected(source())], baseline_rows=1)["field_discrepancies"])


if __name__ == "__main__":
    unittest.main()
