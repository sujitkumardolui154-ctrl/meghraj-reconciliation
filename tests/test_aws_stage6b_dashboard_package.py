"""Stage 6B full dashboard container is intentionally non-deployable."""
import importlib.util
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
GUARD=ROOT/"staging/aws_lightsail/stage6b_build_guard.py"
DOCKER=ROOT/"staging/aws_lightsail/Dockerfile.stage6b"
IGNORE=ROOT/"staging/aws_lightsail/Dockerfile.stage6b.dockerignore"
spec=importlib.util.spec_from_file_location("stage6b_guard",GUARD)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Stage6BTests(unittest.TestCase):
    def test_original_dashboard_contract(self):
        self.assertTrue(module.verify(ROOT/"dashboard_source"))

    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,"Required dashboard files absent"):
                module.verify(pathlib.Path(t))

    def test_container_is_package_only_not_runnable(self):
        d=DOCKER.read_text()
        self.assertIn("COPY dashboard_source/ /app/",d)
        self.assertIn("USER 65534:65534",d)
        self.assertIn('CMD ["python3", "/app/stage6b_build_guard.py", "--block-startup"]',d)
        self.assertNotIn("gunicorn --bind",d)
        self.assertNotIn("ENTRYPOINT",d)
        self.assertNotIn("docker.sock",d)

    def test_context_allowlist_and_secret_filters(self):
        d=IGNORE.read_text()
        self.assertTrue(d.startswith("# Restrict"))
        for text in ("**", "!dashboard_source/**", "**/.env", "**/*.pem", "**/*.key"):
            self.assertIn(text,d)

    def test_runtime_cannot_be_enabled_by_flag(self):
        self.assertEqual(module.main.__name__,"main")
        s=GUARD.read_text()
        self.assertIn("STAGE6B_STARTUP=BLOCKED_PENDING_AUTH_IDENTITY_AND_BACKEND_PARITY",s)
        self.assertNotIn("subprocess",s)

if __name__=="__main__":
    unittest.main()
