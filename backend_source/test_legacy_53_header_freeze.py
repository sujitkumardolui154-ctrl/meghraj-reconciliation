"""Frozen legacy 53-column CSV header regression contract.

Independently repeated labels are intentionally retained: this test MUST NOT
derive its approved expected headers from invoice_import_contract.json.
Synthetic and source-only: no external access or invoice records.
"""
import ast
import csv
import io
import json
from pathlib import Path
import unittest

from invoice_source_schema import HEADERS_53, HEADERS_35, export_values_53

APPROVED_LEGACY_53_HEADERS = [
    "Client Name",
    "FY",
    "Invoice Branch",
    "Invoice Generate Location",
    "Month",
    "Invoice Date",
    "Branch Code",
    "Client Name",
    "Model SOL ID",
    "Model Proper Client Name",
    "Branch Code",
    "GST NO",
    "Invoice No",
    "Taxable Amount",
    "CGST",
    "SGST",
    "Total Bill Amount",
    "Less TDS",
    "Actual Reciaveable Ammount Deductionof  TDS (Including GST)",
    "Taxable Amount  Less TDS( Without GST",
    "Payment Received ( If With GST or Excluding GST)",
    "Payment Received ( If With GST or Excluding GST)_ Payment Date",
    "GST Payment_ Blance",
    "GST Payment Date",
    "TOTAL Paymnet Received( BASE Amt + GST)",
    "Creit Note Ammount",
    "Total Payment( Base Amt+ GST )-Credit Note & TDS",
    "Outstanding Balance/ Negetive Blance",
    "Mode",
    "Remraks",
    "Mail Id",
    "REMRAKS",
    "Sbi Contcat Number",
    "Meghraj Contact Number",
    "Others Remraks",
    "New Invoice Agansit of Credit Note",
    "Date",
    "Model Reconciliation Status",
    "Model Payment Source Row",
    "Model Matched Bank Credit",
    "Model TDS %",
    "Model Expected Bank Credit",
    "Model Signed Difference",
    "Model Matching Evidence",
    "Model Invoice Payment Eligibility",
    "Model Normalized SOL Key",
    "Model SOL Mapping Evidence",
    "Model v2.2 Evidence Classification",
    "Model v2.2 Payment / Reference Risk",
    "Model v2.2 Allocation Evidence",
    "Model Original Excel Error Cells",
    "Model Stage B Shadow Status (NOT ACTIVE)",
    "Model v2.2 Audit Execution Version",
]


class Legacy53HeaderFreezeTest(unittest.TestCase):
    def test_frozen_header_labels_exact_and_ordered(self):
        self.assertEqual(len(APPROVED_LEGACY_53_HEADERS), 53)
        self.assertEqual(HEADERS_53, APPROVED_LEGACY_53_HEADERS)
        contract = json.loads(
            Path(__file__).with_name("invoice_import_contract.json").read_text()
        )
        self.assertEqual(contract["headers"], APPROVED_LEGACY_53_HEADERS)

    def test_duplicate_header_names_retained(self):
        self.assertEqual([i for i, value in enumerate(APPROVED_LEGACY_53_HEADERS)
                          if value == "Branch Code"], [6, 10])
        self.assertEqual([i for i, value in enumerate(APPROVED_LEGACY_53_HEADERS)
                          if value == "Client Name"], [0, 7])

    def test_csv_writer_preserves_every_header_exactly(self):
        stream = io.StringIO(newline="")
        csv.writer(stream).writerow(APPROVED_LEGACY_53_HEADERS)
        stream.seek(0)
        self.assertEqual(next(csv.reader(stream)), APPROVED_LEGACY_53_HEADERS)

    def test_legacy_snapshot_endpoint_rejects_any_header_drift(self):
        # Static AST check avoids importing a live Firestore-backed Flask app.
        tree = ast.parse(Path(__file__).with_name("report_api.py").read_text())
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "handle_snapshot_reports")
        comparisons = [
            node for node in ast.walk(function)
            if isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "headers"
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.NotEq)
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Name)
            and node.comparators[0].id == "HEADERS_53"
        ]
        self.assertEqual(len(comparisons), 1,
                         "Legacy snapshot exporter must fail closed on exact header mismatch")

    def test_35_source_projection_does_not_replace_53_csv_headers(self):
        projected = export_values_53({
            "original_headers": HEADERS_35,
            "original_values": [str(i) for i in range(35)],
        })
        self.assertEqual(len(projected), 53)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(HEADERS_53)
        writer.writerow(projected)
        stream.seek(0)
        rows = list(csv.reader(stream))
        self.assertEqual(rows[0], APPROVED_LEGACY_53_HEADERS)
        self.assertEqual(len(rows[1]), 53)


if __name__ == "__main__":
    unittest.main()
