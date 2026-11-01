
import unittest
import hashlib
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path.home() / "meghraj-reconciliation"
DASH = ROOT / "dashboard_source"
BACKUP = ROOT / "backups/login_ui_step84"

class LoginParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.inputs = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "input" and "id" in attrs:
            self.inputs[attrs["id"]] = attrs.get("type")

class TestMeghrajLogin(unittest.TestCase):

    def test_branding(self):
        html = (DASH / "login.html").read_text()
        self.assertIn(
            "Meghraj _ SBI Reconciliation Control Center",
            html
        )

    def test_login_elements(self):
        parser = LoginParser()
        parser.feed((DASH / "login.html").read_text())
        self.assertTrue({
            "login-form", "email", "password",
            "sign-in", "toggle-password"
        }.issubset(parser.ids))
        self.assertEqual(parser.inputs["email"], "email")
        self.assertEqual(parser.inputs["password"], "password")

    def test_authentication_files_unchanged(self):
        for filename in (
            "login.js",
            "cloud_auth.py",
            "dashboard_login_pages.py"
        ):
            with self.subTest(filename=filename):
                original = BACKUP / filename
                current = DASH / filename
                self.assertTrue(original.is_file())
                self.assertEqual(
                    hashlib.sha256(original.read_bytes()).digest(),
                    hashlib.sha256(current.read_bytes()).digest()
                )

    def test_responsive_css(self):
        css = (DASH / "login.css").read_text()
        self.assertIn(
            "MEGHRAJ LOGIN UI V2 START", css
        )
        self.assertIn(
            "prefers-reduced-motion", css
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
