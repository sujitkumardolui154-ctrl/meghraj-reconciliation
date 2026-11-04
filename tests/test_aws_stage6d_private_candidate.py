"""Stage 6D private authenticated shell gate: synthetic only, no cloud."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"dashboard_source"))
from stage6d_private_entry import startup_gate
from stage6_origin_policy import private_aws_origin

ORIGIN="https://sbi-stage6.13-232-241-221.sslip.io"
GOOD={
    "SBI_STAGE6_AUTH_PROFILE":"aws-private-staging",
    "SBI_STAGE6_AWS_ORIGIN":ORIGIN,
    "SBI_STAGE6_PRIVATE_ONLY":"1",
    "SBI_STAGE6_FINANCIAL_EXECUTION":"disabled",
    "SBI_STAGE6_BACKEND_CONNECTED":"false",
}
class PrivateOnlyTests(unittest.TestCase):
    def test_must_explicitly_opt_into_private_profile(self):
        self.assertEqual(startup_gate({}),"BLOCKED_PROFILE")
        self.assertEqual(startup_gate({**GOOD,"SBI_STAGE6_AUTH_PROFILE":""}),"BLOCKED_PROFILE")

    def test_missing_or_untrusted_origin_blocks(self):
        self.assertEqual(startup_gate({**GOOD,"SBI_STAGE6_AWS_ORIGIN":""}),"BLOCKED_ORIGIN")
        self.assertEqual(startup_gate({**GOOD,"SBI_STAGE6_AWS_ORIGIN":"https://evil.example"}),"BLOCKED_ORIGIN")

    def test_no_public_or_financial_backend_access(self):
        self.assertEqual(startup_gate({**GOOD,"SBI_STAGE6_PRIVATE_ONLY":"0"}),"BLOCKED_PRIVATE_ONLY")
        self.assertEqual(startup_gate({**GOOD,"SBI_STAGE6_FINANCIAL_EXECUTION":"enabled"}),"BLOCKED_FINANCIAL_EXECUTION")
        self.assertEqual(startup_gate({**GOOD,"SBI_STAGE6_BACKEND_CONNECTED":"true"}),"BLOCKED_BACKEND_CONNECTED")
        self.assertEqual(startup_gate(GOOD),"READY_PRIVATE_AUTH_SHELL_ONLY")

    def test_fully_original_app_packaged_without_public_compose_changes(self):
        docker=(ROOT/"staging/aws_lightsail/Dockerfile.stage6d").read_text()
        self.assertIn("COPY dashboard_source/ /app/",docker)
        self.assertIn("USER 65534:65534",docker)
        self.assertIn('CMD ["python3", "/app/stage6d_private_entry.py"]',docker)
        self.assertNotIn("443:443",docker)
        self.assertNotIn("aws ec2 run-instances",docker)
        self.assertIn("aws-private-staging",(ROOT/"dashboard_source/stage6_origin_policy.py").read_text())

    def test_live_gateway_api_still_explicitly_denied(self):
        from flask import Flask
        from stage6_aws_guard import install_aws_private_guard
        app=Flask("private_candidate_synthetic")
        install_aws_private_guard(app)
        @app.get("/api/reports")
        def reports(): return "should not return"
        @app.get("/reports/credit-note.csv")
        def credit(): return "should not return"
        with patch.dict("os.environ",GOOD,clear=True):
            c=app.test_client()
            self.assertEqual(c.get("/api/reports").status_code,503)
            self.assertEqual(c.get("/reports/credit-note.csv").status_code,503)

if __name__=="__main__": unittest.main()
