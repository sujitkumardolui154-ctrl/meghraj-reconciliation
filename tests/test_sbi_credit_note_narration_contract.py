"""Synthetic regression for owner-approved CREDIT NOTE and CREDIT NORTE narratives.

Never reads production invoice rows; preserves all 17 original report fields.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_credit_note_report", ROOT / "backend_source" / "credit_note_report.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def invoice(invoice_no="MXP-TEST-01", narration=""):
    source = {h: "" for h in mod.SOURCE_HEADERS}
    source["Invoice No"] = invoice_no
    source["Branch Code"] = "00123"
    source["Client Name"] = "SYNTHETIC ONLY"
    source[mod.PAYMENT_FIELD] = narration
    return source


class CreditNoteNarrationTests(unittest.TestCase):
    def test_source_header_contract_is_18_columns(self):
        self.assertEqual(len(mod.HEADERS), 18)
        self.assertEqual(mod.HEADERS[-1], "Credi note")
        self.assertEqual(len(mod.SOURCE_HEADERS), 17)

    def test_approved_token_variants_inside_narration(self):
        narrations = [
            "CREDIT NOTE", "credit note @ 30/11/2024",
            "CREDIT NORTE @ 30/11/2024",
            "Credit Note Against Invoice MXP",
            "PAID; CREDIT NOTE, see reference",
            "(CREDIT NOTE) / ADJUSTED",
            "other\ncredit  note\nentry",
        ]
        rows = [invoice("TEST-" + str(i), note) for i, note in enumerate(narrations)]
        original = deepcopy(rows)
        report, summary = mod.generate_credit_note_report(rows)
        self.assertEqual(rows, original)
        self.assertEqual(len(report), len(narrations))
        self.assertTrue(all(row["Credi note"] == "CREDIT NOTE" for row in report))
        self.assertEqual(summary["credit_note_invoices"], len(narrations))
        self.assertEqual(summary["credit_note_unambiguous_invoices"], len(narrations))
        self.assertEqual(summary["source_records_modified"], 0)
        self.assertFalse(summary["independent_source_approval"])
        self.assertEqual(summary["release_status"], "REVIEW_REQUIRED")

    def test_unrelated_words_never_mark_credit_note(self):
        notes = [
            "PAID", "CREDIT NOTEBOOK", "credit notebook issued",
            "CREDIT NOTES", "RE-CREDIT NOTEBOOK", "CREDIT NOTE123",
            "XPAYCREDIT NOTEBOOK", "NO CREDIT", "NORTE CREDIT",
        ]
        report, summary = mod.generate_credit_note_report([
            invoice("TEST-" + str(i), note) for i, note in enumerate(notes)
        ])
        self.assertEqual(summary["credit_note_invoices"], 0)
        self.assertTrue(all(not r["Credi note"] for r in report))

    def test_duplicate_positive_and_negative_invoice_requires_review(self):
        rows = [
            invoice("DUP-01", "CREDIT NOTE @ 01/01/2026"),
            invoice("DUP-01", "PAID"),
            invoice("UNIQUE", "CREDIT NORTE"),
        ]
        report, summary = mod.generate_credit_note_report(rows)
        self.assertEqual(len(report), 3)
        self.assertEqual(summary["unique_invoices"], 2)
        self.assertEqual(summary["credit_note_invoices"], 2)
        self.assertEqual(summary["credit_note_conflict_groups"], 1)
        self.assertEqual(summary["credit_note_unambiguous_invoices"], 1)
        self.assertEqual(summary["duplicate_invoice_groups"], 1)
        self.assertEqual([r["Credi note"] for r in report],
                         ["CREDIT NOTE", "", "CREDIT NOTE"])

    def test_duplicate_same_positive_row_not_counted_as_conflict(self):
        row = invoice("DUP-01", "CREDIT NOTE")
        _, summary = mod.generate_credit_note_report([row, deepcopy(row)])
        self.assertEqual(summary["credit_note_invoices"], 1)
        self.assertEqual(summary["credit_note_conflict_groups"], 0)

    def test_duplicate_positive_rows_with_different_source_values_conflict(self):
        first = invoice("DUP-01", "CREDIT NOTE")
        second = invoice("DUP-01", "CREDIT NOTE")
        second["Taxable Amount"] = "DIFFERENT"
        _, summary = mod.generate_credit_note_report([first, second])
        self.assertEqual(summary["credit_note_conflict_groups"], 1)
        self.assertEqual(summary["credit_note_unambiguous_invoices"], 0)

    def test_missing_invoice_number_cannot_inflate_unique_invoice_count(self):
        _, summary = mod.generate_credit_note_report([
            invoice("", "CREDIT NOTE"), invoice("ID-01", "CREDIT NOTE")
        ])
        self.assertEqual(summary["credit_note_invoices"], 1)
        self.assertEqual(summary["missing_invoice_numbers"], 1)
        self.assertEqual(summary["missing_credit_note_invoice_numbers"], 1)

    def test_missing_required_column_fails_closed(self):
        row = invoice()
        del row["Invoice No"]
        with self.assertRaises(ValueError):
            mod.generate_credit_note_report([row])


if __name__ == "__main__":
    unittest.main()
