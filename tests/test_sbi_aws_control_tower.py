"""Source-and-session regression for restoring the original Control Tower.

Run: python3 -m unittest tests/test_sbi_aws_control_tower.py -v
"""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LOGIN = ROOT / "staging/aws_login_v150"
for folder in (ROOT / "dashboard_source", LOGIN, ROOT / "staging/railway_public"):
    sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location("aws_login_control_tower_test", LOGIN / "app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TowerRestoreTests(unittest.TestCase):
    def setUp(self):
        module.app.testing = True
        self.client = module.app.test_client()

    def authenticated(self):
        self.client.set_cookie("__Host-dil_session", "synthetic", secure=True)
        user = SimpleNamespace(uid="synthetic", disabled=False, email="test@example.invalid",
                               custom_claims={"dil_dashboard": True}, display_name="test")
        return (
            patch("dashboard_sessions.firebase_app", return_value=None),
            patch("dashboard_sessions.auth.verify_session_cookie", return_value={"uid": "synthetic"}),
            patch("dashboard_sessions.auth.get_user", return_value=user),
        )

    def test_tower_and_data_are_not_public(self):
        for route in ("/control-tower", "/control-tower/api/pipeline/status",
                      "/control-tower/api/pipeline/version",
                      "/control-tower/api/pipeline/history.csv",
                      "/control-tower/api/priority-tasks"):
            self.assertEqual(self.client.get(route).status_code, 401, route)

    def test_original_control_tower_reused_under_same_login(self):
        a, b, c = self.authenticated()
        with a, b, c:
            dashboard = self.client.get("/dashboard")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn(b'id="dil-tower-button"', dashboard.data)
            self.assertIn(b'data-src="/control-tower?embedded=1"', dashboard.data)
            page = self.client.get("/control-tower")
            self.assertEqual(page.status_code, 200)
            for original in (b"All stages. One control center.",
                             b"Project priorities", b"Task pipeline",
                             b"critical", b"Version log"):
                self.assertIn(original.lower(), page.data.lower())
            self.assertIn(b'href="/dashboard"', page.data)
            self.assertIn(b"/control-tower/api/pipeline/status", page.data)
            self.assertNotIn(b'fetch("/api/pipeline/status', page.data)
            self.assertIn("frame-ancestors 'none'",
                          page.headers.get("Content-Security-Policy", ""))

    def test_live_monitor_returns_source_backed_data_only(self):
        payload = {
            "register": {"available": True, "total": 2, "tasks": []},
            "activity": {"events": [{"kind": "code_change", "timestamp": "2026-11-19",
                                    "title": "test", "status": "source_only"}]},
            "financial_api_connected": False,
        }
        a, b, c = self.authenticated()
        with a, b, c, patch("tower_readonly.current_pipeline", return_value=payload):
            status = self.client.get("/control-tower/api/pipeline/status")
            self.assertEqual(status.status_code, 200)
            self.assertFalse(status.json["financial_api_connected"])
            self.assertEqual(status.json["register"]["total"], 2)
            self.assertFalse(status.json["deployed_build"]["financial_api_connected"])
            self.assertEqual(self.client.get("/control-tower/api/pipeline/version").status_code, 200)
            history = self.client.get("/control-tower/api/pipeline/history.csv")
            self.assertEqual(history.status_code, 200)
            self.assertIn(b"GitHub evidence URL", history.data)

    def test_financial_and_owner_writes_stay_blocked(self):
        a, b, c = self.authenticated()
        with a, b, c:
            self.assertEqual(self.client.get("/control-tower/api/priority-tasks").status_code, 503)
            self.assertEqual(self.client.get("/api/reports").status_code, 403)
            self.assertEqual(self.client.get("/api/health").status_code, 403)
            self.assertEqual(self.client.get("/users").status_code, 403)
            self.assertEqual(self.client.post(
                "/control-tower/api/priority-tasks", json={"title":"Denied"},
                headers={"Origin": module.SITE_ORIGIN}).status_code, 403)

    def test_original_pipeline_and_staging_are_not_modified(self):
        caddy = (LOGIN / "Caddyfile.phase1").read_text()
        self.assertIn("reverse_proxy sbi-preview:8080", caddy)
        docker = (LOGIN / "Dockerfile").read_text()
        self.assertIn("COPY staging/railway_public/pipeline.html /app/pipeline.html", docker)
        self.assertIn("COPY staging/railway_public/pipeline_data.py /app/pipeline_data.py", docker)
        self.assertNotIn("priority_tasks.py /app/", docker)


if __name__ == "__main__":
    unittest.main()
