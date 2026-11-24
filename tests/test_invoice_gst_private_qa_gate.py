"""Combined private QA readiness gate regression — no actual AWS/DB access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sbi_invoice_gst_private_qa_gate",
    ROOT / "scripts" / "sbi_invoice_gst_private_qa_gate.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

GOOD = {
    "source": {
        "owner_approved_pdf_template": "APPROVED_REFERENCE_LOCKED",
        "branch_master_hash_checked": True,
        "branch_master_source_status": "WORKING_REVIEW_NOT_APPROVED_FOR_AUTOMATIC_IMPORT",
        "private_vendor_bundle_status": "OWNER_SOURCE_ARCHIVE_HASH_VERIFIED",
        "original_logo_hash_checked": True,
    },
    "isolated_qa_database": {
        "status": "STAGING_SCHEMA_PRESENT",
        "private_vendor_profile_present": True,
        "verified_branch_records": 1,
        "production_write": False,
    },
    "aws_ingress": {"status": "UNAUTHENTICATED_INGRESS_PROTECTED"},
    "reconciliation_financial_writes": False,
    "authenticated_aws_staging_test": "NOT_PERFORMED",
}


class PrivateQaDecisionTests(unittest.TestCase):
    def test_ready_for_auth_private_qa_not_production(self):
        result = gate.evaluate_staging_preflight(GOOD)
        self.assertTrue(result["ready_for_authenticated_private_qa"])
        self.assertEqual(result["status"],
                         "READY_FOR_OPERATOR_AUTHENTICATED_PRIVATE_QA")
        self.assertEqual(result["production_deployment"], "NOT_AUTHORIZED")
        self.assertEqual(result["authenticated_aws_e2e"], "NOT_VERIFIED_BY_THIS_GATE")

    def test_missing_qa_database_fails_closed(self):
        payload = json.loads(json.dumps(GOOD))
        payload["isolated_qa_database"] = {"status": "NOT_CONNECTED_NOT_TESTED"}
        result = gate.evaluate_staging_preflight(payload)
        self.assertFalse(result["ready_for_authenticated_private_qa"])
        self.assertIn("ISOLATED_QA_DATABASE_SCHEMAS_PRESENT", result["outstanding"])

    def test_unverified_branches_and_vendor_profile_fail_closed(self):
        payload = json.loads(json.dumps(GOOD))
        payload["isolated_qa_database"]["verified_branch_records"] = 0
        payload["isolated_qa_database"]["private_vendor_profile_present"] = False
        result = gate.evaluate_staging_preflight(payload)
        self.assertFalse(result["ready_for_authenticated_private_qa"])
        self.assertIn("INDEPENDENTLY_VERIFIED_SBI_BRANCHES_EXIST", result["outstanding"])
        self.assertIn("PRIVATE_VENDOR_PROFILE_INSERTED", result["outstanding"])

    def test_public_200_not_interpreted_as_safety(self):
        payload = json.loads(json.dumps(GOOD))
        payload["aws_ingress"] = {"status": "UNEXPECTED_PUBLIC_ACCESS_RESULT", "http_status":200}
        result = gate.evaluate_staging_preflight(payload)
        self.assertFalse(result["ready_for_authenticated_private_qa"])
        self.assertIn("PUBLIC_AWS_ACCESS_NOT_PROVEN_OPEN", result["outstanding"])

    def test_financial_write_flag_must_be_explicitly_false(self):
        payload = json.loads(json.dumps(GOOD))
        payload["reconciliation_financial_writes"] = None
        result = gate.evaluate_staging_preflight(payload)
        self.assertFalse(result["ready_for_authenticated_private_qa"])
        self.assertIn("NO_PRODUCTION_FINANCIAL_WRITES", result["outstanding"])

    def test_cli_fails_nonzero_without_source_or_db(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "preflight.json"
            target.write_text(json.dumps({
                "source": {"missing_source_files": True},
                "isolated_qa_database": {"status":"NOT_CONNECTED_NOT_TESTED"},
                "aws_ingress": {"status":"NOT_CONNECTED_NOT_TESTED"},
                "reconciliation_financial_writes": False,
            }))
            self.assertEqual(gate.main([
                "--preflight-json", str(target), "--assert-ready"
            ]), 2)

if __name__ == "__main__":
    unittest.main()
