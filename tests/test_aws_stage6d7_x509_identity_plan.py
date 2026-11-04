"""SBI Stage 6D.7: non-mutating review tests and bad-plan denials."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"staging/aws_lightsail/stage6d7_validate_identity_plan.py"
PLAN=ROOT/"staging/aws_lightsail/stage6d7_x509_identity_plan.json"
spec=importlib.util.spec_from_file_location("stage6d7", SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class X509PlanSafetyTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads(PLAN.read_text(encoding="utf-8"))

    def test_all_controls_hold_at_source(self):
        c=module.review(self.plan)
        self.assertGreaterEqual(len(c),12)
        self.assertTrue(all(c.values()),[x for x,ok in c.items() if not ok])
        self.assertEqual(self.plan["production_cutover"],"BLOCKED")

    def test_wildcard_identity_must_fail(self):
        p=deepcopy(self.plan)
        p["planned_provider"]["principal_scope"]="POOL_WIDE"
        self.assertFalse(module.review(p)["EXACT_CLIENT_IDENTITY"])

    def test_different_condition_must_fail(self):
        p=deepcopy(self.plan)
        p["planned_provider"]["attribute_condition"]="true"
        self.assertFalse(module.review(p)["EXACT_CLIENT_IDENTITY"])

    def test_costly_managed_ca_must_fail(self):
        p=deepcopy(self.plan)
        p["costs"]["managed_ca"]="ENABLED"
        self.assertFalse(module.review(p)["NO_NEW_PAID_PROVIDER"])

    def test_creating_cert_or_provider_must_fail(self):
        p=deepcopy(self.plan)
        p["credentials"]["client_private_key"]="CREATED"
        p["planned_provider"]["state"]="ENABLED"
        self.assertFalse(module.review(p)["NO_CREDENTIAL_ISSUANCE"])
        self.assertFalse(module.review(p)["SEPARATE_X509_PROVIDER"])

    def test_unreviewed_change_cannot_grant_access(self):
        p=deepcopy(self.plan)
        p["permissions"]["iam_grants"]="roles/editor"
        p["permissions"]["firestore_write"]="ALLOWED"
        self.assertFalse(module.review(p)["NO_IAM_GRANTS"])
        self.assertFalse(module.review(p)["NO_FINANCIAL_ACCESS"])

    def test_source_audit_cannot_mark_approvals_complete(self):
        p=deepcopy(self.plan)
        p["approvals"]["owner_iam_x509_provider"]="APPROVED"
        self.assertFalse(module.review(p)["APPROVALS_ALL_PENDING"])

    def test_audit_never_handles_live_credentials_or_cloud(self):
        code=SCRIPT.read_text()
        for forbidden in ("import boto3", "import google", "import requests",
                          "subprocess", "os.system", "os.environ", "import firebase_admin"):
            self.assertNotIn(forbidden,code)

if __name__=="__main__":
    unittest.main()
