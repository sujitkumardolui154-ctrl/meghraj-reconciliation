"""Targeted no-deploy checks for the user-selected existing preview deployment target."""
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
TARGET="https://sbi-preview.13-232-241-221.sslip.io/login"

class ExistingPreviewPolicyTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((HERE/"existing_preview_target_policy.json").read_text(encoding="utf-8"))

    def test_existing_login_is_only_canonical_target(self):
        p=self.data
        self.assertEqual(p["user_required_url"],TARGET)
        self.assertTrue(p["existing_url_must_remain_canonical"])
        self.assertFalse(p["new_application_platform_allowed"])
        self.assertFalse(p["domain_purchase_required"])
        self.assertFalse(p["mandatory_ts_net_hostname"])

    def test_security_and_release_locks_remain(self):
        p=self.data
        self.assertEqual(p["financial_apply"],"LOCKED")
        self.assertEqual(p["production_release"],"BLOCKED")
        self.assertFalse(p["actual_deployment_performed"])
        self.assertEqual(p["legacy_external_mtls_22_cases"],"0_EXECUTED_NO_AUTOMATIC_WAIVER")
        self.assertEqual(p["approved_security_gates"],0)

    def test_existing_caddy_source_routes_login(self):
        c=(ROOT/"staging/aws_login_v150/Caddyfile.workspace").read_text(encoding="utf-8")
        self.assertIn("/login",c)
        self.assertIn("reverse_proxy sbi-login-workspace:8080",c)

    def test_old_tailnet_runbook_marked_superseded(self):
        previous=(ROOT/"staging/private_multisite/PRIVATE_MULTISITE_DEPLOYMENT_RUNBOOK_20261128.md").read_text(encoding="utf-8")
        self.assertIn("SUPERSEDED DEPLOYMENT TARGET",previous)
        self.assertIn(TARGET,previous)

if __name__=="__main__":
    unittest.main()
