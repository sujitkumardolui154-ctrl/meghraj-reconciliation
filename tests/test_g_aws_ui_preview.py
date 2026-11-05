"""AWS private UI preview contract — source-only regression tests."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "staging" / "railway_public"

class AwsUiPreviewSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.html = (ROOT / "ui_preview.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui_preview.css").read_text(encoding="utf-8")
        cls.docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    def test_private_preview_routes_exist(self):
        self.assertIn('@app.get("/ui-preview")', self.app)
        self.assertIn('@app.get("/ui-preview.css")', self.app)
        self.assertIn('def require_preview_login():', self.app)

    def test_no_public_route_exemption_for_preview(self):
        auth_section = self.app.split('def require_preview_login():', 1)[1].split('@app.after_request', 1)[0]
        self.assertIn('request.path == "/healthz"', auth_section)
        self.assertNotIn('"/ui-preview"', auth_section)

    def test_preview_is_not_an_authentication_replacement(self):
        self.assertNotIn('<form', self.html.lower())
        self.assertNotIn('type="password"', self.html.lower())
        self.assertNotIn('identitytoolkit.googleapis.com', self.html)
        self.assertNotIn('firebase_admin', self.app)
        self.assertIn('href="/pipeline"', self.html)

    def test_no_financial_data_in_preview(self):
        self.assertIn('No financial database connection', self.html)
        self.assertNotIn('fetch(', self.html)
        self.assertNotIn('<script', self.html.lower())

    def test_assets_in_container_and_responsive(self):
        self.assertIn('ui_preview.html ui_preview.css', self.docker)
        self.assertIn('href="/ui-preview.css"', self.html)
        self.assertIn('@media(max-width:760px)', self.css)
        self.assertIn("Content-Security-Policy", self.app)

if __name__ == "__main__":
    unittest.main()
