"""Static safety contract for the AWS staging-only login bootstrap (no Docker access)."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "staging/aws_lightsail/bootstrap_stage_preview_login.sh"


class AWSStagePreviewLoginBootstrapContract(unittest.TestCase):
    def test_shell_syntax_without_execution(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reviewed_main_pinning_and_target_isolation(self):
        src = SCRIPT.read_text()
        for required in (
            'ls-remote origin refs/heads/main',
            'git -C "$ROOT" show "$SHA:staging/aws_lightsail/bootstrap_stage_preview_login.sh"',
            'sbi-agent-stage', '127.0.0.1', '18082',
            'len .Mounts', 'sbi-stage-release.lock',
            'PREVIEW_USERNAME', 'PREVIEW_PASSWORD',
        ):
            with self.subTest(required=required):
                self.assertIn(required, src)
        for forbidden in ("gcloud run deploy", "firestore", "firebase",
                          "docker compose down", "docker system prune", "gh secret set"):
            self.assertNotIn(forbidden, src)

    def test_auth_gate_precedes_original_container_stop(self):
        src = SCRIPT.read_text()
        self.assertLess(src.index('AUTH_PROBE=PASS'), src.index('docker stop "$NAME"'))
        self.assertLess(src.index('docker tag "$IMAGE" "$ROLLBACK_IMAGE"'),
                        src.index('docker stop "$NAME"'))
        self.assertIn('verify_login "$PROBE_NAME"', src)
        self.assertIn('verify_login "$NAME"', src)

    def test_rollback_preserves_original_container_object(self):
        src = SCRIPT.read_text()
        self.assertIn('docker rename "$NAME" "$BACKUP_NAME"', src)
        self.assertIn('docker rename "$BACKUP_NAME" "$NAME"', src)
        self.assertIn('docker start "$NAME"', src)
        self.assertIn('trap rollback EXIT', src)
        self.assertLess(src.index('MUTATED=1\n'), src.index('docker stop "$NAME"'))
        self.assertIn('STAGING_LOGIN_ROLLBACK=PASS', src)
        self.assertIn('FINANCIAL_WRITES=DISABLED', src)

if __name__ == "__main__":
    unittest.main()
