"""Offline-only R9 guard QA. Never connects to Firebase or creates users."""
from __future__ import annotations

import os
import runpy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/ci/sbi_r9_real_staging_signed_token_probe.py"

class R9RealStagingProbePreflightTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "SBI_R9_REAL_STAGING_PROBE": "R9_REAL_FIREBASE_STAGING_QA_ONLY",
            "SBI_R8_STAGING_MODE": "SBI_R8_STAGING_ONLY_NONFINANCIAL",
            "SBI_R8_STAGING_FIREBASE_PROJECT_ID": "sbi-r9-staging",
            "SBI_R9_STAGING_EXPECTED_SERVICE_ACCOUNT_EMAIL":
                "sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com",
            "SBI_R8_STAGING_SITE_ORIGIN": "https://sbi-r9-staging-qa.example.invalid",
            "SBI_R8_STAGING_FIREBASE_WEB_API_KEY": "synthetic-r9-staging-only-00000000001",
            "SBI_READONLY_QUARANTINE_SOL_KEYS": "7001,7002,7003",
        }
        for key in (
            "FIREBASE_AUTH_EMULATOR_HOST",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "FIREBASE_WEB_API_KEY",
            "SBI_PAYMENT_EVIDENCE_DIR",
            "SBI_PRIVATE_WORKSPACE_DB",
            "GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT",
        ):
            self.base[key] = None

    def config(self, updates=None):
        env = os.environ.copy()
        for key, value in dict(self.base, **(updates or {})).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def checked(self, updates=None):
        # Suppress actual execute() and ADC discovery by runpy's __name__.
        with patch.dict(os.environ, self.config(updates), clear=True):
            loc = runpy.run_path(str(PROBE))
            return loc["check_environment"]()

    def refused(self, updates, expected):
        with patch.dict(os.environ, self.config(updates), clear=True):
            loc = runpy.run_path(str(PROBE))
            with self.assertRaisesRegex(RuntimeError, expected):
                loc["check_environment"]()

    def test_01_offline_validate_allowlisted_staging_values(self):
        project, origin, key, identity = self.checked()
        self.assertEqual(project, "sbi-r9-staging")
        self.assertEqual(origin, "https://sbi-r9-staging-qa.example.invalid")
        self.assertTrue(key.startswith("synthetic-r9-"))
        self.assertEqual(
            identity, "sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com"
        )

    def test_02_refuse_missing_R9_gate(self):
        self.refused({"SBI_R9_REAL_STAGING_PROBE": None}, "dedicated explicit R9 gate")

    def test_03_refuse_improper_R9_gate(self):
        self.refused({"SBI_R9_REAL_STAGING_PROBE": "true"}, "dedicated explicit R9 gate")

    def test_04_refuse_missing_R8_staging_mode(self):
        self.refused({"SBI_R8_STAGING_MODE": None}, "R8 staging-only mode")

    def test_05_refuse_production_Firebase_project(self):
        self.refused({
            "SBI_R8_STAGING_FIREBASE_PROJECT_ID": "meghraj-reconciliation"
        }, "separate staging project")

    def test_06_refuse_non_staging_Firebase_project(self):
        self.refused({
            "SBI_R8_STAGING_FIREBASE_PROJECT_ID": "demo-project"
        }, "separate staging project")

    def test_07_refuse_emulator_forged_tokens(self):
        self.refused({
            "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099"
        }, "Auth Emulator forbidden")

    def test_08_refuse_service_account_file_path(self):
        self.refused({
            "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/any-key.json"
        }, "service-account JSON file forbidden")

    def test_09_refuse_inherited_web_key(self):
        self.refused({
            "FIREBASE_WEB_API_KEY": "production-key"
        }, "inherited Firebase web API key forbidden")

    def test_10_refuse_live_payment_storage(self):
        self.refused({
            "SBI_PAYMENT_EVIDENCE_DIR": "/var/lib/live-payments"
        }, "inherited payment evidence storage forbidden")

    def test_11_refuse_live_workspace_database(self):
        self.refused({
            "SBI_PRIVATE_WORKSPACE_DB": "/var/lib/live-workspace.sqlite"
        }, "inherited workspace database forbidden")

    def test_12_refuse_inherited_production_google_project(self):
        self.refused({
            "GCLOUD_PROJECT": "meghraj-reconciliation"
        }, "inherited Google project")

    def test_13_refuse_production_preview_origin(self):
        self.refused({
            "SBI_R8_STAGING_SITE_ORIGIN":
                "https://sbi-preview.13-232-241-221.sslip.io"
        }, "separate HTTPS staging origin")

    def test_14_refuse_http_origin(self):
        self.refused({
            "SBI_R8_STAGING_SITE_ORIGIN":
                "http://sbi-r9-staging-qa.example.invalid"
        }, "separate HTTPS staging origin")

    def test_15_refuse_malformed_staging_api_key(self):
        self.refused({
            "SBI_R8_STAGING_FIREBASE_WEB_API_KEY": ""
        }, "separately supplied staging web API key")

    def test_16_refuse_missing_private_synthetic_SOL_registry(self):
        self.refused({
            "SBI_READONLY_QUARANTINE_SOL_KEYS": ""
        }, "explicit synthetic-only quarantine")

    def test_17_python_optimized_mode_still_refuses_default_entrypoint(self):
        env = self.config({"SBI_R9_REAL_STAGING_PROBE": None})
        p = subprocess.run(
            [sys.executable, "-O", str(PROBE)],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("dedicated explicit R9 gate required", p.stderr)

    def test_18_missing_separate_service_account_denied(self):
        self.refused({
            "SBI_R9_STAGING_EXPECTED_SERVICE_ACCOUNT_EMAIL": None
        }, "explicit separate staging-only service account")

    def test_19_production_service_account_denied(self):
        self.refused({
            "SBI_R9_STAGING_EXPECTED_SERVICE_ACCOUNT_EMAIL":
                "sbi-r9-qa@meghraj-reconciliation.iam.gserviceaccount.com"
        }, "explicit separate staging-only service account")

    def test_20_other_staging_service_account_denied(self):
        self.refused({
            "SBI_R9_STAGING_EXPECTED_SERVICE_ACCOUNT_EMAIL":
                "sbi-r9-qa@sbi-r9-staging-different.iam.gserviceaccount.com"
        }, "explicit separate staging-only service account")

    def test_21_no_live_cloud_code_invoked_during_offline_guard_import(self):
        # A fully valid fixture still runs only pure config checks, no SDK calls.
        # We never call execute() here.
        p = self.checked()
        self.assertEqual(p[0], "sbi-r9-staging")

    def test_22_refuse_old_R8_synthetic_project(self):
        self.refused({
            "SBI_R8_STAGING_FIREBASE_PROJECT_ID": "sbi-r8-staging-qa123"
        }, "separate staging project")

    def test_23_refuse_legacy_R8_origin_prefix(self):
        self.refused({
            "SBI_R8_STAGING_SITE_ORIGIN":
                "https://sbi-r8-staging-qa.example.invalid"
        }, "separate HTTPS staging origin")


if __name__ == "__main__":
    unittest.main()
