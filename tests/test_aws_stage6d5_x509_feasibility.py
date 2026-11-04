"""Stage 6D.5 X.509 WIF dependency-only preflight tests (no credentials)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT/"staging/aws_lightsail/stage6d5_x509_feasibility.py"
spec = importlib.util.spec_from_file_location("sbi_stage6d5", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Stage6D5FeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.fake_file = lambda name: "verify_session_cookie( check_revoked=True auth.get_user( auth.revoke_refresh_tokens( auth.create_session_cookie( Stage 6 AWS backend integration disabled SBI_STAGE6_PRIVATE_ONLY SBI_STAGE6_FINANCIAL_EXECUTION"

    def test_versions(self):
        self.assertEqual(module.parse_version("2.39.0"), (2, 39, 0))
        self.assertEqual(module.parse_version("2.46.1"), (2, 46, 1))
        self.assertEqual(module.parse_version("2.38.99"), (2, 38, 99))
        self.assertIsNone(module.parse_version("unknown"))

    def test_supported_library_is_not_a_live_auth_pass(self):
        versions = lambda p: {"google-auth":"2.39.0","firebase-admin":"7.1.0"}[p]
        data = module.inspect(version_lookup=versions, read_text=self.fake_file)
        self.assertEqual(data["x509_version_requirement"], "PASS")
        self.assertEqual(data["batch_qa"], "PASS")
        self.assertEqual(data["firebase_real_login"], "NOT_TESTED")
        self.assertEqual(data["x509_wif_provider"], "NOT_CONFIGURED")
        self.assertEqual(data["production_deployment"], "BLOCKED")
        self.assertEqual(data["financial_database"], "NOT_CONNECTED")

    def test_old_library_blocks(self):
        versions = lambda p: {"google-auth":"2.38.0","firebase-admin":"7.1.0"}[p]
        data = module.inspect(version_lookup=versions, read_text=self.fake_file)
        self.assertEqual(data["batch_qa"], "BLOCKED")
        self.assertEqual(data["x509_version_requirement"], "BLOCKED")

    def test_missing_revocation_contract_blocks(self):
        def fake_read(path):
            return self.fake_file(path).replace("check_revoked=True","check_revoked=False")
        versions = lambda p: {"google-auth":"2.41.0","firebase-admin":"7.1.0"}[p]
        self.assertEqual(module.inspect(version_lookup=versions,read_text=fake_read)["batch_qa"],"BLOCKED")

    def test_no_cloud_calls_or_secret_reads(self):
        text = PATH.read_text()
        for forbidden in ("google.auth.default", "import boto3", "import requests",
                          "subprocess", "credential_source", "read_bytes()", "os.environ"):
            self.assertNotIn(forbidden,text)
if __name__=="__main__": unittest.main()
