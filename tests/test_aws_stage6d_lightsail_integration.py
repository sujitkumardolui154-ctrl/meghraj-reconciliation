"""Stage 6D offline safety/integration architecture regression."""
import importlib.util
import pathlib
import tempfile
import unittest

FILE=pathlib.Path(__file__).resolve().parents[1]/"staging/aws_lightsail/stage6d_lightsail_integration_audit.py"
spec=importlib.util.spec_from_file_location("sbi_stage6d",FILE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Stage6DTests(unittest.TestCase):
    def test_live_source_dependencies_and_release_block(self):
        report=mod.audit(FILE.parents[2])
        f=report["source_markers"]
        for marker in ("firebase_web_config_endpoint","firebase_admin_revoked_session_verify",
                       "firebase_admin_user_lookup","firebase_admin_create_session",
                       "firebase_admin_revocation","admin_can_create_users",
                       "cloud_run_backend_token","credit_note_gcs",
                       "aws_backend_fail_closed","package_only_image"):
            self.assertTrue(f[marker],marker)
        self.assertIn("BLOCKED",report["release"])
        self.assertEqual(report["production_changes"],0)
        self.assertEqual(report["financial_access"],"DISABLED")
        self.assertEqual(report["recommendation"],"LIGHTSAIL_FIRST_FEASIBILITY_NO_EC2_PURCHASE")

    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"Required source file missing"):
                mod.audit(temp)

    def test_audit_no_network_or_secrets(self):
        s=FILE.read_text()
        for forbidden in ("import requests", "import boto3", "import subprocess",
                          "os.environ", "google.auth.default", "docker run",
                          "aws sts", "firebase_admin.initialize_app"):
            self.assertNotIn(forbidden,s)

if __name__=="__main__":
    unittest.main()
