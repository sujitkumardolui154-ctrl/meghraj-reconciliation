"""SBI professional dashboard, embedded Tower and private note/task security."""
import importlib.util
import os
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "dashboard_source", ROOT / "staging/aws_login_v150",
               ROOT / "staging/railway_public"):
    sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location(
    "sbi_workspace_release_test", ROOT / "staging/aws_login_v150/app.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrivateWorkspaceTests(unittest.TestCase):
    def setUp(self):
        module.app.testing = True
        self.client = module.app.test_client()
        self.temp = tempfile.TemporaryDirectory(prefix="sbi-private-workspace-")
        self.addCleanup(self.temp.cleanup)
        self.dbfile = str(Path(self.temp.name) / "notes.sqlite3")
        self.path = "/control-tower/api/workspace"
        self.csrf = "a" * 64
        self.client.set_cookie("__Host-dil_session", "synthetic-session", secure=True)
        self.client.set_cookie("__Host-dil_csrf", self.csrf, secure=True)

    def session(self, uid="personal-owner"):
        user = SimpleNamespace(uid=uid, email="user@example.invalid",
                               disabled=False, display_name="QA",
                               custom_claims={"dil_dashboard": True})
        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ,
            {"SBI_PRIVATE_WORKSPACE_DB": self.dbfile}))
        stack.enter_context(patch("dashboard_sessions.firebase_app", return_value=None))
        stack.enter_context(patch("dashboard_sessions.auth.verify_session_cookie",
                                  return_value={"uid":uid}))
        stack.enter_context(patch("dashboard_sessions.auth.get_user", return_value=user))
        return stack

    def headers(self):
        return {"Origin": module.SITE_ORIGIN, "X-DIL-CSRF": self.csrf}

    def test_professional_login_and_dashboard_remove_obsolete_panels(self):
        login = self.client.get("/login")
        self.assertEqual(login.status_code, 200)
        self.assertIn(b"Your operations.", login.data)
        self.assertIn(b"Your priorities.", login.data)
        self.assertEqual(self.client.get("/login.css").status_code, 200)
        with self.session():
            dashboard = self.client.get("/dashboard")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn(b'id="dil-tower-button"', dashboard.data)
            self.assertIn(b'iframe id="dil-tower-frame"', dashboard.data)
            self.assertNotIn(b"Backend API Reports", dashboard.data)
            self.assertNotIn(b"Supervisor API Monitoring", dashboard.data)
            self.assertNotIn(b'<script src="/dashboard.js"', dashboard.data)
            self.assertIn(b"Plan, monitor and deliver", dashboard.data)
            css_response = self.client.get("/dashboard-theme.css")
            self.assertEqual(css_response.status_code, 200,
                "ROOT="+str(module.UI_ROOT)+
                " FILE="+str((module.UI_ROOT/"dashboard-theme.css").exists())+
                " ROUTES="+repr(sorted(str(r.rule) for r in module.app.url_map.iter_rules())))
            tower = self.client.get("/control-tower?embedded=1")
            self.assertEqual(tower.status_code, 200)
            for section in (b"Project priorities", b"Essential", b"Critical obstructions",
                            b"Staging deployment history", b"Pending task pipeline",
                            b"Owner-added priority tasks", b"Project notes"):
                self.assertIn(section.lower(), tower.data.lower(), section)
            self.assertEqual(tower.headers["X-Frame-Options"], "SAMEORIGIN")
            self.assertIn("frame-ancestors 'self'",
                          tower.headers["Content-Security-Policy"])
            self.assertEqual(self.client.get("/control-tower/theme.css").status_code, 200)

    def test_notes_and_tasks_are_private_durable_and_editable(self):
        with self.session():
            self.assertEqual(self.client.get(self.path).json["items"], [])
            task = {"kind":"task","title":"Verify staging history",
                    "body":"Check GitHub evidence","priority":"P0",
                    "status":"pending","due_on":"2026-12-01"}
            created = self.client.post(self.path, json=task, headers=self.headers())
            self.assertEqual(created.status_code, 201)
            tid = created.json["item_id"]
            note = {"kind":"note","title":"Design decision",
                    "body":"Keep the existing release freeze."}
            note_created = self.client.post(self.path, json=note, headers=self.headers())
            self.assertEqual(note_created.status_code, 201)
            items = self.client.get(self.path).json["items"]
            self.assertEqual(len(items), 2)
            self.assertTrue(any(it["title"]=="Design decision" for it in items))
            self.assertEqual(
                self.client.patch(self.path+"/"+tid, json={"status":"done"},
                                  headers=self.headers()).status_code, 200)
            rows = self.client.get(self.path).json["items"]
            self.assertEqual(next(it for it in rows if it["item_id"] == tid)["status"],"done")
            self.assertEqual(
                self.client.delete(self.path+"/"+note_created.json["item_id"],
                                   json={}, headers=self.headers()).status_code, 200)
            self.assertEqual(len(self.client.get(self.path).json["items"]), 1)
            self.assertTrue(Path(self.dbfile).is_file(), "Persistent host volume source")
        with self.session():  # Fresh request context points to the same durable file.
            self.assertEqual(self.client.get(self.path).json["items"][0]["status"], "done")

    def test_user_isolation_write_denial_and_no_finance_access(self):
        with self.session("first"):
            first = self.client.post(self.path, json={
                "kind":"note","title":"Private to first"
            }, headers=self.headers())
            self.assertEqual(first.status_code, 201)
            fid = first.json["item_id"]
            self.assertEqual(self.client.post(
                self.path,json={"kind":"note","title":"No CSRF"},
                headers={"Origin":module.SITE_ORIGIN}).status_code, 403)
            self.assertEqual(self.client.post(
                self.path,json={"kind":"note","title":"Foreign Origin"},
                headers={"Origin":"https://untrusted.example","X-DIL-CSRF":self.csrf}).status_code,403)
            self.assertEqual(self.client.get("/api/reports").status_code,403)
            self.assertEqual(self.client.post("/api/imports/apply", json={},
                headers=self.headers()).status_code,403)
        with self.session("second"):
            self.assertEqual(self.client.get(self.path).json["items"], [])
            self.assertEqual(
                self.client.patch(self.path+"/"+fid, json={"title":"Stolen"},
                    headers=self.headers()).status_code,404)

    def test_invalid_data_is_rejected_and_unconfigured_storage_fails_closed(self):
        with self.session():
            for bad in ({"kind":"task","title":""},
                        {"kind":"task","title":"Ok","status":"approved"},
                        {"kind":"note","title":"a","extra_field":"oops"},
                        {"kind":"task","title":"Ok","body":"b"*4001}):
                result = self.client.post(self.path,json=bad,headers=self.headers())
                self.assertEqual(result.status_code,422,bad)
        with self.session():
            with patch.dict(os.environ,{"SBI_PRIVATE_WORKSPACE_DB":""}):
                result=self.client.get(self.path)
                self.assertEqual(result.status_code,503)
                self.assertIn("unavailable",result.json["error"])

    def test_legacy_preview_and_financial_safety_source(self):
        root = ROOT / "staging/aws_login_v150"
        original=(root/"Caddyfile.control_tower_tab").read_text()
        candidate=(root/"Caddyfile.workspace").read_text()
        self.assertIn("sbi-control-tower-tab:8080",original)
        self.assertIn("sbi-login-workspace:8080",candidate)
        self.assertIn("reverse_proxy sbi-preview:8080",candidate)
        self.assertNotIn("X-Frame-Options DENY",candidate)
        shell=(root/"deploy_workspace_ui.sh").read_text()
        self.assertIn("10001:10001:700",shell)
        self.assertIn("SBI_PRIVATE_WORKSPACE_DB=/data/workspace.sqlite3",shell)
        self.assertIn("FINANCIAL_WRITES=DISABLED",shell)


if __name__ == "__main__":
    unittest.main()
