"""Source-only F43 floating assistant accessibility and bounded DOM guards."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "dashboard_source" / "dil_floating_assistant.js"

class FloatingAssistantGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = SOURCE.read_text(encoding="utf-8")

    def test_one_overlay_not_new_navigation(self):
        self.assertIn('id="dil-assistant-panel"', self.js)
        self.assertIn('id="dil-assistant-root"', self.js)
        self.assertNotIn('window.location.href', self.js)

    def test_keyboard_focus_containment(self):
        for token in ('event.key === "Escape"', 'event.key !== "Tab"', 'event.shiftKey', 'event.preventDefault()', 'last.focus()', 'first.focus()'):
            self.assertIn(token, self.js)

    def test_bounded_dom(self):
        self.assertIn('MAX_VISIBLE_MESSAGES = 80', self.js)
        self.assertIn('while (log.children.length > MAX_VISIBLE_MESSAGES)', self.js)

    def test_no_html_injection(self):
        self.assertIn('bubble.textContent = message', self.js)
        self.assertNotIn('bubble.innerHTML', self.js)

    def test_reduced_motion_and_mobile(self):
        self.assertIn('prefers-reduced-motion:reduce', self.js)
        self.assertIn('@media(max-width:420px)', self.js)
        self.assertIn('100dvh', self.js)

    def test_no_financial_api_or_write(self):
        for forbidden in ('fetch(', 'XMLHttpRequest', 'localStorage', 'indexedDB', '/imports/apply'):
            self.assertNotIn(forbidden, self.js)

if __name__ == "__main__":
    unittest.main()
