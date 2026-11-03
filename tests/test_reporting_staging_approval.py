"""Independent, synthetic staging-approval gate regression tests."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_reporting_staging_approval import approved

SHA = "a" * 64
GOOD = {
    "release_scope": "reporting_only",
    "decision": "APPROVED_FOR_PRIVATE_STAGING",
    "source_sha": SHA,
    "dataset_sha256": "b" * 64,
    "reviewer": "independent-reviewer",
    "private_evidence_verified": True,
    "financial_execution": "RESTRICTED",
    "production_traffic_change": False,
    "financial_database_writes": False,
}

class ApprovalGateTests(unittest.TestCase):
    def test_verified_synthetic_input(self):
        self.assertTrue(approved(json.dumps(GOOD), SHA))

    def test_missing_or_malformed_or_non_object(self):
        for raw in ("", "{", "[]", "null", '"string"', "{}"):
            with self.subTest(raw=raw):
                self.assertFalse(approved(raw, SHA))

    def test_every_required_field_fails_closed(self):
        for key in GOOD:
            altered = dict(GOOD)
            del altered[key]
            with self.subTest(key=key):
                self.assertFalse(approved(json.dumps(altered), SHA))

    def test_invalid_evidence_values_fail_closed(self):
        changes = (
            ("release_scope", "finance"),
            ("decision", "REVIEW_REQUIRED"),
            ("source_sha", "f" * 64),
            ("source_sha", "not-a-commit"),
            ("dataset_sha256", "unverified"),
            ("reviewer", "  "),
            ("private_evidence_verified", 1),
            ("financial_execution", "ENABLED"),
            ("production_traffic_change", True),
            ("financial_database_writes", True),
        )
        for key, value in changes:
            altered = dict(GOOD, **{key: value})
            with self.subTest(key=key, value=value):
                self.assertFalse(approved(json.dumps(altered), SHA))

    def test_missing_environment_fails_closed(self):
        script = ROOT / "tools" / "verify_reporting_staging_approval.py"
        env = os.environ.copy()
        env.pop("REPORTING_APPROVAL_JSON", None)
        result = subprocess.run([sys.executable, str(script)], env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED", result.stdout)
        self.assertNotIn("dataset_sha256", result.stdout)

if __name__ == "__main__":
    unittest.main()
