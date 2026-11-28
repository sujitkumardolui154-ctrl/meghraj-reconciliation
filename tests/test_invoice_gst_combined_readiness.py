"""Targeted offline tests for invoice/GST combined read-only readiness only."""
import importlib.util
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "sbi_invoice_combined_readiness",
    ROOT/"scripts/sbi_invoice_gst_combined_readiness.py")
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
GATE_SPEC=importlib.util.spec_from_file_location(
    "sbi_invoice_original_private_gate",
    ROOT/"scripts/sbi_invoice_gst_private_qa_gate.py")
gate=importlib.util.module_from_spec(GATE_SPEC)
GATE_SPEC.loader.exec_module(gate)


def sample(ready=False):
    return {
      "source": {
        "owner_approved_pdf_template": "APPROVED_REFERENCE_LOCKED",
        "branch_master_hash_checked": ready,
        "approved_pdf_sha256_checked": ready,
        "branch_master_source_status":
          "WORKING_REVIEW_NOT_APPROVED_FOR_AUTOMATIC_IMPORT",
        "private_vendor_bundle_status":
          "OWNER_SOURCE_ARCHIVE_HASH_VERIFIED" if ready else "NOT_READ",
        "original_logo_hash_checked": ready,
      },
      "isolated_qa_database": {
        "status": "STAGING_SCHEMA_PRESENT" if ready else "NOT_CONNECTED_NOT_TESTED",
        "private_vendor_profile_present": ready,
        "verified_branch_records": 1 if ready else 0,
        "production_write": False,
      },
      "aws_ingress": {
        "status": "UNAUTHENTICATED_INGRESS_PROTECTED" if ready
                  else "NOT_CONNECTED_NOT_TESTED",
      },
      "reconciliation_financial_writes": False,
    }


class CombinedReadinessTests(unittest.TestCase):
    def test_existing_gate_is_reused_without_reimplementing_decision(self):
        report=mod.combine(sample(False), gate.evaluate_staging_preflight)
        self.assertEqual(report["status"],"BLOCKED_PRIVATE_PREREQUISITES")
        self.assertIn("MASTER_FILE_SHA256_VERIFIED",report["source_outstanding"])

    def test_even_fully_ready_source_does_not_pass_real_user_e2e_or_release(self):
        report=mod.combine(sample(True), gate.evaluate_staging_preflight)
        self.assertEqual(report["status"],
                         "STAGING_PREREQUISITES_READY_EXTERNAL_ACCEPTANCE_PENDING")
        self.assertEqual(report["authenticated_aws_e2e"],"NOT_TESTED_BY_THIS_COMMAND")
        self.assertEqual(report["production_deployment"],"BLOCKED")
        self.assertEqual(report["financial_apply"],"LOCKED")
        self.assertEqual(report["database_write"],"NONE")
        self.assertIn("GST01_MULTI_MONTH_TAX_PERIOD_POLICY_APPROVAL",
                      report["required_independent_acceptance"])

    def test_no_network_or_db_without_opt_in(self):
        r=Mock()
        r.source_review.return_value={"missing_source_files":True}
        payload=mod.collect(r)
        self.assertEqual(payload["isolated_qa_database"]["status"],
                         "NOT_CONNECTED_NOT_TESTED")
        self.assertEqual(payload["aws_ingress"]["status"],
                         "NOT_CONNECTED_NOT_TESTED")
        r.database_review.assert_not_called()
        r.public_access_review.assert_not_called()

    def test_opt_in_reads_use_original_functions(self):
        r=Mock(PUBLIC_AWS_HOST="https://example.invalid")
        r.source_review.return_value={}
        r.database_review.return_value={"status":"ISOLATED_QA_DSN_MISSING"}
        r.public_access_review.return_value={"status":"AWS_INGRESS_UNREACHABLE"}
        p=mod.collect(r,qa_db=True,check_public_ingress=True)
        r.database_review.assert_called_once()
        r.public_access_review.assert_called_once_with("https://example.invalid")
        self.assertFalse(p["reconciliation_financial_writes"])

    def test_invalid_gate_never_fakes_authorization(self):
        with self.assertRaises(ValueError):
            mod.combine(sample(True), lambda _: {
                "production_deployment":"AUTHORIZED",
                "financial_allocation":"NOT_PERMITTED",
                "ready_for_authenticated_private_qa":True,
            })

    def test_json_existing_readiness_reused_and_missing_remains_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"evidence.json"
            path.write_text(json.dumps(sample(False)),encoding="utf-8")
            self.assertEqual(mod.main(["--preflight-json",str(path),
                                       "--assert-source-ready"]),2)
            self.assertEqual(mod.main(["--preflight-json",str(path),
                                       "--master","/not/allowed"]),3)


if __name__=="__main__":
    unittest.main()
