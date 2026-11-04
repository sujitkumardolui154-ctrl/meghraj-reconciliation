"""F01 source-only safety regression for floating DIL UI."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "dashboard_source"
SRC = ROOT / "dil_floating_assistant.js"

class FloatingAssistantSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SRC.read_text(encoding="utf-8")

    def test_no_extra_tab_or_section_navigation(self):
        self.assertIn("position:fixed", self.source)
        self.assertIn("dil-assistant-panel", self.source)
        self.assertNotIn("window.location", self.source)
        self.assertNotIn("data-tab=", self.source)

    def test_no_unsafe_rendering_of_user_content(self):
        self.assertIn("bubble.textContent = message", self.source)
        self.assertNotIn("bubble.innerHTML =", self.source)
        self.assertIn('maxlength="2000"', self.source)

    def test_not_misrepresented_as_live_financial_api(self):
        self.assertIn("not yet available", self.source)
        self.assertIn("No financial data was accessed or modified.", self.source)
        self.assertNotIn('fetch(', self.source)

    def test_dashboard_mount_and_serving_contract(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        gateway = (ROOT / "production_gateway.py").read_text(encoding="utf-8")
        self.assertEqual(html.count('src="/dil_floating_assistant.js"'), 1)
        self.assertIn('@app.get("/dil_floating_assistant.js")', gateway)
        self.assertIn('"dil_floating_assistant.js", mimetype="application/javascript"', gateway)
        self.assertIn('response.headers["X-Content-Type-Options"] = "nosniff"', gateway)
        self.assertNotIn('@app.post("/api/dil', gateway)

    def test_accessibility_and_motion(self):
        self.assertIn("prefers-reduced-motion", self.source)
        self.assertIn("aria-expanded", self.source)
        self.assertIn("Escape", self.source)
        self.assertIn("aria-live", self.source)

if __name__ == "__main__":
    unittest.main()
