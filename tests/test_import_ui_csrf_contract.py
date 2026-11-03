"""Offline regression for dashboard import POST CSRF wiring.

This protects the fail-closed gateway/client contract. It does not simulate
Firebase identity or claim that an authenticated host test passed.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImportUiCsrfContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "dashboard_source" / "index.html").read_text(encoding="utf-8")
        cls.gateway = (ROOT / "dashboard_source" / "production_gateway.py").read_text(encoding="utf-8")
        cls.sessions = (ROOT / "dashboard_source" / "dashboard_sessions.py").read_text(encoding="utf-8")

    def test_post_fetches_same_origin_csrf_before_import(self):
        section = self.html.split('async function api(path, method = "GET", body)', 1)[1].split('function clearLog()', 1)[0]
        self.assertIn('if (method === "POST")', section)
        self.assertIn('fetch("/auth/csrf"', section)
        self.assertIn('credentials: "same-origin"', section)
        self.assertIn('redirect: "error"', section)
        self.assertRegex(section, r'\^\[a-f0-9\]\{64\}\$')
        self.assertIn('headers["X-DIL-CSRF"] = csrfPayload.csrf_token', section)
        self.assertIn('headers["X-DIL-Import"] = "1"', section)
        self.assertLess(section.index('fetch("/auth/csrf"'), section.index('fetch("/api/imports/"'))

    def test_gateway_requires_session_csrf_and_import_entitlement(self):
        section = self.gateway.split('def database_import_gateway(part):', 1)[1].split('# DIL authentication integration', 1)[0]
        self.assertIn('can_import_invoice(', section)
        self.assertIn('if not csrf_valid():', section)
        self.assertIn('request.headers.get("X-DIL-Import") != "1"', section)
        self.assertLess(section.index('if not csrf_valid():'), section.index('requests.request('))

    def test_csrf_endpoint_matches_http_only_cookie(self):
        self.assertIn('CSRF_COOKIE = "__Host-dil_csrf"', self.sessions)
        self.assertIn('httponly=True', self.sessions)
        self.assertIn('def session_csrf():', self.sessions)
        self.assertIn('jsonify(csrf_token=token)', self.sessions)
        self.assertIn('set_cookie(response, CSRF_COOKIE, token, SESSION_SECONDS)', self.sessions)
        self.assertIn('secrets.compare_digest(cookie, header)', self.sessions)


if __name__ == "__main__":
    unittest.main()
