"""Offline, no-cloud AWS staging release-gate regression."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "staging" / "aws_lightsail"))
from aws_import_auth_preflight import evaluate_aws_import_readiness


class AWSImportAuthPreflightTests(unittest.TestCase):
    def test_empty_environment_denies(self):
        result = evaluate_aws_import_readiness({})
        self.assertFalse(result.ready)
        self.assertIn("independent_gateway_auth_not_verified", result.blockers)

    def test_basic_auth_cannot_grant_import_access(self):
        result = evaluate_aws_import_readiness({
            "PREVIEW_USERNAME": "demo", "PREVIEW_PASSWORD": "not-a-real-secret"
        })
        self.assertFalse(result.ready)

    def test_headers_cannot_grant_import_access(self):
        result = evaluate_aws_import_readiness({
            "X-DIL-Import": "1", "X-Forwarded-User": "admin",
        })
        self.assertFalse(result.ready)

    def test_operator_flags_alone_are_not_identity_proof(self):
        result = evaluate_aws_import_readiness({
            "SBI_AWS_GATEWAY_AUTH_VERIFIED": "true",
            "SBI_AWS_BACKEND_AUTH_VERIFIED": "true",
            "SBI_AWS_PRIVATE_NETWORK_VERIFIED": "true",
            "SBI_AWS_NO_FINANCIAL_WRITES": "true",
        })
        self.assertFalse(result.ready)
        self.assertEqual(result.blockers, ("external_auth_evidence_required",))

    def test_no_secrets_exposed_in_blockers(self):
        secret = "sensitive-example-value"
        result = evaluate_aws_import_readiness({"PREVIEW_PASSWORD": secret})
        self.assertNotIn(secret, str(result))


if __name__ == "__main__":
    unittest.main()
