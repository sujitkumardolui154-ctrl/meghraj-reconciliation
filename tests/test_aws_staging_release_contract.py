"""Synthetic, non-deploying AWS staging SSH/executor contract tests."""
from __future__ import annotations

import ast
import json
import os
import stat
import subprocess
import sys
import tempfile
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

    def test_executor_rejects_unterminated_trailing_input(self):
        executor = AWS / "sbi_stage_deploy_root.sh"
        for request in ("status\nunexpected", "a" * 40 + "\nunexpected"):
            with self.subTest(request=request[:8]):
                result = subprocess.run(
                    ["bash", str(executor)], input=request,
                    capture_output=True, text=True, check=False, timeout=5,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("ERROR: extra input rejected", result.stdout + result.stderr)

    def test_executor_version_handshake_is_read_only(self):
        executor = AWS / "sbi_stage_deploy_root.sh"
        proc = subprocess.run(
            ["bash", str(executor)], input="status\n",
            capture_output=True, text=True, check=False, timeout=5,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SBI_STAGE_EXECUTOR=PREVIEW_AUTH_V1", proc.stdout)
        self.assertIn("FINANCIAL_WRITES=DISABLED", proc.stdout)
        self.assertNotIn("REQUESTED_RELEASE_SHA", proc.stdout)
        handler = (AWS / "sbi_stage_request.sh").read_text(encoding="utf-8")
        self.assertIn('"status-auth-v1"', handler)
        self.assertIn("printf 'status\\n' | sudo -n /usr/local/sbin/sbi-stage-deploy", handler)

    def test_workflow_blocks_old_executor_before_release(self):
        workflow = (ROOT / ".github/workflows/sbi-aws-staging-release-request.yml").read_text()
        self.assertIn("status-auth-v1", workflow)
        self.assertIn("SBI_STAGE_EXECUTOR=PREVIEW_AUTH_V1", workflow)
        self.assertLess(workflow.index("status-auth-v1"), workflow.index('"deploy $SHA"'))

    def test_auth_env_helper_allows_only_existing_preview_login(self):
        helper = AWS / "preview_auth_env.py"
        ast.parse(helper.read_text(encoding="utf-8"))
        password = "synthetic-password-1234567890"
        entries = [
            "PREVIEW_USERNAME=stage-reviewer",
            "PAYMENT_DATABASE_URL=synthetic-never-copy",
            "PREVIEW_PASSWORD=" + password,
        ]
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "preview.env"
            dest.touch(mode=0o600)
            os.chmod(dest, 0o600)
            proc = subprocess.run(
                [sys.executable, str(helper), str(dest)],
                input=json.dumps(entries), text=True, capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
            self.assertEqual(
                dest.read_text(),
                "PREVIEW_USERNAME=stage-reviewer\nPREVIEW_PASSWORD=" + password + "\n",
            )
            self.assertNotIn("synthetic-never-copy", dest.read_text())
            self.assertNotIn(password, proc.stdout + proc.stderr)

    def test_auth_env_helper_fails_closed_without_safe_existing_login(self):
        helper = AWS / "preview_auth_env.py"
        valid_password = "synthetic-password-1234567890"
        invalid_cases = (
            [],
            ["PREVIEW_USERNAME=reviewer"],
            ["PREVIEW_USERNAME=reviewer", "PREVIEW_PASSWORD=short"],
            ["PREVIEW_USERNAME=reviewer", "PREVIEW_USERNAME=other",
             "PREVIEW_PASSWORD=" + valid_password],
            ["PREVIEW_USERNAME=reviewer", "PREVIEW_PASSWORD=" + valid_password + "\nother"],
            ["PREVIEW_USERNAME=bad:username", "PREVIEW_PASSWORD=" + valid_password],
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, entries in enumerate(invalid_cases):
                with self.subTest(case=index):
                    dest = Path(directory) / ("invalid-" + str(index))
                    dest.touch(mode=0o600)
                    os.chmod(dest, 0o600)
                    proc = subprocess.run(
                        [sys.executable, str(helper), str(dest)],
                        input=json.dumps(entries), text=True,
                        capture_output=True, check=False,
                    )
                    self.assertEqual(proc.returncode, 2)
                    self.assertEqual(dest.read_text(), "")
                    self.assertNotIn(valid_password, proc.stdout + proc.stderr)

    def test_executor_keeps_login_during_probe_release_and_rollback(self):
        script = (AWS / "sbi_stage_deploy_root.sh").read_text(encoding="utf-8")
        self.assertEqual(script.count('--env-file "$AUTH_ENV_FILE"'), 3)
        self.assertIn('python3 "$SRC/staging/aws_lightsail/preview_auth_env.py"', script)
        self.assertIn('verify_authenticated "$PROBE"', script)
        self.assertIn('verify_authenticated "$NAME"', script)
        self.assertIn('AUTH_LOGIN=PASS', script)
        self.assertIn('cleanup_auth_file', script)

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
