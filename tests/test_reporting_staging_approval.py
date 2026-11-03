"""Synthetic approval gate checks; no credentials or real financial data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_reporting_staging_approval import approved

SHA = "a" * 64
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
