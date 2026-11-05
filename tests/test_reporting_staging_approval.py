"""Synthetic approval gate checks; no credentials or real financial data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_reporting_staging_approval import approved

SHA = "a" * 40
GOOD = dict(release_scope="reporting_only", decision="APPROVED_FOR_PRIVATE_STAGING",
            source_sha=SHA, dataset_sha256="b" * 64, reviewer="independent-reviewer",
            private_evidence_verified=True, financial_execution="RESTRICTED",
            production_traffic_change=False, financial_database_writes=False)

class ApprovalGateTests(unittest.TestCase):
    def test_synthetic_valid(self):
        self.assertTrue(approved(json.dumps(GOOD), SHA))

    def test_every_field_is_required(self):
        for key in GOOD:
            candidate = dict(GOOD)
            del candidate[key]
            with self.subTest(key=key):
                self.assertFalse(approved(json.dumps(candidate), SHA))

    def test_unsafe_changes_fail(self):
        for key, value in [("release_scope","finance"), ("source_sha","c"*64),
                           ("dataset_sha256","not-a-hash"), ("reviewer"," "),
                           ("private_evidence_verified",1), ("financial_execution","ENABLED"),
                           ("production_traffic_change",True), ("financial_database_writes",True)]:
            with self.subTest(key=key):
                self.assertFalse(approved(json.dumps({**GOOD,key:value}), SHA))

    def test_gh_sha_format_is_40_hex(self):
        self.assertEqual(len(SHA), 40)
        self.assertTrue(approved(json.dumps(GOOD), SHA))
        self.assertFalse(approved(json.dumps(GOOD), "a" * 64))

    def test_source_sha_mismatch_or_dataset_length_blocks(self):
        self.assertFalse(approved(json.dumps({**GOOD, "source_sha": "c" * 40}), SHA))
        self.assertFalse(approved(json.dumps({**GOOD, "dataset_sha256": "b" * 40}), SHA))

    def test_staging_workflow_gates_manual_deploy_on_protected_approval(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
                    "sbi-autonomous-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("\n  private-approval-gate:", workflow)
        self.assertIn("needs.private-approval-gate.outputs.approved == 'true'", workflow)
        self.assertIn("environment: staging", workflow)
        source_stage = workflow.split("\n  private-approval-gate:", 1)[0]
        self.assertNotIn("secrets.REPORTING_APPROVAL_JSON", source_stage)
        self.assertIn("secrets.REPORTING_APPROVAL_JSON",
                      workflow.split("\n  private-approval-gate:", 1)[1])
        self.assertIn("--no-traffic", workflow)
        self.assertIn("--no-allow-unauthenticated", workflow)

    def test_malformed_and_missing_fail(self):
        for raw in ("", "{}", "[]", "null", "{broken}"):
            self.assertFalse(approved(raw, SHA))

    def test_without_secret_command_fails_closed(self):
        script = Path(__file__).resolve().parents[1] / "tools" / "verify_reporting_staging_approval.py"
        env = os.environ.copy()
        env.pop("REPORTING_APPROVAL_JSON", None)
        proc = subprocess.run([sys.executable,str(script)],env=env,capture_output=True,text=True)
        self.assertEqual(proc.returncode,2)
        self.assertIn("BLOCKED",proc.stdout)

if __name__ == "__main__":
    unittest.main()
