"""Independent repository-contract tests for report header/worksheet safety.

Synthetic positional evidence only. Never opens financial databases or writes.
"""
import json
from pathlib import Path
import unittest

from invoice_source_schema import (
    HEADERS_53, HEADERS_34, HEADERS_35,
    sheet_layout, row_layout, export_values_53,
)


class ApprovedHeaderContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            Path(__file__).with_name("invoice_import_contract.json").read_text()
        )

    def test_literal_frozen_53_header_contract(self):
        self.assertEqual(len(HEADERS_53), 53)
        self.assertEqual(HEADERS_53, self.contract["headers"])
        self.assertEqual(HEADERS_53[6], "Branch Code")
        self.assertEqual(HEADERS_53[10], "Branch Code")
        self.assertEqual(HEADERS_53[7], "Client Name")
        self.assertEqual(HEADERS_53[12], "Invoice No")
        self.assertEqual(HEADERS_53[20],
                         "Payment Received ( If With GST or Excluding GST)")

    def test_original_34_agrees_with_separately_recorded_contract(self):
        self.assertEqual(len(HEADERS_34), 34)
        self.assertEqual(HEADERS_34, self.contract["original_source_headers_34"])
        self.assertEqual(HEADERS_34, HEADERS_53[:8] + HEADERS_53[11:37])

    def test_35_preserves_second_branch_code_position(self):
        self.assertEqual(len(HEADERS_35), 35)
        self.assertEqual(HEADERS_35[:8], HEADERS_34[:8])
        self.assertEqual(HEADERS_35[8], "Branch Code")
        self.assertEqual(HEADERS_35[9:], HEADERS_34[8:])
        self.assertEqual([i for i, h in enumerate(HEADERS_35)
                          if h == "Branch Code"], [6, 8])

    def test_source_sheet_accepts_only_exact_approved_34_and_35(self):
        for h, n in ((HEADERS_34, 34), (HEADERS_35, 35)):
            self.assertIsNotNone(sheet_layout("Invoice Details.", h))
            self.assertEqual(sheet_layout("Invoice Details.", h)[0], n)
            for name in ("Invoice Details", "invoice details.", "Sheet1", ""):
                self.assertIsNone(sheet_layout(name, h))

    def test_swapped_header_fails_closed(self):
        for h in (HEADERS_34, HEADERS_35, HEADERS_53):
            swapped = list(h)
            swapped[2], swapped[3] = swapped[3], swapped[2]
            self.assertIsNone(sheet_layout("Invoice Details.", swapped))
            with self.assertRaises(ValueError):
                row_layout({"original_headers": swapped,
                            "original_values": [""] * len(swapped)})

    def test_35_values_project_to_correct_53_positions(self):
        source = [f"source_{i}" for i in range(35)]
        report = export_values_53({
            "original_headers": HEADERS_35,
            "original_values": source,
        })
        self.assertEqual(len(report), 53)
        self.assertEqual(report[:8], source[:8])
        self.assertEqual(report[10], source[8])
        self.assertEqual(report[11:37], source[9:])
        self.assertEqual(report[8:10], ["", ""])
        self.assertEqual(report[37:], [""] * 16)

    def test_34_values_project_without_inventing_model_columns(self):
        source = [f"source_{i}" for i in range(34)]
        report = export_values_53({
            "original_headers": HEADERS_34,
            "original_values": source,
        })
        self.assertEqual(report[:8], source[:8])
        self.assertEqual(report[8:11], ["", "", ""])
        self.assertEqual(report[11:37], source[8:])
        self.assertEqual(report[37:], [""] * 16)

    def test_53_values_remain_positional_and_unchanged(self):
        source = [f"source_{i}" for i in range(53)]
        report = export_values_53({
            "original_headers": HEADERS_53,
            "original_values": source,
        })
        self.assertEqual(report, source)
        self.assertIsNot(report, source)


if __name__ == "__main__":
    unittest.main()
