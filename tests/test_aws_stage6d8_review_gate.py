"""Stage 6D.8 plan review; no external integrations or elevated privileges."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/"staging/aws_lightsail/stage6d8_review_gate.py"
PLAN = ROOT/"staging/aws_lightsail/stage6d7_x509_identity_plan.json"
spec=importlib.util.spec_from_file_location("sbi_stage6d8", SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Stage6D8Tests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads(PLAN.read_text(encoding="utf-8"))

    def test_proposal_pass_is_not_approval(self):
        checks, blockers=mod.assess(self.plan)
        self.assertTrue(all(checks.values()))
        self.assertGreaterEqual(len(blockers),7)
        self.assertEqual(self.plan["real_firebase_login"],"NOT_TESTED")
        self.assertEqual(self.plan["production_cutover"],"BLOCKED")
        self.assertEqual(self.plan["approvals"]["independent_security_review"],"PENDING")

    def test_no_new_server_or_authorized_provider(self):
        plan=deepcopy(self.plan)
        plan["estimated_new_aws_instances"]=1
        plan["planned_provider"]["state"]="ENABLED"
        checks,_=mod.assess(plan)
        self.assertFalse(checks["EXISTING_LIGHTSAIL_ONLY"])
        self.assertFalse(checks["PROPOSAL_STILL_INERT"])

    def test_no_wildcard_subject(self):
        plan=deepcopy(self.plan)
        plan["planned_provider"]["attribute_condition"]="true"
        self.assertFalse(mod.assess(plan)[0]["EXACT_SPIFFE_SUBJECT"])

    def test_no_unapproved_financial_or_user_access(self):
        plan=deepcopy(self.plan)
        plan["permissions"]["firestore_write"]="ALLOWED"
        self.assertFalse(mod.assess(plan)[0]["NO_FINANCE_OR_USER_WRITES"])

    def test_no_assumption_of_free_ca_or_approved_iam(self):
        plan=deepcopy(self.plan)
        plan["costs"]["managed_ca"]="PAID_SERVICE_CREATED"
        plan["approvals"]["cost_acceptance"]="APPROVED"
        checks,_=mod.assess(plan)
        self.assertFalse(checks["UNKNOWN_CA_COST_NOT_ASSUMED_FREE"])
        self.assertFalse(checks["APPROVALS_NOT_PRETENDED"])

    def test_no_live_clients_or_commands(self):
        source=SCRIPT.read_text(encoding="utf-8")
        for item in ("import boto3", "import google", "import requests", "import firebase_admin",
                     "subprocess", "os.system(", "os.environ", "docker run", "gcloud "):
            self.assertNotIn(item,source)

if __name__=="__main__":
    unittest.main()
