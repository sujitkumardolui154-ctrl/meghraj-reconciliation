"""Owner-approved Stage 6 deployment governance checks."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
RULES=ROOT/"AGENTS.md"

class DeploymentGovernanceTests(unittest.TestCase):
    def test_owner_locked_destination_and_approval_gate(self):
        text=RULES.read_text(encoding="utf-8")
        for requirement in (
            "LIGHTSAIL_FIRST", "EC2_PROPOSAL_ONLY",
            "ARCHITECTURE_CHANGE=BLOCKED_PENDING_OWNER_APPROVAL",
            "explicit approval", "recurring", "financial write",
            "Google Cloud Run", "Lightsail",
            "source audit", "rollback", "Firebase"):
            self.assertIn(requirement,text)
    def test_no_default_deploy_of_extra_server_in_existing_stage6_workflow(self):
        text=(ROOT/".github/workflows/sbi_stage6_migration.yml").read_text()
        for unsafe in ("aws ec2 run-instances", "terraform apply", "cdk deploy",
                       "aws cloudformation deploy", "gcloud run deploy"):
            self.assertNotIn(unsafe,text)
if __name__=="__main__":
    unittest.main()
