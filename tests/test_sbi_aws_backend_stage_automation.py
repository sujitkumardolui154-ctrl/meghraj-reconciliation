"""Source-only safety contracts for separate approval-gated AWS backend staging."""
from pathlib import Path
import re
import unittest

BASE = Path(__file__).resolve().parents[1]
DIR = BASE / "staging/aws_backend_readonly"


class BackendStagingAutomationTests(unittest.TestCase):
    def test_executor_runs_only_backend_stage_and_exact_main_source(self):
        script = (DIR / "stage_release_root.sh").read_text()
        for required in (
            "NAME=sbi-backend-readonly-stage",
            "NETWORK=sbi-backend-readonly-net",
            "SHA must be the reviewed main HEAD",
            "refs/heads/main",
            "BACKEND_STAGING_SOURCE_SHA=",
            "MUTATED=1",
            "BACKEND_ROLLBACK=PASS",
            "BACKEND_CANARY=PASS",
            "BACKEND_STAGING_HEALTH=FAIL",
            "BACKEND_STAGING=PASS",
            "docker build --build-arg SBI_SOURCE_SHA=",
            "docker network create --internal",
            "--read-only --tmpfs /tmp:",
            "--cap-drop ALL --security-opt no-new-privileges",
            '-p "127.0.0.1:$port:8080"',
            'source "$ENVFILE"'  # ensure not even present
        )[:-1]:
            with self.subTest(phrase=required):
                self.assertIn(required, script)
        self.assertNotIn('source "$ENVFILE"', script)
        self.assertNotIn("git clean -fdx", script)
        self.assertIn("SBI_AWS_REPORT_USERNAME", script)
        self.assertIn("SBI_AWS_REPORT_PASSWORD", script)
        self.assertIn("unexpected key in backend-only credential file", script)
        self.assertIn('run_candidate "$NAME" 18086 "$OLD_IMAGE"', script)
        for unsafe in ("sbi-agent-stage", "sbi-dashboard-ui-stage",
                       "aws_lightsail-caddy-1", "docker compose up",
                       "gcloud run deploy", "aws cloudformation"):
            self.assertNotIn(unsafe, script)

    def test_ssh_is_forced_allowlisted_not_general_remote_shell(self):
        script = (DIR / "stage_ssh_gate.sh").read_text()
        self.assertIn("SSH_ORIGINAL_COMMAND", script)
        self.assertIn("'status-backend-v1'", script)
        self.assertIn("deploy-backend", script)
        self.assertIn("sudo -n", script)
        self.assertIn("command not allowlisted", script)
        self.assertNotIn('eval ', script)

    def test_workflow_cannot_auto_deploy_or_modify_public(self):
        workflow = (BASE / ".github/workflows/sbi-aws-backend-staging-release.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertNotIn("\n  pull_request:", workflow)
        self.assertIn("refs/heads/main", workflow)
        self.assertIn("environment: sbi-backend-staging", workflow)
        self.assertIn("APPROVE_ISOLATED_BACKEND_STAGING", workflow)
        self.assertIn("inputs.mode == 'stage'", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("SBI_BACKEND_STAGE_DEPLOY_KEY", workflow)
        self.assertIn("SBI_BACKEND_STAGE_HOST_KEY", workflow)
        self.assertIn("StrictHostKeyChecking=yes", workflow)
        self.assertIn("SBI_BACKEND_EXECUTOR=READONLY_V1", workflow)
        self.assertIn("deploy-backend $SHA", workflow)
        self.assertNotIn("sbi-aws-staging-release-request.yml", workflow)
        for unsafe in ("aws-actions/configure-aws-credentials", "docker compose up",
                       "gcloud run deploy", "firebase auth", "iam:"):
            self.assertNotIn(unsafe, workflow)

    def test_source_only_docs_show_manual_bootstrap_and_financial_gate(self):
        readme = (DIR / "README.md").read_text()
        self.assertIn("sbi-backend-staging", readme)
        self.assertIn("manual", readme.lower())
        self.assertIn("rollback", readme.lower())
        self.assertIn("financial", readme.lower())


if __name__ == "__main__":
    unittest.main()
