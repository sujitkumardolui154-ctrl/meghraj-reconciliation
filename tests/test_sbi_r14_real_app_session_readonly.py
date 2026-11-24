"""R14 offline-only refusal tests: MUST NOT access Firebase or any network."""
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/ci/sbi_r14_real_app_session_readonly.py"
spec = importlib.util.spec_from_file_location("sbi_r14_probe", PROBE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def safe_env():
    return {
        "SBI_R14_REAL_APP_SESSION": probe.OPT_IN,
        "GCLOUD_PROJECT": probe.PROJECT,
        "SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS": "999999999999",
    }


class R14OfflineEnvironmentTests(unittest.TestCase):
    def assert_refuses(self, code, updates=None, removed=()):
        env = safe_env()
        env.update(updates or {})
        for name in removed:
            env.pop(name, None)
        with self.assertRaisesRegex(probe.R14Refused, code):
            probe.check_environment(env)

    def test_01_requires_explicit_gate(self):
        self.assert_refuses("EXPLICIT_APPROVAL", removed=("SBI_R14_REAL_APP_SESSION",))

    def test_02_requires_exact_project(self):
        self.assert_refuses("NOT_STAGING", updates={"GCLOUD_PROJECT": "meghraj-reconciliation"})

    def test_03_forbids_github_ci(self):
        self.assert_refuses("GITHUB_CI", updates={"GITHUB_ACTIONS": "true"})

    def test_04_forbids_auth_emulator(self):
        self.assert_refuses("INHERITED", updates={"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099"})

    def test_05_forbids_json_service_account_file(self):
        self.assert_refuses("INHERITED", updates={"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/service.json"})

    def test_06_forbids_financial_database_path(self):
        self.assert_refuses("INHERITED", updates={"SBI_PRIVATE_WORKSPACE_DB": "/var/lib/production.db"})

    def test_07_forbids_inherited_production_web_key(self):
        self.assert_refuses("INHERITED", updates={"FIREBASE_WEB_API_KEY": "not-a-test-key"})

    def test_08_requires_approved_synthetic_SOL_keys(self):
        self.assert_refuses("APPROVED_SYNTHETIC", removed=("SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS",))

    def test_09_rejects_unsafe_SOL_key_values(self):
        self.assert_refuses("APPROVED_SYNTHETIC", updates={"SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS": "1; rm -rf /"})

    def test_10_accepts_only_exact_separate_staging_gate(self):
        self.assertEqual(probe.check_environment(safe_env()), "999999999999")

    def test_11_never_has_user_mutation_or_financial_update_calls(self):
        source = PROBE.read_text()
        for prohibited in (
            "auth.create_user(", "auth.delete_user(",
            "auth.update_user(", "auth.set_custom_user_claims(",
            "auth.revoke_refresh_tokens(",
            "payment_evidence.upload(", "finance_apply(", "psycopg.connect(",
        ):
            self.assertNotIn(prohibited, source)

    def test_12_requires_exact_identity_and_project_as_source_guards(self):
        source = PROBE.read_text()
        self.assertIn('getattr(credentials, "service_account_email", None) == QA_ACCOUNT', source)
        self.assertIn('adc_project == PROJECT', source)
        self.assertIn('"R14_FINANCIAL_APPLY=LOCKED"', source)


if __name__ == "__main__":
    unittest.main()
