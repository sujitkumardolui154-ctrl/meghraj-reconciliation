"""Verify real invoice preview preserves accept/reject decisions while annotating CNs."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / "backend_source"
sys.path.insert(0, str(BASE))
from invoice_source_schema import HEADERS_35


def candidate_row(number, invoice, note):
    values = [""] * len(HEADERS_35)
    values[10] = invoice
    values[18] = note
    return {"source_row": number, "original_values": values,
            "original_headers": list(HEADERS_35)}


def read_preview_module(parsed):
    fake_parser = types.ModuleType("invoice_excel_parser")
    fake_parser.parse_excel = lambda filename, data: parsed
    with patch.dict(sys.modules, {"invoice_excel_parser": fake_parser}):
        spec = importlib.util.spec_from_file_location(
            "preview_readonly_test", BASE / "invoice_import_preview.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class InvoicePreviewBridgeTests(unittest.TestCase):
    def test_new_credit_note_annotations_do_not_change_invoice_decisions(self):
        parsed = {"sheet": "Invoice Details.", "headers": list(HEADERS_35),
                  "rows": [
                      candidate_row(2, "MXPTEST01", "Credit Note @ 30/11/2024"),
                      candidate_row(3, "MXPTEST02", "PAID"),
                  ], "rejected": []}
        module = read_preview_module(parsed)
        result = module.build_preview("synthetic.xlsx", b"synthetic", set())
        self.assertEqual(result["summary"], {"total": 2, "ready_to_add": 2, "rejected": 0})
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual(result["credit_note_review"]["normal_or_dated_credit_note_count"], 1)
        self.assertEqual(result["credit_note_review"]["credit_note_import_ready"], False)
        self.assertEqual(result["database_changed"], False)

    def test_duplicate_invoice_rejections_unchanged(self):
        parsed = {"sheet": "Invoice Details.", "headers": list(HEADERS_35),
                  "rows": [
                      candidate_row(2, "MXPDUP1", "CREDIT NOTE"),
                      candidate_row(3, "MXPDUP1", "Credit Note @ 30/11/2024"),
                  ], "rejected": []}
        module = read_preview_module(parsed)
        result = module.build_preview("synthetic.xlsx", b"synthetic", set())
        self.assertEqual(result["summary"], {"total": 2, "ready_to_add": 0, "rejected": 2})
        self.assertTrue(all(
            "DUPLICATE_IN_UPLOADED_FILE" in row["reasons"]
            for row in result["rejected"]
        ))
        self.assertEqual(result["credit_note_review"]["normal_or_dated_credit_note_count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
