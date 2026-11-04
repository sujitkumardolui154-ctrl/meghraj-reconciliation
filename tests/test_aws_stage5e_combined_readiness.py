"""Stage 5E consolidated inventory contract — entirely offline."""
import importlib.util
import pathlib
import subprocess
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / "staging/aws_lightsail/stage5e_combined_readiness.py"
spec = importlib.util.spec_from_file_location("stage5e_combined", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture(name):
    return {
        "Config": {"Image": m.EXPECTED_LOCAL.get(name, "preview:image")},
        "Image": "sha256:" + "a"*64,
        "State": {"Running": True},
        "HostConfig": {"PortBindings": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]},
                       "Privileged": False, "ReadonlyRootfs": False},
        "Mounts": [{"Destination": "/srv", "RW": True, "Type": "volume"}] if name == "sbi-dashboard-ui-stage" else [],
        "NetworkSettings": {"Networks": {"bridge": {}}}
    }

class CombinedTests(unittest.TestCase):
    def test_no_secret_values_or_mount_sources_in_report(self):
        d = m.summarize(fixture("sbi-dashboard-ui-stage"), "sbi-dashboard-ui-stage")
        self.assertEqual(d["mounts"], [{"destination": "/srv", "type": "volume", "read_only": False}])
        self.assertNotIn("Env", str(d))
        self.assertNotIn("Source", str(d))

    def test_no_mutating_calls(self):
        source = PATH.read_text()
        for forbidden in ('"docker", "run"', '"docker", "stop"', '"docker", "start"',
                          '"docker", "rm"', '"docker", "compose"', 'docker exec'):
            self.assertNotIn(forbidden, source)

    def test_evidence_does_not_claim_release(self):
        with patch.object(m, "image_exists", return_value=True):
            rows = [m.summarize(fixture(n), n) for n in m.NAMES]
        report = m.evaluate(rows)
        self.assertEqual(report["status"], "INVENTORY_PASS_RELEASE_NOT_APPROVED")
        self.assertEqual(report["cloud_run_login_v150_parity"], "UNVERIFIED")
        self.assertFalse(report["current_deployment_changed"])
        self.assertFalse(report["financial_write_performed"])

    def test_missing_rollback_image_blocks(self):
        with patch.object(m, "image_exists", return_value=False):
            rows = [m.summarize(fixture(n), n) for n in m.NAMES]
        self.assertEqual(m.evaluate(rows)["status"], "REVIEW_REQUIRED")

    def test_failed_docker_query_fails_closed(self):
        with patch.object(m.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 1, "", "failure")):
            with self.assertRaises(RuntimeError):
                m.inspect("sbi-agent-stage")

if __name__ == "__main__":
    unittest.main()
