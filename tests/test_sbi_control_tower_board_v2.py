"""SBI Control Tower combined board, 10-minute GitHub polling and private task order tests."""
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
for p in (ROOT/"dashboard_source",ROOT/"staging/aws_login_v150",ROOT/"staging/railway_public"):
    sys.path.insert(0,str(p))
spec=importlib.util.spec_from_file_location("sbi_board_v2",ROOT/"staging/aws_login_v150/app.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
import pipeline_data
class BoardV2Tests(unittest.TestCase):
    def setUp(self):
        module.app.testing=True
        self.client=module.app.test_client()
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=str(Path(self.temp.name)/"private.sqlite3")
        self.path="/control-tower/api/workspace"
        self.client.set_cookie("__Host-dil_session","test",secure=True)
        self.client.set_cookie("__Host-dil_csrf","a"*64,secure=True)
    def session(self,uid="owner"):
        stack=ExitStack()
        user=SimpleNamespace(uid=uid,disabled=False,email="test@example.invalid",
                 display_name="test",custom_claims={"dil_dashboard":True})
        stack.enter_context(patch.dict(os.environ,{"SBI_PRIVATE_WORKSPACE_DB":self.db}))
        stack.enter_context(patch("dashboard_sessions.firebase_app",return_value=None))
        stack.enter_context(patch("dashboard_sessions.auth.verify_session_cookie",return_value={"uid":uid}))
        stack.enter_context(patch("dashboard_sessions.auth.get_user",return_value=user))
        return stack
    def headers(self):
        return {"Origin":module.SITE_ORIGIN,"X-DIL-CSRF":"a"*64}
    def add(self,title,priority="P0",kind="task"):
        values={"kind":kind,"title":title}
        if kind=="task":values["priority"]=priority
        response=self.client.post(self.path,json=values,headers=self.headers())
        self.assertEqual(response.status_code,201,response.get_data(as_text=True))
        return response.json["item_id"]
    def rows(self):
        response=self.client.get(self.path)
        self.assertEqual(response.status_code,200)
        return response.json["items"]
    def test_github_board_refresh_and_privilege_guards(self):
        self.assertEqual(pipeline_data.TTL_SECONDS,600)
        anonymous=module.app.test_client()
        self.assertEqual(anonymous.get("/control-tower").status_code,401)
        with self.session():
            page=self.client.get("/control-tower?embedded=1")
            self.assertEqual(page.status_code,200)
            html=page.get_data(as_text=True)
            for phrase in ('id="workstream-task-board"','Workstream progress &amp; pending tasks',
                           'id="gb-search"','id="gb-workstream"','id="gb-bucket"',
                           'Execution: ','Verification: ','Approval gate: ',
                           'sbi-github-snapshot','setInterval(refresh,600000)',
                           'Completed archive','My task buckets','Restore to active',
                           '↑ Move up','↓ Move down'):
                self.assertIn(phrase,html,phrase)
            self.assertNotIn('setInterval(refresh,90000)',html)
            self.assertIn('10-minute GitHub cache',html)
            css=self.client.get("/control-tower/theme.css")
            self.assertIn(b"#obstructions > article:nth-child(2), #tasks",css.data)
            self.assertEqual(self.client.get("/api/reports").status_code,403)
            self.assertEqual(self.client.post("/control-tower/api/priority-tasks",
                      json={},headers=self.headers()).status_code,403)
    def test_in_place_migration_preserves_existing_notes(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE personal_items (item_id TEXT PRIMARY KEY,"
                 "owner_uid TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,"
                 "body TEXT NOT NULL,priority TEXT NOT NULL,status TEXT NOT NULL,"
                 "due_on TEXT NOT NULL,created_utc TEXT NOT NULL,updated_utc TEXT NOT NULL)")
            conn.execute("INSERT INTO personal_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                 ("0"*32,"owner","note","Original note","preserve","P1","note","","2026-11-19","2026-11-19"))
        with self.session():
            self.assertEqual(self.rows()[0]["body"],"preserve")
            self.assertIn("sort_order",self.rows()[0])
            self.add("New task")
            self.assertEqual(len(self.rows()),2)
        with sqlite3.connect(self.db) as conn:
            self.assertIn("sort_order",{r[1] for r in conn.execute("PRAGMA table_info(personal_items)")})
    def test_reorder_complete_archive_restore_and_priority_move(self):
        with self.session():
            a=self.add("First");b=self.add("Second");c=self.add("Next",priority="P1")
            r=self.client.post(self.path+"/reorder",json={"priority":"P0","ordered_ids":[b,a]},
                       headers=self.headers())
            self.assertEqual(r.status_code,200,r.get_data(as_text=True))
            self.assertEqual([x["item_id"] for x in self.rows() if x["priority"]=="P0"],[b,a])
            self.assertEqual(self.client.patch(self.path+"/"+b,json={"status":"done"},
                         headers=self.headers()).status_code,200)
            self.assertNotIn(b,[x["item_id"] for x in self.rows() if x["status"]!="done"])
            self.assertIn(b,[x["item_id"] for x in self.rows() if x["status"]=="done"])
            self.assertEqual(self.client.patch(self.path+"/"+b,json={"status":"pending"},
                         headers=self.headers()).status_code,200)
            self.assertEqual([x["item_id"] for x in self.rows() if x["priority"]=="P0"],[a,b])
            self.assertEqual(self.client.patch(self.path+"/"+b,json={"priority":"P1"},
                         headers=self.headers()).status_code,200)
            self.assertEqual([x["item_id"] for x in self.rows() if x["priority"]=="P1"],[c,b])
    def test_csrf_stale_order_and_cross_user_isolation(self):
        with self.session("owner1"):
            a=self.add("Owner 1")
            self.assertEqual(self.client.post(self.path+"/reorder",
                json={"priority":"P0","ordered_ids":[a]},
                headers={"Origin":module.SITE_ORIGIN}).status_code,403)
            self.assertEqual(self.client.post(self.path+"/reorder",
                json={"priority":"P0","ordered_ids":[a,a]},
                headers=self.headers()).status_code,422)
        with self.session("owner2"):
            b=self.add("Owner 2")
            self.assertEqual(self.client.post(self.path+"/reorder",
                json={"priority":"P0","ordered_ids":[a]},
                headers=self.headers()).status_code,409)
            self.assertEqual([r["item_id"] for r in self.rows()],[b])
        with self.session("owner1"):
            self.assertEqual([r["item_id"] for r in self.rows()],[a])
            with patch.dict(os.environ,{"SBI_PRIVATE_WORKSPACE_DB":""}):
                self.assertEqual(self.client.get(self.path).status_code,503)
if __name__=="__main__":unittest.main()
