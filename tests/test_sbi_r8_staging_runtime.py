"""R8 separate staging process guards; all tests are offline and synthetic."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SMOKE = r"""
import json, sys
from pathlib import Path
from types import SimpleNamespace
root = Path.cwd()
sys.path.insert(0, str(root / 'staging/aws_login_v150'))
import r8_staging_entrypoint as stage
from dashboard_sessions import ORIGINS, PROJECT, MASTER_UID
from firebase_admin import _apps
health = stage.app.test_client().get('/healthz')
status = stage.app.test_client().get('/api/payment-reconciliation/status')
print('R8_STAGING_RESULT=' + json.dumps({
  'project': PROJECT,
  'aws_app_source': str(Path(stage.original_app.__file__).resolve()),
  'origin': stage.origin,
  'origins': sorted(ORIGINS),
  'site_origin': stage.original_app.SITE_ORIGIN,
  'master_uid': MASTER_UID,
  'possible_master_login_denied': not stage.session_config.is_master(
    SimpleNamespace(uid='R8_STAGING_ADMIN_DISABLED',
      email='disabled-r8@example.invalid',
      custom_claims={'dil_admin':True, 'dil_dashboard':True}, disabled=False)
  ),
  'staging_flag': stage.app.config['SBI_R8_STAGING_ONLY'],
  'finance_lock': stage.app.config['SBI_R8_FINANCIAL_APPLY_LOCKED'],
  'health_code': health.status_code,
  'status_code': status.status_code,
  'finance_enabled': health.json['financial_execution_enabled'],
  'auth_apps_initialized': len(_apps),
  'api_key_configured': bool(stage.original_app.os.environ.get('FIREBASE_WEB_API_KEY')),
}))
"""

class R8StagingRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sbi-r8-staging-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.path.chmod(0o700)
        self.env = os.environ.copy()
        for k in (
            "FIREBASE_AUTH_EMULATOR_HOST",
            "GCLOUD_PROJECT", "GCP_PROJECT", "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_WEB_API_KEY",
            "SBI_PAYMENT_EVIDENCE_DIR", "SBI_PRIVATE_WORKSPACE_DB",
        ):
            self.env.pop(k, None)
        self.env.update({
            "SBI_R8_STAGING_MODE": "SBI_R8_STAGING_ONLY_NONFINANCIAL",
            "SBI_R8_STAGING_FIREBASE_PROJECT_ID": "sbi-r8-staging-qa123",
            "SBI_R8_STAGING_SITE_ORIGIN": "https://sbi-r8-staging-qa.example.invalid",
            "SBI_R8_STAGING_EVIDENCE_DIR": str(self.path),
            "SBI_R8_STAGING_FIREBASE_WEB_API_KEY": "r8-fake-key-for-offline-tests-only-000001",
            "SBI_READONLY_QUARANTINE_SOL_KEYS": "7001,7002,7003",
        })

    def launch(self, overrides=None):
        env = dict(self.env)
        if overrides:
            for k, v in overrides.items():
                if v is None:
                    env.pop(k, None)
                else:
                    env[k] = v
        return subprocess.run(
            [sys.executable, "-c", SMOKE],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=20
        )

    def assert_refused(self, overrides, code):
        result = self.launch(overrides)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("R8_STAGING_STARTUP_REFUSED", result.stderr)
        self.assertIn(code, result.stderr)

    def test_01_valid_offline_process_is_separate_and_finance_locked(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next(
            a.removeprefix("R8_STAGING_RESULT=")
            for a in result.stdout.splitlines()
            if a.startswith("R8_STAGING_RESULT=")
        )
        info = json.loads(line)
        self.assertEqual(info["project"], "sbi-r8-staging-qa123")
        self.assertTrue(
            info["aws_app_source"].endswith("/staging/aws_login_v150/app.py")
        )
        self.assertEqual(info["origins"], [
            "https://sbi-r8-staging-qa.example.invalid"
        ])
        self.assertEqual(info["origin"], info["site_origin"])
        self.assertEqual(info["master_uid"], "R8_STAGING_ADMIN_DISABLED")
        self.assertTrue(info["possible_master_login_denied"])
        self.assertTrue(info["staging_flag"])
        self.assertTrue(info["finance_lock"])
        self.assertEqual(info["health_code"], 200)
        self.assertEqual(info["status_code"], 401)
        self.assertFalse(info["finance_enabled"])
        self.assertEqual(info["auth_apps_initialized"], 0)
        self.assertTrue(info["api_key_configured"])

    def test_02_explicit_staging_mode_required(self):
        self.assert_refused({"SBI_R8_STAGING_MODE": None}, "explicit nonproduction")

    def test_03_production_project_denied(self):
        self.assert_refused({
            "SBI_R8_STAGING_FIREBASE_PROJECT_ID": "meghraj-reconciliation"
        }, "separate sbi-r8-staging prefix")

    def test_04_non_staging_project_denied(self):
        self.assert_refused({
            "SBI_R8_STAGING_FIREBASE_PROJECT_ID": "demo-r8"
        }, "separate sbi-r8-staging prefix")

    def test_05_live_production_origin_denied(self):
        self.assert_refused({
            "SBI_R8_STAGING_SITE_ORIGIN":
                "https://sbi-preview.13-232-241-221.sslip.io"
        }, "separate HTTPS staging origin")

    def test_06_http_origin_denied(self):
        self.assert_refused({
            "SBI_R8_STAGING_SITE_ORIGIN": "http://sbi-r8-staging-qa.example.invalid"
        }, "separate HTTPS staging origin")

    def test_07_origin_with_port_denied(self):
        self.assert_refused({
            "SBI_R8_STAGING_SITE_ORIGIN":
                "https://sbi-r8-staging-qa.example.invalid:8080"
        }, "separate HTTPS staging origin")

    def test_08_inherited_auth_emulator_denied(self):
        self.assert_refused({
            "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099"
        }, "emulator must be disabled")

    def test_09_service_account_file_denied(self):
        self.assert_refused({
            "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/production.json"
        }, "service-account file path is forbidden")

    def test_10_inherited_prod_google_project_denied(self):
        self.assert_refused({
            "GCLOUD_PROJECT": "meghraj-reconciliation"
        }, "inherited Google project")

    def test_11_inherited_web_api_key_denied(self):
        self.assert_refused({
            "FIREBASE_WEB_API_KEY": "inherited-key"
        }, "inherited production web API key")

    def test_12_missing_separate_web_key_denied(self):
        self.assert_refused({
            "SBI_R8_STAGING_FIREBASE_WEB_API_KEY": ""
        }, "independently supplied staging web API key")

    def test_13_inherited_evidence_directory_denied(self):
        self.assert_refused({
            "SBI_PAYMENT_EVIDENCE_DIR": "/mnt/production-evidence"
        }, "inherited evidence directory")

    def test_14_inherited_workspace_database_denied(self):
        self.assert_refused({
            "SBI_PRIVATE_WORKSPACE_DB": "/mnt/production-workspace.sqlite"
        }, "inherited workspace database")

    def test_15_missing_private_staging_directory_denied(self):
        self.assert_refused({
            "SBI_R8_STAGING_EVIDENCE_DIR": "/var/lib/production-payments"
        }, "dedicated private staging evidence directory")

    def test_16_staging_directory_with_bad_permissions_denied(self):
        self.path.chmod(0o755)
        self.assert_refused({}, "mode 0700")

    def test_17_missing_private_quarantine_registry_denied(self):
        self.assert_refused({
            "SBI_READONLY_QUARANTINE_SOL_KEYS": ""
        }, "private quarantine SOL group registry")

    def test_18_mismatched_google_cloud_project_denied(self):
        self.assert_refused({
            "GOOGLE_CLOUD_PROJECT": "meghraj-reconciliation"
        }, "inherited Google project")

    def test_19_optimized_python_cannot_bypass_staging_guard(self):
        env = dict(self.env)
        env.pop("SBI_R8_STAGING_MODE")
        p = subprocess.run(
            [sys.executable, "-O", "-c", SMOKE],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=20,
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("explicit nonproduction mode required", p.stderr)


if __name__ == "__main__":
    unittest.main()
