"""Stage 6C-4: strictly non-mutating AWS WIF Firebase preflight tests."""
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

TARGET=pathlib.Path(__file__).resolve().parents[1]/"staging/aws_lightsail/stage6c4_firebase_probe.py"
spec=importlib.util.spec_from_file_location("stage6c4",TARGET)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Stage6C4Tests(unittest.TestCase):
    def test_missing_config_fails_closed(self):
        self.assertEqual(mod.preflight({}),"BLOCKED_AUTH_PROFILE")
        self.assertEqual(mod.preflight({"SBI_STAGE6_AUTH_PROFILE":"aws-private-staging"}),"BLOCKED_WIF_CONFIG_MISSING")

    def test_reject_service_account_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"credentials.json"
            p.write_text(json.dumps({"type":"service_account","private_key":"fake"}))
            env={"SBI_STAGE6_AUTH_PROFILE":"aws-private-staging",
                 "GOOGLE_APPLICATION_CREDENTIALS":str(p),"SBI_STAGE6_TEST_FIREBASE_UID":"test"}
            self.assertEqual(mod.preflight(env),"BLOCKED_WIF_REQUIRED_NO_PRIVATE_KEYS")

    def test_external_account_needs_explicit_uid_and_profile(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"config.json"
            p.write_text(json.dumps({"type":"external_account",
                         "audience":"//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/p/providers/a",
                         "credential_source":{"environment_id":"aws1"}}))
            env={"SBI_STAGE6_AUTH_PROFILE":"aws-private-staging",
                 "GOOGLE_APPLICATION_CREDENTIALS":str(p)}
            self.assertEqual(mod.preflight(env),"BLOCKED_TEST_UID_MISSING")
            env["SBI_STAGE6_TEST_FIREBASE_UID"]="synthetic"
            self.assertEqual(mod.preflight(env),"READY_FOR_LIVE_FIREBASE_AUTH_READ_ONLY")

    def test_no_mutating_firebase_operations_or_cloud_api_output(self):
        source=TARGET.read_text()
        for call in ("auth.create_user(", "auth.update_user(", "auth.revoke_refresh_tokens(",
                     "auth.set_custom_user_claims(", "firestore.Client(", "storage.Client(",
                     "docker run", "requests.post("):
            self.assertNotIn(call,source)
        self.assertIn("FIREBASE_AUTH_READ=PASS_ACCOUNT_ELIGIBLE",source)
        self.assertIn("STAGE6C4_BROWSER_LOGIN=NOT_TESTED",source)

if __name__=="__main__":
    unittest.main()
