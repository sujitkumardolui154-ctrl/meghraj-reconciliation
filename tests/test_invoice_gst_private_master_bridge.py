"""Synthetic GitHub v2.7 branch-rule -> private invoice master bridge QA."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "staging/invoice-gst/private_master_adapter.py"
spec = spec_from_file_location("sbi_gst_private_master_adapter", SOURCE)
adapter = module_from_spec(spec)
spec.loader.exec_module(adapter)

MASTER = [{"Official Branch Name": "QA VERIFIED KOLKATA BRANCH",
           "SOL ID": "03970", "Search Aliases": "QA VK BRANCH"}]
EVIDENCE = {
    ("QA VERIFIED KOLKATA BRANCH", "03970"): {
        "approved": True, "branch_key": "qa-03970",
        "invoice_branch": "KOLKATA", "invoice_generate_location": "KOLKATA",
        "customer_address": "QA ADDRESS ONLY", "recipient_title": "AGM",
        "verified_by": "qa-owner", "client_class": "SBI_BANK",
        "gstin": "19AAACS8577K3ZK"
    }
}


class BranchBridgeTests(unittest.TestCase):
    def test_complete_approved_private_master_projects_to_invoice_db(self):
        result = adapter.prepare_private_master_rows(MASTER, EVIDENCE)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "READY_FOR_PRIVATE_QA_IMPORT")
        self.assertEqual(result[0]["branch"]["sol_id"], "03970")
        self.assertEqual(result[0]["branch"]["client_name"], "QA VERIFIED KOLKATA BRANCH")

    def test_missing_private_evidence_must_not_mark_verified(self):
        result = adapter.prepare_private_master_rows(MASTER, {})
        self.assertEqual(result[0]["status"], "REVIEW_REQUIRED")
        self.assertNotIn("branch", result[0])

    def test_incomplete_location_never_guesses_sol(self):
        rows = [{"Official Branch Name": "R.B.O.", "SOL ID": "14877", "Search Aliases": ""}]
        result = adapter.prepare_private_master_rows(rows, {})
        self.assertEqual(result[0]["status"], "REVIEW_REQUIRED")
        self.assertIn("GITHUB_APPROVED_MASTER_MISMATCH", result[0]["flags"])

    def test_duplicate_master_collision_is_review_required(self):
        rows = MASTER + [dict(MASTER[0])]
        result = adapter.prepare_private_master_rows(rows, EVIDENCE)
        self.assertEqual(result[1]["status"], "REVIEW_REQUIRED")
        self.assertIn("DUPLICATE_OFFICIAL_SOL", result[1]["flags"])

    def test_non_text_sol_is_rejected_not_silently_converted(self):
        rows = [{"Official Branch Name": "QA VERIFIED KOLKATA BRANCH",
                 "SOL ID": 3970, "Search Aliases": ""}]
        result = adapter.prepare_private_master_rows(rows, EVIDENCE)
        self.assertEqual(result[0]["status"], "REVIEW_REQUIRED")
        self.assertIn("SOL_NOT_TEXT_OR_INVALID", result[0]["flags"])


if __name__ == "__main__":
    unittest.main()
