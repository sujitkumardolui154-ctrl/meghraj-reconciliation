"""Stage 5E preflight security contract; offline, no Docker access."""
import importlib.util
import json
import pathlib
import subprocess
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / "staging/aws_lightsail/stage5e_hardening_preflight.py"
spec = importlib.util.spec_from_file_location("stage5e_preflight", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def container(name, image):
    return {
        "Config": {"Image": image, "User": ""},
        "State": {"Running": True},
        "HostConfig": {"Privileged": False, "ReadonlyRootfs": False,
                       "CapAdd": None, "CapDrop": None, "SecurityOpt": None,
                       "NetworkMode": "bridge"},
        "Mounts": [],
    }


class Stage5ETests(unittest.TestCase):
    def test_both_real_observed_names_pinned(self):
        self.assertEqual(set(mod.EXPECTED), {"sbi-agent-stage", "sbi-dashboard-ui-stage"})
        self.assertEqual(mod.EXPECTED["sbi-dashboard-ui-stage"], "caddy:2")

    def test_default_inventory_is_read_only_and_omits_env(self):
        def run(argv, **kwargs):
            self.assertEqual(argv[:3], ["docker", "container", "inspect"])
            return subprocess.CompletedProcess(argv, 0, json.dumps(
                [container(argv[-1], mod.EXPECTED[argv[-1]])]), "")
        with patch.object(mod.subprocess, "run", side_effect=run):
            rows = mod.inventory()
        self.assertEqual(len(rows), 2)
        self.assertNotIn("env", str(rows).lower())

    def test_image_drift_fails_closed(self):
        with patch.object(mod, "docker_json", return_value=container(
                "sbi-agent-stage", "unreviewed:latest")):
            with self.assertRaisesRegex(RuntimeError, "unexpected image"):
                mod.inventory()

    def test_inactive_container_fails_closed(self):
        doc = container("sbi-agent-stage", mod.EXPECTED["sbi-agent-stage"])
        doc["State"]["Running"] = False
        with patch.object(mod, "docker_json", return_value=doc):
            with self.assertRaisesRegex(RuntimeError, "not running"):
                mod.inventory()

    def test_synthetic_smoke_has_no_network_host_bind_or_privileges(self):
        commands = []
        def run(argv, **kwargs):
            commands.append(argv)
            return subprocess.CompletedProcess(argv, 0, "ok", "")
        with patch.object(mod.subprocess, "run", side_effect=run):
            result = mod.smoke()
        self.assertEqual(len(result), 2)
        for argv in commands:
            self.assertEqual(argv[:2], ["docker", "run"])
            self.assertIn("--rm", argv)
            self.assertIn("--network=none", argv)
            self.assertIn("--read-only", argv)
            self.assertIn("--user", argv)
            self.assertIn("65534:65534", argv)
            self.assertIn("--cap-drop=ALL", argv)
            self.assertIn("no-new-privileges", argv)
            for forbidden in ("--privileged", "--publish", "-p", "--volume", "-v",
                              "compose", "--mount", "/var/run/docker.sock"):
                self.assertNotIn(forbidden, argv)
        self.assertTrue(all(x["result"] == "PASS" for x in result))
        agent, caddy = commands
        self.assertNotIn("--cap-add", agent)
        self.assertIn("--cap-add", caddy)
        self.assertEqual(caddy[caddy.index("--cap-add") + 1], "NET_BIND_SERVICE")
        for argv in commands:
            for dest in ("/tmp", "/data", "/config"):
                self.assertTrue(any(
                    x.startswith(dest + ":") and "uid=65534" in x
                    and "gid=65534" in x and "mode=0700" in x
                    for x in argv
                ))

    def test_no_autorun_and_runtime_production_changes(self):
        source = PATH.read_text()
        self.assertIn('parser.add_argument(\n        "--smoke"', source)
        self.assertNotIn("docker compose up", source)
        self.assertNotIn("docker stop", source)
        self.assertNotIn("docker rm", source)
        self.assertNotIn("docker network connect", source)


if __name__ == "__main__":
    unittest.main()
