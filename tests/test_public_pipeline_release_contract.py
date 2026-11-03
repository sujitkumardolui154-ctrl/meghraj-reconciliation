"""Non-deploying contract for the public SBI pipeline preview release."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "staging/aws_lightsail/publish_pipeline_dashboard.sh"


class DashboardReleaseSafety(unittest.TestCase):
    def test_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_only_public_preview_service_replaced(self):
        src = SCRIPT.read_text()
        self.assertIn('refs/heads/aws/lightsail-preview-20261102', src)
        self.assertIn('docker compose up -d --no-deps --no-build --force-recreate sbi-preview', src)
        self.assertIn('ORIGINAL_PUBLIC_IMAGE_PRESERVED=YES', src)
        self.assertIn('PUBLIC_PREVIEW_ROLLBACK=STARTED', src)
        self.assertIn('CANDIDATE_DASHBOARD=PASS', src)
        self.assertIn('FINANCIAL_WRITES=DISABLED', src)
        for forbidden in ("docker compose down", "docker system prune", "gcloud run deploy",
                          "firestore", "docker rm -f sbi-agent-stage", "service caddy restart"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, src)

    def test_login_monitoring_and_api_denial_checked_before_release(self):
        src = SCRIPT.read_text()
        self.assertLess(src.index('verify_container "$PROBE"'), src.index('CHANGED=1'))
        self.assertIn('get("/api/pipeline/status")', src)
        self.assertIn('get("/api/upload")', src)
        self.assertIn('get("/",False)', src)


if __name__ == "__main__":
    unittest.main()
