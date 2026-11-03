"""Synthetic source-position QA for CREDIT NOTE output.

The 53 headers contain duplicate names: projection MUST use positions.
No live source, finance, Cloud Run, or customer records are used.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_source"
sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location(
    "sbi_credit_note_53", BACKEND / "credit_note_report.py"
)
credit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credit)
HEADERS = json.loads(
    (BACKEND / "invoice_import_contract.json").read_text(encoding="utf-8")
)["headers"]


def raw(invoice="MXP-SYNTHETIC-001", narration="CREDIT NORTE @ 2026-10-01"):
    values = [""] * 53
    values[0] = "WRONG_FIRST_CLIENT_NAME"
    values[1:8] = ["2026-27", "SBI ZO", "KOLKATA", "Oct 2026",
                   "2026-10-03", "00123", "RIGHT_CLIENT_NAME"]
    values[10] = "WRONG_SECOND_BRANCH_CODE"
    values[11:21] = [
        "GST-NUMBER", invoice, "123.00", "11.07", "11.07",
        "145.14", "1.23", "143.91", "121.77", narration,
    ]
    return {"original_values": values, "original_headers": list(HEADERS)}


class CreditNote53PositionTests(unittest.TestCase):
    def test_original_53_headers_include_duplicate_names(self):
        self.assertEqual(len(HEADERS), 53)
        self.assertEqual(HEADERS[0], HEADERS[7])
        self.assertEqual(HEADERS[6], HEADERS[10])
        self.assertEqual(HEADERS[12], "Invoice No")
        self.assertEqual(credit.SOURCE_POSITIONS_53, (
            1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20
        ))

    def test_exact_projection_and_unchanged_original_values(self):
        row = raw()
        frozen = deepcopy(row)
        report, summary = credit.generate_credit_note_report_from_53(
            [row], approved_53_headers=list(HEADERS)
        )
        self.assertEqual(row, frozen)
        self.assertEqual(len(report), 1)
        self.assertEqual(list(report[0]), credit.HEADERS)
        self.assertEqual(
            [report[0][h] for h in credit.SOURCE_HEADERS],
            [row["original_values"][i] for i in credit.SOURCE_POSITIONS_53],
        )
        self.assertEqual(report[0]["Branch Code"], "00123")
        self.assertEqual(report[0]["Client Name"], "RIGHT_CLIENT_NAME")
        self.assertEqual(report[0]["Invoice No"], "MXP-SYNTHETIC-001")
        self.assertEqual(report[0]["Credi note"], "CREDIT NOTE")
        self.assertEqual(summary["credit_note_invoices"], 1)
        self.assertEqual(summary["source_projection"], "ORIGINAL_53_POSITIONAL")
        self.assertFalse(summary["independent_source_approval"])

    def test_source_row_mismatch_and_reference_absence_rejected(self):
        row = raw()
        for headers in (None, [], HEADERS[:-1], HEADERS[:]):
            if headers == HEADERS:
                continue
            with self.subTest(headers_len=len(headers or [])):
                with self.assertRaises(ValueError):
                    credit.generate_credit_note_report_from_53(
                        [row], approved_53_headers=headers
                    )
        changed = list(HEADERS)
        changed[7] = "WRONG CLIENT NAME"
        with self.assertRaises(ValueError):
            credit.generate_credit_note_report_from_53(
                [row], approved_53_headers=changed
            )
        changed_row = deepcopy(row)
        changed_row["original_headers"][6] = "WRONG BRANCH CODE"
        with self.assertRaises(ValueError):
            credit.generate_credit_note_report_from_53(
                [changed_row], approved_53_headers=list(HEADERS)
            )

    def test_positional_blank_invoice_and_duplicate_conflict(self):
        one = raw(invoice="DUP-SYNTH", narration="CREDIT NOTE @ 10/10/2026")
        two = raw(invoice="DUP-SYNTH", narration="PAID")
        original = deepcopy([one, two])
        report, summary = credit.generate_credit_note_report_from_53(
            [one, two], approved_53_headers=list(HEADERS)
        )
        self.assertEqual([one, two], original)
        self.assertEqual(summary["credit_note_invoices"], 1)
        self.assertEqual(summary["credit_note_conflict_groups"], 1)
        self.assertEqual(summary["credit_note_unambiguous_invoices"], 0)
        self.assertEqual([r["Credi note"] for r in report], ["CREDIT NOTE", ""])

    def test_nontext_or_partial_row_is_not_silently_coerced(self):
        examples = [
            {"original_values": [""] * 52},
            {"original_values": [""] * 54},
            {"original_values": [0] + [""] * 52},
            {"original_values": "not-a-list"},
            {"missing": True},
            None,
        ]
        for example in examples:
            with self.subTest(example_type=str(type(example))):
                with self.assertRaises(ValueError):
                    credit.generate_credit_note_report_from_53(
                        [example], approved_53_headers=list(HEADERS)
                    )

    def test_explicit_report_is_not_auto_approved_for_release(self):
        _, summary = credit.generate_credit_note_report_from_53(
            [raw()], approved_53_headers=list(HEADERS)
        )
        self.assertEqual(summary["release_status"], "REVIEW_REQUIRED")
        self.assertFalse(summary["independent_source_approval"])


if __name__ == "__main__":
    unittest.main()
