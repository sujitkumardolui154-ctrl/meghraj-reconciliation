"""Offline synthetic contract tests for combined engine gating."""
from pathlib import Path
import importlib.util
import unittest

src = Path(__file__).resolve().parents[1] / "readiness_gate.py"
spec = importlib.util.spec_from_file_location("combined_readiness", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class CombinedGateTests(unittest.TestCase):
    def test_empty_evidence_blocks_every_capability(self):
        result = mod.assess_combined_readiness({})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(set(result["blocked_capabilities"]), set(mod.REQUIRED_CAPABILITIES))
        self.assertFalse(result["deployment_performed"])

    def test_synthetic_gst_ci_does_not_certify_finance(self):
        evidence = {"gst_v2_7_original_invoice_parity": {
            "status": "SYNTHETIC_PASS", "reviewer": "ci", "evidence_ref": "run-123"}}
        result = mod.assess_combined_readiness(evidence)
        self.assertEqual(result["checks"]["gst_v2_7_original_invoice_parity"], "BLOCKED")

    def test_missing_review_and_evidence_deny_pass(self):
        for record in (True, "PASS", {"status": "PASS"},
                       {"status": "PASS", "reviewer": "", "evidence_ref": "x"},
                       {"status": "PASS", "reviewer": "reviewer", "evidence_ref": ""}):
            result = mod.assess_combined_readiness({"no_financial_writes": record})
            self.assertEqual(result["checks"]["no_financial_writes"], "BLOCKED")

    def test_independent_gates_required_even_with_all_other_checks(self):
        evidence = {key: {"status": "PASS", "reviewer": "independent",
                           "evidence_ref": "private-evidence-hash"}
                    for key in mod.REQUIRED_CAPABILITIES
                    if key != "financial_source_to_output_value_parity"}
        result = mod.assess_combined_readiness(evidence)
        self.assertIn("financial_source_to_output_value_parity", result["blocked_capabilities"])
        with self.assertRaises(mod.FinancialEngineNotReady):
            mod.require_combined_staging_readiness(evidence)

    def test_all_certified_is_review_ready_not_prod(self):
        evidence = {key: {"status": "PASS", "reviewer": "independent",
                           "evidence_ref": "private-evidence-hash"}
                    for key in mod.REQUIRED_CAPABILITIES}
        result = mod.require_combined_staging_readiness(evidence)
        self.assertEqual(result["status"], "CANDIDATE_REVIEW_READY")
        self.assertEqual(result["production_financial_cutover"], "BLOCKED")
        self.assertFalse(result["approved_for_settlement"])
        self.assertFalse(result["deployment_performed"])
        self.assertFalse(result["financial_write_performed"])

if __name__ == "__main__":
    unittest.main()
