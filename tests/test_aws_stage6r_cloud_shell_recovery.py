"""Stage 6R cloud-shell-independent recovery: source inventory and fail-closed status."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"staging/aws_lightsail/stage6r_cloud_shell_independent_recovery.py"
spec=importlib.util.spec_from_file_location("stage6r",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Stage6RRecoveryTests(unittest.TestCase):
    def test_source_present_but_financial_access_not_claimed(self):
        data=mod.inspect(ROOT)
        self.assertEqual(data["source_recovery"],"PASS")
        self.assertEqual(data["batch_qa"],"PASS")
        self.assertEqual(data["target"],"EXISTING_AWS_LIGHTSAIL_ONLY")
        self.assertEqual(data["deployed_gcp_revision_parity"],"NOT_VERIFIED")
        self.assertEqual(data["live_firestore_access"],"NOT_VERIFIED")
        self.assertEqual(data["gcs_firestore_export_access"],"NOT_VERIFIED")
        self.assertEqual(data["financial_data_transfer"],"NOT_PERFORMED")
        self.assertEqual(data["financial_writes"],0)
        self.assertFalse(data["existing_services_changed"])
        self.assertEqual(data["production_cutover"],"BLOCKED")

    def test_empty_repo_does_not_pass(self):
        with tempfile.TemporaryDirectory() as empty:
            data=mod.inspect(empty)
            self.assertEqual(data["batch_qa"],"BLOCKED")
            self.assertIn("backend_source/main.py", data["sections"]["backend"]["missing"])

    def test_script_cannot_change_cloud_or_connect_live_resources(self):
        code=SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("import boto3", "import google", "import requests",
                          "import firebase_admin","subprocess","os.system(",
                          "os.environ", "docker run", "gsutil ", "gcloud "):
            self.assertNotIn(forbidden,code)
if __name__=="__main__": unittest.main()
