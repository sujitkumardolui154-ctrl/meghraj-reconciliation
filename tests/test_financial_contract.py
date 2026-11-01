"""Financial source-contract regression tests for the uploaded SBI backend.

These validate recovered reporting behavior only. They deliberately do NOT
certify settlement/allocation or the v2.51 financial engine.
"""
import importlib
import types
from unittest.mock import patch
import json
import sys
import unittest
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_source"
sys.path.insert(0, str(BACKEND))


class FinancialSourceContractTests(unittest.TestCase):
    def test_required_import_header_contract_exists(self):
        contract = BACKEND / "invoice_import_contract.json"
        self.assertTrue(contract.is_file(), "Missing authoritative 53-header invoice import contract")
        data = json.loads(contract.read_text(encoding="utf-8"))
        self.assertEqual(len(data["headers"]), 53)
        # The approved original 53-column invoice sheet has duplicate labels.
        # Preserve them by position rather than inventing unique headings.
        self.assertEqual(data["headers"][0], "Client Name")
        self.assertEqual(data["headers"][7], "Client Name")
        self.assertEqual(data["headers"][6], "Branch Code")
        self.assertEqual(data["headers"][10], "Branch Code")
        self.assertEqual(data["headers"][12], "Invoice No")
        self.assertIn("Payment Received", data["headers"][20])

    def test_reporting_classification_and_no_mutation(self):
        # Test recovered classification independently while the official
        # invoice-header contract is missing; do not invent its 53 headers.
        stub = types.ModuleType("invoice_source_schema")
        stub.row_layout = lambda row: (_ for _ in ()).throw(
            AssertionError("row_layout must not be called by classify_payment")
        )
        with patch.dict(sys.modules, {"invoice_source_schema": stub}):
            sys.modules.pop("payment_report_rules", None)
            module = importlib.import_module("payment_report_rules")
        cases = [
            ("", "s", "unpaid"),
            ("0", "n", "unpaid"),
            ("100.50", "n", "ok"),
            ("1e2", "n", "ok"),
            ("1e2", "s", "error-value"),
            ("=100", "s", "error-value"),
            ("NaN", "n", "error-value"),
            ("abc", "s", "error-value"),
        ]
        for value, cell_type, expected in cases:
            with self.subTest(value=value, cell_type=cell_type):
                self.assertEqual(module.classify_payment(value, cell_type), expected)
        with self.assertRaises(ValueError):
            module.classify_payment(100, "n")

    def test_tds_reference_rounding_only(self):
        for taxable, rate, expected in [
            ("1000", "0", "0.00"),
            ("1000", "1", "10.00"),
            ("1000", "2", "20.00"),
            ("1000", "3", "30.00"),
            ("105.50", "3", "3.17"),
            ("100.50", "1", "1.01"),
        ]:
            actual = (Decimal(taxable) * Decimal(rate) / 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            self.assertEqual(actual, Decimal(expected))

    def test_full_financial_engine_release_not_certified(self):
        # Prevent this recovered reporting-only code from being promoted as
        # settlement engine v2.51 until integration is independently certified.
        marker = ROOT / "deployment" / "staging" / "financial_engine_certification.json"
        self.assertFalse(marker.exists(), "Certification must be independently checked by release review")


if __name__ == "__main__":
    unittest.main()
