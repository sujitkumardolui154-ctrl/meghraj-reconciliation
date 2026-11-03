"""Static fail-closed contract for the AWS preview rollback gate (no AWS calls)."""
from pathlib import Path
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "staging/aws_lightsail/consolidated_release.sh"


class AwsPreviewRollbackTests(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_compose_failure_cannot_skip_rollback(self):
        source = SCRIPT.read_text()
        self.assertIn('if ! sudo docker compose up -d --no-deps --force-recreate sbi-preview; then', source)
        self.assertIn('echo "DEPLOY_ACTION=FAILED_COMPOSE"', source)
        self.assertIn('rollback_preview || true', source)
        self.assertIn('echo "RELEASE=BLOCKED_DEPLOY_FAILURE"', source)

    def test_rollback_requires_http_verification(self):
        source = SCRIPT.read_text()
        self.assertIn('ROLLBACK_RESULT=HOST_HTTP_VERIFIED', source)
        self.assertIn('ROLLBACK_RESULT=FAILED_COMPOSE', source)
        self.assertIn('ROLLBACK_RESULT=UNVERIFIED_HTTP', source)
        self.assertIn('[ "$restored_home" = 401 ] && [ "$restored_health" = 200 ]', source)
        self.assertIn('RELEASE=BLOCKED_SMOKE_FAILURE', source)


if __name__ == "__main__":
    unittest.main()
