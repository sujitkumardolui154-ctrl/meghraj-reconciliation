"""Regression checks for the immutable admin-approved original 35-column layout.

Synthetic values only. No Firestore, AWS, finance writes, or production imports.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))

from invoice_source_schema import (
    HEADERS_34, HEADERS_35, HEADERS_53, invoice_number, row_layout, sheet_layout
)
from credit_note_53_adapter import header_mapping, project_credit_notes, REPORT_HEADERS


class Approved35SourceLayoutTests(unittest.TestCase):
    def test_approved_projection_matches_exact_original_header(self):
        self.assertEqual(len(HEADERS_35), 35)
        self.assertEqual(HEADERS_35[:8], HEADERS_34[:8])
        self.assertEqual(HEADERS_35[8], "Branch Code")
        self.assertEqual(HEADERS_35[9:], HEADERS_34[8:])
        self.assertEqual([i for i, x in enumerate(HEADERS_35) if x == "Branch Code"], [6, 8])

    def test_sheet_layouts_preserved(self):
        self.assertEqual(sheet_layout("Invoice Details.", HEADERS_35), (35, 10))
        self.assertEqual(sheet_layout("Invoice Details.", HEADERS_34), (34, 9))
        self.assertEqual(sheet_layout("Invoice Details.", HEADERS_53), (53, 12))
        self.assertIsNone(sheet_layout("Wrong sheet", HEADERS_35))
        bad = HEADERS_35.copy()
        bad[8] = "Changed Branch Code"
        self.assertIsNone(sheet_layout("Invoice Details.", bad))

    def test_35_row_indexes_and_text_preservation(self):
        values = [""] * 35
        values[6] = "001234"  # Source G, authoritative branch identity.
        values[8] = "009999"  # Source I, preserved separately.
        values[10] = "MXP-00001"  # Invoice K.
        values[18] = "CREDIT NOTE"  # Payment S.
        values[25] = "0"  # Balance Z.
        record = {"original_values": values, "original_headers": HEADERS_35.copy()}
        self.assertEqual(row_layout(record)[:4], (35, 10, 18, 25))
        self.assertEqual(invoice_number(record), "MXP-00001")
        self.assertEqual(record["original_values"][6], "001234")
        self.assertEqual(record["original_values"][8], "009999")
        self.assertEqual(record["original_values"][18], "CREDIT NOTE")
        self.assertEqual(record["original_values"][25], "0")

    def test_fail_closed_on_header_or_value_mutation(self):
        row = {"original_values": [""] * 35, "original_headers": HEADERS_35.copy()}
        row["original_headers"][8] = "Unknown"
        with self.assertRaises(ValueError):
            row_layout(row)
        row["original_headers"] = HEADERS_35.copy()
        row["original_values"][6] = 1234
        with self.assertRaises(ValueError):
            row_layout(row)
        with self.assertRaises(ValueError):
            row_layout({"original_values": [""] * 33})

    def test_credit_note_uses_source_g_not_extra_i(self):
        m = header_mapping(tuple(HEADERS_35))
        self.assertEqual(m["Branch Code"], 6)
        self.assertEqual(m["Invoice No"], 10)
        self.assertEqual(m["Payment Received (If With GST or Excluding GST)"], 18)
        row = [""] * 35
        row[6], row[8], row[10], row[18] = "001234", "009999", "INV-1", "CREDIT NOTE"
        result, summary = project_credit_notes(HEADERS_35, [row])
        self.assertEqual(result[0]["Branch Code"], "001234")
        self.assertEqual(result[0]["Invoice No"], "INV-1")
        self.assertEqual(result[0]["Credi note"], "CREDIT NOTE")
        self.assertEqual(summary["credit_note_invoices"], 1)
        self.assertEqual(summary["report_columns"], len(REPORT_HEADERS))
        self.assertFalse(summary["source_modified"])
        with self.assertRaises(ValueError):
            project_credit_notes(HEADERS_35, [dict(zip(HEADERS_35, row))])

    def test_35_credit_note_rejects_wrong_header_even_if_same_width(self):
        changed = HEADERS_35.copy()
        changed[8] = "Model SOL ID"
        with self.assertRaises(ValueError):
            header_mapping(changed)


if __name__ == "__main__":
    unittest.main()
