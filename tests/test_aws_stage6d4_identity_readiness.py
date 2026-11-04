"""Stage 6D.4 independent source-only Firebase authentication contract tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/"staging/aws_lightsail/stage6d4_identity_readiness.py"
spec=importlib.util.spec_from_file_location("stage6d4",AUDIT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class IdentityReadinessTests(unittest.TestCase):
    def test_security_inventory_and_no_false_live_pass(self):
        result=mod.inspect(ROOT)
        self.assertEqual(result["source_contract"],"PASS")
        self.assertEqual(result["batch_qa"],"PASS")
        self.assertEqual(result["identity_design_decision"],"BLOCKED_AWAITING_SECURE_LIGHTSAIL_COMPATIBLE_IDENTITY")
        self.assertEqual(result["firebase_real_login"],"NOT_TESTED")
        self.assertEqual(result["firebase_revocation_live"],"NOT_TESTED")
        self.assertEqual(result["finance_database"],"NOT_CONNECTED")
        self.assertEqual(result["production_deployment"],"BLOCKED")
        self.assertEqual(result["financial_writes"],0)
        self.assertEqual(result["new_ec2_server"],"NOT_AUTHORIZED")
        self.assertTrue(all(result["findings"].values()))

    def test_source_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"Missing required source"):
                mod.inspect(temp)

    def test_required_revocation_marker_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp)
            for name in mod.REQUIRED:
                destination=temp/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_text((ROOT/name).read_text())
            session=temp/"dashboard_source/dashboard_sessions.py"
            session.write_text(session.read_text().replace("check_revoked=True","check_revoked=False"))
            result=mod.inspect(temp)
            self.assertEqual(result["source_contract"],"FAIL")
            self.assertEqual(result["batch_qa"],"FAIL")
            self.assertFalse(result["findings"]["explicit_revocation_flag"])

    def test_script_never_uses_live_identity(self):
        source=AUDIT.read_text()
        for forbidden in ("firebase_admin.initialize_app","import boto3","google.auth.default(",
                          "requests.get(", "requests.post(", "subprocess.run(",
                          "os.environ", "private_key"):
            self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
