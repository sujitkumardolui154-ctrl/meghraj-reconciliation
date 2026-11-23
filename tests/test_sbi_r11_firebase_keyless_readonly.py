"""R11 keyless Firebase *read-only* probe guard tests — strictly offline."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/ci/sbi_r11_firebase_keyless_readonly_probe.py"
spec = importlib.util.spec_from_file_location("sbi_r11_probe_qa", PROBE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class R11ReadOnlyFirebaseTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "SBI_R11_READONLY_FIREBASE":
                "SBI_R11_READ_ONLY_STAGING_FIREBASE_APPROVED"
        }

    def denies(self, overrides, message):
        values = dict(self.env, **overrides)
        with self.assertRaisesRegex(RuntimeError, message):
            mod.check_environment(values)

    def test_01_explicit_gate_accepts_only_isolated_project(self):
        self.assertEqual(mod.check_environment(self.env), (
            "sbi-r9-staging", "sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com"
        ))

    def test_02_refuses_missing_intent(self):
        self.denies({"SBI_R11_READONLY_FIREBASE": ""},
                    "explicit read-only intent missing")

    def test_03_refuses_emulator(self):
        self.denies({"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099"},
                    "Auth Emulator forbidden")

    def test_04_refuses_credentials_file(self):
        self.denies({"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/key.json"},
                    "private credential file")

    def test_05_refuses_production_project(self):
        self.denies({"GCLOUD_PROJECT": "meghraj-reconciliation"},
                    "not exact staging project")

    def test_06_refuses_cross_project_identity(self):
        self.denies({"GOOGLE_CLOUD_PROJECT": "another-project"},
                    "not exact staging project")

    def test_07_refuses_inherited_financial_evidence(self):
        self.denies({"SBI_PAYMENT_EVIDENCE_DIR": "/var/lib/bank-data"},
                    "financial evidence/database")

    def test_08_refuses_inherited_workspace_db(self):
        self.denies({"SBI_PRIVATE_WORKSPACE_DB": "/var/lib/invoices.sqlite"},
                    "financial evidence/database")

    def test_09_refuses_r9_user_creation_probe_gate(self):
        self.denies({
            "SBI_R9_REAL_STAGING_PROBE": "R9_REAL_FIREBASE_STAGING_QA_ONLY"
        }, "R9 user-creating probe")

    def test_10_refuses_wrong_gcloud_project_before_token_request(self):
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(mod, "command", return_value="meghraj-reconciliation") as cmd:
            with self.assertRaisesRegex(RuntimeError, "gcloud active project differs"):
                mod.verify_read_only_api()
            self.assertEqual(cmd.call_count, 1)

    def test_11_refuses_bogus_impersonation_token_without_api_request(self):
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(mod, "command", side_effect=["sbi-r9-staging", "bad"]), \
                patch.object(mod, "urlopen") as url:
            with self.assertRaisesRegex(RuntimeError, "invalid short-lived"):
                mod.verify_read_only_api()
            url.assert_not_called()

    def test_12_real_http_is_GET_and_output_never_contains_user_or_token(self):
        bearer = "test-secret-not-real-bearer-token-1234567890"
        fake = Mock(status=200)
        fake.read.return_value = json.dumps({
            "users": [{"email": "do-not-print@example.invalid"}]
        }).encode("utf-8")
        ctx = Mock()
        ctx.__enter__ = Mock(return_value=fake)
        ctx.__exit__ = Mock(return_value=None)
        # Mock supports magic protocol as MagicMock (not a real HTTP request).
        from unittest.mock import MagicMock
        context = MagicMock()
        context.__enter__.return_value = fake
        output = io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(mod, "command", side_effect=["sbi-r9-staging", bearer]), \
                patch.object(mod, "urlopen", return_value=context) as api, \
                patch("sys.stdout", output):
            mod.verify_read_only_api()
        req = api.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, mod.ENDPOINT)
        self.assertEqual(api.call_args.kwargs["timeout"], 20)
        self.assertEqual(req.headers["Authorization"], "Bearer " + bearer)
        text = output.getvalue()
        self.assertIn("R11_REAL_FIREBASE_AUTH_API=PASS_READONLY", text)
        self.assertNotIn(bearer, text)
        self.assertNotIn("do-not-print@example.invalid", text)
        self.assertIn("R11_FINANCIAL_APPLY=LOCKED", text)

    def test_13_api_permission_denial_fails_without_token_leak(self):
        err = HTTPError(mod.ENDPOINT, 403, "unauthorized", {}, None)
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(mod, "command", side_effect=[
                    "sbi-r9-staging", "fake-service-account-token-1234567890"
                ]), \
                patch.object(mod, "urlopen", side_effect=err):
            with self.assertRaises(HTTPError):
                mod.verify_read_only_api()

    def test_14_optimized_python_still_refuses_missing_gate(self):
        values = os.environ.copy()
        values.pop("SBI_R11_READONLY_FIREBASE", None)
        result = subprocess.run(
            [sys.executable, "-O", str(PROBE)],
            cwd=ROOT, env=values, capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("R11_PREFLIGHT_REFUSED:", result.stderr)


if __name__ == "__main__":
    unittest.main()
