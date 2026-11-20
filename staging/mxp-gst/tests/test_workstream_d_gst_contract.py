"""Workstream D: GST staging source contract gate. Synthetic/offline; no financial data."""
import importlib.util
import json
from pathlib import Path
import unittest

GST_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = GST_ROOT / "config" / "approved_alias_rules_v2_7.json"
MATCHER_PATH = GST_ROOT / "matcher.py"

spec = importlib.util.spec_from_file_location("mxp_gst_matcher_d_gate", MATCHER_PATH)
matcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matcher)


class WorkstreamDGstBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    def test_fixed_16_column_contract_and_exact_duplicate_branch_code(self):
        expected = [
            "FY", "Invoice Branch", "Invoice Generate Location", "Month",
            "Invoice Date", "Branch Code", "Client Name", "Branch Code",
            "GST NO", "Invoice No", "Taxable Amount", "CGST", "SGST",
            "Total Bill Amount", "Error / Verification Flags",
            "Original Extracted Branch Name",
        ]
        self.assertEqual(self.rules["version"], "2.7")
        self.assertEqual(self.rules["column_count"], 16)
        self.assertEqual(self.rules["headers"], expected)

    def test_production_write_is_explicitly_disabled(self):
        self.assertIs(self.rules["automatic_write_to_production"], False)
        self.assertEqual(self.rules["status"], "REVIEW_REQUIRED")

    def test_unverified_source_never_gets_autofilled_identity(self):
        for value in ("", "AMCC", "RBO-III", "R.B.O."):
            result = matcher.resolve_name(value, [])
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            self.assertNotIn("sol_id", result)

    def test_leading_zero_sol_is_preserved_as_text(self):
        master = [{
            "Official Branch Name": "TEST BRANCH",
            "SOL ID": "03970",
            "Search Aliases": "TEST ALIAS"
        }]
        result = matcher.resolve_name("test alias", master)
        self.assertEqual(result["status"], "MATCHED")
        self.assertEqual(result["sol_id"], "03970")
        self.assertIsInstance(result["sol_id"], str)

    def test_ambiguous_master_does_not_auto_resolve(self):
        master = [
            {"Official Branch Name": "SAMPLE", "SOL ID": "00001", "Search Aliases": ""},
            {"Official Branch Name": "SAMPLE", "SOL ID": "00002", "Search Aliases": ""},
        ]
        result = matcher.resolve_name("SAMPLE", master)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["reason"], "MULTIPLE_MASTER_MATCHES")

    def test_gstin_mapping_requires_verified_classification(self):
        self.assertEqual(self.rules["gstin"]["SBI_BANK"], "19AAACS8577K3ZK")
        self.assertEqual(self.rules["gstin"]["SBI_FUND"], "19AAACS7339D1ZB")
        self.assertIsNone(self.rules["gstin"]["OTHER"])
        self.assertIsNone(self.rules["gstin"]["UNVERIFIED"])


if __name__ == "__main__":
    unittest.main()
