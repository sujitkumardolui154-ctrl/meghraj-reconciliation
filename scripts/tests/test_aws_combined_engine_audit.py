"""Synthetic tests: sanitized audit output and no Docker side effects on import."""
import importlib.util
import unittest
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "aws_combined_engine_audit.py"
spec = importlib.util.spec_from_file_location("aws_audit", p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class GatewayTests(unittest.TestCase):
    def test_redact_nonroute_secret_token(self):
        raw = """example.org {
 handle /api/* {
   reverse_proxy sbi-login-workspace-stage:8080
 }
 reverse_proxy https://user:password@some-private-domain.example:443
 basic_auth user SECRET987
 import secret.conf
}"""
        out = module.classify_caddy(raw, module.TARGETS)
        self.assertNotIn("password", str(out))
        self.assertNotIn("SECRET987", str(out))
        self.assertNotIn("some-private-domain", str(out))
        self.assertTrue(any(x.get("known_container_targets") == ["sbi-login-workspace-stage"] for x in out))
        self.assertTrue(any(x.get("kind") == "caddy_import" for x in out))

    def test_path_only_if_safe(self):
        out = module.classify_caddy("handle /api/token?key=mysecret {\nhandle /api/* {", module.TARGETS)
        self.assertEqual(out[0]["path"], "WITHHELD")
        self.assertEqual(out[1]["path"], "/api/*")

    def test_no_docker_commands_on_import(self):
        self.assertTrue(callable(module.main))
        self.assertTrue(callable(module.command))

if __name__ == "__main__":
    unittest.main()
