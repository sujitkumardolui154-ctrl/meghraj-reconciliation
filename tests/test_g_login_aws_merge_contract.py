"""Read-only architecture gate for Workstream G: v150 login -> AWS preview.

Run: python3 -m unittest discover -s tests -p 'test_g_login_aws_merge_contract.py' -v
These checks inspect source only; they never contact Firebase, AWS or finance.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOOGLE = ROOT / "dashboard_source"
AWS = ROOT / "staging" / "railway_public"

class LoginAwsMergeContract(unittest.TestCase):
    def read(self, root, path):
        return (root / path).read_text(encoding="utf-8")

    def test_v150_login_assets_present(self):
        for path in ("login.html", "login.css", "login.js", "dashboard_login_pages.py"):
            with self.subTest(path=path):
                self.assertTrue((GOOGLE / path).is_file())

    def test_google_login_uses_firebase_session_contract(self):
        js = self.read(GOOGLE, "login.js")
        for endpoint in ("/auth/config", "/auth/csrf", "/auth/session"):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, js)
        sessions = self.read(GOOGLE, "dashboard_sessions.py")
        self.assertIn("verify_session_cookie(", sessions)
        self.assertIn("check_revoked=True", sessions)

    def test_aws_isolated_auth_remains_present(self):
        app = self.read(AWS, "app.py")
        self.assertIn("def require_preview_login(", app)
        self.assertIn("def authorized(", app)
        self.assertIn("PREVIEW_USERNAME", app)
        self.assertIn("PREVIEW_PASSWORD", app)

    def test_aws_financial_access_is_not_connected(self):
        app = self.read(AWS, "app.py")
        self.assertIn('"financial_data_connected": False', app)
        self.assertIn('"financial_api_connected": False', app)

    def test_aws_docker_remains_separate_from_cloud_login(self):
        dockerfile = self.read(AWS, "Dockerfile")
        self.assertIn("COPY app.py pipeline_data.py pipeline.html priority_tasks.py", dockerfile)
        self.assertNotIn("dashboard_sessions.py", dockerfile)
        self.assertNotIn("firebase_admin", self.read(AWS, "app.py"))

if __name__ == "__main__":
    unittest.main()
