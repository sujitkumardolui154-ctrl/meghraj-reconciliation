"""Offline safety contracts for the one-run AWS Phase 1 combined release gate."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tools/sbi_aws_phase1_combined_gate.py"
spec = importlib.util.spec_from_file_location("combined_gate", path)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class CombinedGateTests(unittest.TestCase):
    def test_exact_six_existing_container_names(self):
        self.assertEqual(len(gate.RUNNING), 6)
        self.assertIn("aws_lightsail-sbi-preview-1", gate.RUNNING)
        self.assertIn("aws_lightsail-caddy-1", gate.RUNNING)

    def test_no_data_source_defaults_to_off(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(gate, "PRIVATE_ENV", Path(temp) / "missing.env"):
                with patch.object(gate, "PRIVATE_SNAPSHOT", Path(temp) / "missing"):
                    self.assertFalse(gate.private_configuration())

    def test_partial_private_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            file = folder / "candidate.env"
            file.touch()
            with patch.object(gate, "PRIVATE_ENV", file):
                with patch.object(gate, "PRIVATE_SNAPSHOT", folder / "missing"):
                    with self.assertRaisesRegex(RuntimeError, "PARTIAL_CONFIGURATION"):
                        gate.private_configuration()

    def test_symlink_private_config_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            real = folder / "secret.env"
            real.write_text("SBI_AWS_REPORT_USERNAME=x", encoding="utf-8")
            link = folder / "candidate.env"
            link.symlink_to(real)
            snap = folder / "snapshot"
            snap.mkdir()
            with patch.object(gate, "PRIVATE_ENV", link):
                with patch.object(gate, "PRIVATE_SNAPSHOT", snap):
                    with self.assertRaisesRegex(RuntimeError, "OWNER_OR_MODE_INVALID"):
                        gate.private_configuration()

    def test_baseline_tracks_id_image_and_running_flag(self):
        with patch.object(gate, "image_ref", return_value=("id", "img", "true")) as func:
            result = gate.baseline(["docker"])
        self.assertEqual(set(result), set(gate.RUNNING))
        self.assertEqual(func.call_count, 6)

    def test_unavailable_preview_is_not_a_success(self):
        with patch("urllib.request.urlopen", side_effect=OSError("not connected")):
            self.assertEqual(gate.host_public_preview(), "UNREACHABLE")

    def test_candidate_runs_isolated_without_ports(self):
        commands = []
        def fake(cmd, **kwargs):
            commands.append(cmd)
            class Done:
                stdout = "a" * 64
            return Done()
        with patch.object(gate, "call", side_effect=fake):
            gate.launch(["docker"], "sbi-test", "test-image", False)
        cmd = commands[0]
        self.assertIn("--network", cmd)
        self.assertIn("none", cmd)
        self.assertIn("--read-only", cmd)
        self.assertIn("--cap-drop", cmd)
        self.assertNotIn("--publish", cmd)
        self.assertNotIn("-p", cmd)
        self.assertNotIn("--mount", cmd)
        self.assertNotIn("--env-file", cmd)

    def test_private_data_only_passed_through_readonly_mount(self):
        commands = []
        def fake(cmd, **kwargs):
            commands.append(cmd)
            class Done:
                stdout = "b" * 64
            return Done()
        with patch.object(gate, "call", side_effect=fake):
            gate.launch(["docker"], "sbi-test", "test-image", True)
        cmd = commands[0]
        self.assertIn("--env-file", cmd)
        self.assertIn("--mount", cmd)
        mount = cmd[cmd.index("--mount") + 1]
        self.assertTrue(mount.endswith(",readonly"))
        self.assertIn("dst=/approved-snapshot", mount)
        self.assertNotIn("--publish", cmd)

    def test_probe_checks_http_deny_and_no_data_readiness(self):
        for item in ("/healthz", "/readyz", "/reports", "/api/upload",
                     "/imports/preview", "UNCONFIGURED_READY_SHOULD_503",
                     "PRIVATE_SNAPSHOT_NOT_READY", "PRIVATE_SNAPSHOT_REPORT_INDEX_NOT_200"):
            self.assertIn(item, gate.PROBE)

    def test_no_prod_alteration_or_financial_write_calls(self):
        text = path.read_text()
        for forbidden in (
            "docker compose up", "docker compose down",
            "systemctl restart", "git push", "gcloud run deploy",
            "aws lightsail update-container-service",
            "payment_allocation", "firebase_admin",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn('announce("PRODUCTION_CUTOVER", "BLOCKED")', text)
        self.assertIn('announce("AWS_DEPLOYMENT", "NOT_PERFORMED")', text)


if __name__ == "__main__":
    unittest.main()
