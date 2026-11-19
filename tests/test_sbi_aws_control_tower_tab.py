"""Same-page Control Tower tab and same-origin iframe security regression."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOGIN = ROOT / "staging/aws_login_v150"
for folder in (ROOT / "dashboard_source", LOGIN, ROOT / "staging/railway_public"):
    sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location("sbi_tab_view_test", LOGIN / "app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ControlTowerTabTests(unittest.TestCase):
    def setUp(self):
        module.app.testing = True
        self.client = module.app.test_client()

    def authenticated(self):
        self.client.set_cookie("__Host-dil_session", "synthetic", secure=True)
        user = SimpleNamespace(uid="synthetic", disabled=False,
                               email="synthetic@example.invalid",
                               custom_claims={"dil_dashboard": True}, display_name="QA")
        return (
            patch("dashboard_sessions.firebase_app", return_value=None),
            patch("dashboard_sessions.auth.verify_session_cookie",
                  return_value={"uid": "synthetic"}),
            patch("dashboard_sessions.auth.get_user", return_value=user),
        )

    def test_tab_click_contract_retains_app_header_and_other_tabs(self):
        a, b, c = self.authenticated()
        with a, b, c:
            page = self.client.get("/dashboard")
            self.assertEqual(page.status_code, 200)
            source = page.get_data(as_text=True)
            self.assertIn('id="dil-tower-button" aria-controls="dil-tower"', source)
            self.assertIn('id="dil-tower" hidden', source)
            self.assertIn('data-src="/control-tower?embedded=1"', source)
            self.assertNotIn('<a href="/control-tower" class="dil-tower-link"', source)
            self.assertIn('button.addEventListener("click"', source)
            self.assertIn('siblingNames = ["home", "reports", "imports"]', source)
            self.assertIn('tower.hidden = false', source)
            self.assertIn('tower.hidden = true', source)
            for sibling in ('dil-home-button', 'dil-reports-button', 'dil-imports-button'):
                self.assertIn('id="' + sibling + '"', source)
            self.assertIn("frame-src 'self'", page.headers["Content-Security-Policy"])
            self.assertEqual(page.headers["X-Frame-Options"], "DENY")

    def test_iframe_same_origin_only_full_page_remains_denied(self):
        a, b, c = self.authenticated()
        with a, b, c:
            stand = self.client.get("/control-tower")
            embed = self.client.get("/control-tower?embedded=1")
            self.assertEqual(stand.status_code, 200)
            self.assertEqual(embed.status_code, 200)
            self.assertEqual(stand.headers["X-Frame-Options"], "DENY")
            self.assertIn("frame-ancestors 'none'",
                          stand.headers["Content-Security-Policy"])
            self.assertNotIn('control-tower-embedded-style', stand.get_data(as_text=True))
            self.assertEqual(embed.headers["X-Frame-Options"], "SAMEORIGIN")
            self.assertIn("frame-ancestors 'self'",
                          embed.headers["Content-Security-Policy"])
            self.assertIn('control-tower-embedded-style', embed.get_data(as_text=True))
            self.assertIn("All stages. One control center.", embed.get_data(as_text=True))

    def test_all_new_routes_require_authentication_and_writes_denied(self):
        self.assertEqual(self.client.get("/control-tower?embedded=1").status_code, 401)
        self.assertEqual(self.client.get("/control-tower/api/pipeline/status").status_code, 401)
        a, b, c = self.authenticated()
        with a, b, c:
            self.assertEqual(self.client.get("/api/reports").status_code, 403)
            self.assertEqual(self.client.get("/control-tower/api/priority-tasks").status_code, 503)
            self.assertEqual(self.client.post(
                "/control-tower/api/priority-tasks",
                json={"title":"DENY"},
                headers={"Origin": module.SITE_ORIGIN}).status_code, 403)

    def test_caddy_blue_green_old_tower_is_untouched(self):
        cfg = (LOGIN / "Caddyfile.control_tower_tab").read_text()
        old = (LOGIN / "Caddyfile.control_tower").read_text()
        self.assertIn("reverse_proxy sbi-control-tower-tab:8080", cfg)
        self.assertIn("reverse_proxy sbi-login-control-tower:8080", old)
        self.assertIn("reverse_proxy sbi-preview:8080", cfg)
        script = (LOGIN / "deploy_control_tower_tab.sh").read_text()
        self.assertIn('PREV="sbi-login-control-tower-stage"', script)
        self.assertIn('BASELINE="$ROOT/staging/aws_login_v150/Caddyfile.control_tower"', script)
        self.assertIn('BACKUP="$CONF/Caddyfile.before-control-tower-tab"', script)
        self.assertIn("CONTROL_TOWER_ROLLBACK=ATTEMPTED", script)
        self.assertIn("FINANCIAL_WRITES=DISABLED", script)


if __name__ == "__main__":
    unittest.main()
