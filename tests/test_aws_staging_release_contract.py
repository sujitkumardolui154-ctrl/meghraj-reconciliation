"""Synthetic, non-deploying AWS staging SSH/executor contract tests."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from agent.consolidated_controller import choose_tests

ROOT = Path(__file__).resolve().parents[1]
AWS = ROOT / "staging" / "aws_lightsail"
SCRIPTS = (
    "sbi_stage_request.sh",
    "sbi_stage_deploy_root.sh",
    "install_stage_executor.sh",
    "configure_gh_stage_secrets.sh",
    "staging_release_guarded.sh",
)


class AWSStagingReleaseContractTests(unittest.TestCase):
    def test_all_scripts_parse_without_running_deployment(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                self.assertTrue((AWS / name).is_file())
                result = subprocess.run(
                    ["bash", "-n", str(AWS / name)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_forced_command_status_and_denial(self):
        handler = AWS / "sbi_stage_request.sh"
        env = {**os.environ, "SSH_ORIGINAL_COMMAND": "status"}
        status = subprocess.run(
            ["bash", str(handler)], env=env,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("SBI_STAGE_SSH=RESTRICTED", status.stdout)
        for command in ("", "whoami", "deploy 123", "deploy " + "a" * 39,
                        "deploy " + "a" * 40 + "; id"):
            with self.subTest(command=command):
                env["SSH_ORIGINAL_COMMAND"] = command
                denied = subprocess.run(
                    ["bash", str(handler)], env=env,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(denied.returncode, 126)
                self.assertIn("REQUEST_DENIED", denied.stderr)

    def test_executor_rejects_invalid_input_before_docker_or_git(self):
        executor = AWS / "sbi_stage_deploy_root.sh"
        for stdin in ("", "invalid\n", "a" * 39 + "\n", "a" * 41 + "\n"):
            with self.subTest(input_length=len(stdin)):
                rejected = subprocess.run(
                    ["bash", str(executor)], input=stdin,
                    capture_output=True, text=True, check=False, timeout=5,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn("ERROR:", rejected.stdout + rejected.stderr)

    def test_executor_is_sha_bound_to_reviewed_main(self):
        script = (AWS / "sbi_stage_deploy_root.sh").read_text(encoding="utf-8")
        self.assertIn("refs/heads/main", script)
        self.assertIn('[[ "$ACTUAL" == "$SHA" ]]', script)
        self.assertIn('flock -n 9', script)
        self.assertIn('docker image inspect "$ROLLBACK"', script)
        self.assertIn('ROLLBACK_RESULT=FAIL', script)
        self.assertIn('127.0.0.1:18082:8080', script)

    def test_staging_changes_cannot_bypass_qa(self):
        for path in ("staging/aws_lightsail/sbi_stage_deploy_root.sh",
                     "staging/aws_lightsail/install_stage_executor.sh",
                     "migration/check_public_tree.py",
                     "unexpected_new_source.py"):
            with self.subTest(path=path):
                self.assertEqual(len(choose_tests([path], False)), 5)

    def test_docs_only_does_not_trigger_redundant_full_qa(self):
        self.assertEqual(choose_tests(["docs/release-notes.md"], False), [])


if __name__ == "__main__":
    unittest.main()
