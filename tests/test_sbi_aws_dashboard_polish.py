"""AWS dashboard visual refresh and removed-legacy-panel regression.

No live Firebase, external GitHub, or financial database accessed by these
tests; session access is synthetic and scoped to Flask's test client.
"""
import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LOGIN = ROOT / "staging/aws_login_v150"
for folder in (ROOT / "dashboard_source", LOGIN, ROOT / "staging/railway_public"):
    sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location("sbi_dashboard_polish_test", LOGIN / "app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SBIVisualRefreshTests(unittest.TestCase):
    def setUp(self):
        module.app.testing = True
        self.client = module.app.test_client()

    def session(self):
        self.client.set_cookie("__Host-dil_session", "synthetic", secure=True)
        user = SimpleNamespace(
            uid="synthetic", disabled=False,
            custom_claims={"dil_dashboard": True}, email="qa@example.invalid",
            display_name="synthetic")
        return (
            patch("dashboard_sessions.firebase_app", return_value=None),
            patch("dashboard_sessions.auth.verify_session_cookie",
                  return_value={"uid": "synthetic"}),
            patch("dashboard_sessions.auth.get_user", return_value=user),
        )

    def test_dashboard_style_and_sections(self):
        a, b, c = self.session()
        with a, b, c:
            response = self.client.get("/dashboard")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("MEGHRAJ EXPRESS", html)
            self.assertIn("AWS Private Preview", html)
            self.assertIn("--accent:#55ddc8", html)
            self.assertIn("font-family", html) if "font-family" in html else self.assertIn("font:", html)
            self.assertIn('class="dil-nav"', html)
            self.assertIn('id="dil-tower-button" aria-controls="dil-tower"', html)
            self.assertIn('id="dil-tower" hidden', html)
            self.assertIn('data-src="/control-tower?embedded=1"', html)
            self.assertNotIn('<h2>Backend API Reports</h2>', html)
            self.assertNotIn('id="links"', html)
            self.assertNotIn("Supervisor API Monitoring", html)
            self.assertNotIn('<script src="/dashboard.js"', html)
            self.assertNotIn("refreshMonitoring()", html)
            for section in ('id="dil-home"', 'id="dil-reports" hidden',
                            'id="dil-imports" hidden', 'id="excel-upload"'):
                self.assertIn(section, html)
            self.assertIn('class="site-header"', html)
            self.assertIn("frame-src 'self'", response.headers["Content-Security-Policy"])

    def test_retired_monitor_js_contains_no_network_calls(self):
        script = (ROOT / "dashboard_source/dashboard.js").read_text()
        self.assertNotIn("createMonitorPanels(", script)
        self.assertNotIn("refreshMonitoring(", script)
        self.assertNotIn("fetch(", script)
        self.assertNotIn("setInterval(", script)

    def test_tower_embedded_theme_retains_session_security(self):
        self.assertEqual(self.client.get("/control-tower?embedded=1").status_code, 401)
        a, b, c = self.session()
        with a, b, c:
            response = self.client.get("/control-tower?embedded=1")
            self.assertEqual(response.status_code, 200)
            self.assertIn("--surface:#16263d", response.get_data(as_text=True))
            self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
            self.assertIn("frame-ancestors 'self'",
                          response.headers["Content-Security-Policy"])
            self.assertEqual(self.client.get("/api/reports").status_code, 403)
            self.assertEqual(self.client.get("/control-tower/api/priority-tasks").status_code, 503)

    def test_release_guard_and_prior_control_tower_unmodified(self):
        login = LOGIN / "deploy_dashboard_polish.sh"
        script = login.read_text()
        self.assertIn("BLOCKED_UNREVIEWED_PUBLIC_CADDY_CONFIGURATION", script)
        self.assertIn('BASELINE_TAB="$ROOT/staging/aws_login_v150/Caddyfile.control_tower_tab"', script)
        self.assertIn("DASHBOARD_POLISH_SOURCE_UI=PASS", script)
        self.assertIn('BACKUP="$CONF/Caddyfile.before-dashboard-polish"', script)
        self.assertIn("PRODUCTION_FINANCIAL_CUTOVER=BLOCKED", script)
        caddy = (LOGIN / "Caddyfile.dashboard_polish").read_text()
        self.assertIn("reverse_proxy sbi-dashboard-polish:8080", caddy)
        self.assertIn("reverse_proxy sbi-preview:8080", caddy)
        self.assertIn("/control-tower/*", caddy)
        self.assertIn("/pipeline", caddy)


if __name__ == "__main__":
    unittest.main()
