"""Synthetic owner-task editor QA: SQLite and GitHub are entirely mocked/local.

Run from staging/railway_public: python -m unittest -v test_priority_tasks
"""
import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
import priority_tasks


class PriorityEditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "tasks.db")
        self.key = "owner-test-key-" + "a" * 45
        self.patcher = patch.dict(os.environ, {
            "PREVIEW_USERNAME": "tester",
            "PREVIEW_PASSWORD": "a-very-long-test-only-password",
            "SBI_PRIORITY_DB_PATH": self.db,
            "SBI_TASK_OWNER_KEY": self.key,
            "SBI_GITHUB_ISSUES_TOKEN": "synthetic-no-network-issue-token-987654321",
        })
        self.patcher.start()
        self.client = app.test_client()
        token = base64.b64encode(b"tester:a-very-long-test-only-password").decode()
        self.read_headers = {"Authorization": "Basic " + token}
        self.headers = {**self.read_headers, "Origin": "http://localhost",
                        "Content-Type": "application/json",
                        "X-SBI-Task-Owner": self.key}
        self.payload = {"priority": "P0", "title": "Verify reporting release checklist",
                        "details": "Only synthetic source data. No financial changes.",
                        "status": "pending"}
        self.issue = None

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def gh(self, method, suffix, payload=None):
        if method == "GET" and suffix.startswith("/search/issues?"):
            return {"items": []}
        if method == "POST" and suffix == "/issues":
            self.issue = {"number": 151, "html_url":
                          "https://github.com/" + priority_tasks.REPO + "/issues/151",
                          "body": payload["body"], "title": payload["title"]}
            return self.issue
        if method == "GET" and suffix == "/issues/151":
            return self.issue
        if method == "PATCH" and suffix == "/issues/151":
            self.issue = {**self.issue, "body": payload["body"], "title": payload["title"]}
            return self.issue
        raise AssertionError("Unexpected mocked GitHub API call " + method + " " + suffix)

    def test_preview_auth_and_owner_are_both_required(self):
        self.assertEqual(self.client.get("/api/priority-tasks").status_code, 401)
        self.assertEqual(self.client.post("/api/priority-tasks", json=self.payload).status_code, 401)
        self.assertEqual(self.client.post(
            "/api/priority-tasks", headers=self.read_headers, json=self.payload).status_code, 403)
        bad = {**self.headers, "X-SBI-Task-Owner": "invalid" * 8}
        self.assertEqual(self.client.post(
            "/api/priority-tasks", headers=bad, json=self.payload).status_code, 403)
        crossed = {**self.headers, "Origin": "https://attacker.example"}
        self.assertEqual(self.client.post(
            "/api/priority-tasks", headers=crossed, json=self.payload).status_code, 403)
        no_origin = {k: v for k, v in self.headers.items() if k != "Origin"}
        self.assertEqual(self.client.post(
            "/api/priority-tasks", headers=no_origin, json=self.payload).status_code, 403)
        self.assertFalse(Path(self.db).exists())

    def test_owner_unlock_and_read_only_list(self):
        with patch("priority_tasks._request_github", side_effect=AssertionError("No writes")):
            r = self.client.post("/api/priority-tasks/unlock", headers=self.headers, json={})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json["owner_authorized"])
            r = self.client.get("/api/priority-tasks", headers=self.read_headers)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json["editor_available"])
            self.assertFalse(r.json["financial_database_connected"])
            self.assertEqual(r.json["tasks"], [])

    def test_create_edit_and_read_back_from_sqlite_and_github_issue(self):
        with patch("priority_tasks._request_github", side_effect=self.gh) as remote:
            created = self.client.post("/api/priority-tasks", headers=self.headers,
                                       json=self.payload)
            self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
            one = created.json["task"]
            self.assertEqual(one["sync_state"], "synced")
            self.assertEqual(one["revision"], 1)
            self.assertEqual(one["github_number"], 151)
            self.assertEqual(one["priority"], "P0")
            self.assertTrue(Path(self.db).exists())
            self.assertIn(one["id"], self.issue["body"])
            self.assertEqual(self.issue["title"], "[Priority P0] " + self.payload["title"])
            rows = self.client.get("/api/priority-tasks", headers=self.read_headers).json["tasks"]
            self.assertEqual(len(rows), 1)
            edited = {**self.payload, "priority": "P1", "status": "in_progress",
                      "title": "Improve read-only report usability",
                      "expected_revision": 1}
            response = self.client.patch(
                "/api/priority-tasks/" + one["id"], headers=self.headers, json=edited)
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            self.assertEqual(response.json["task"]["revision"], 2)
            self.assertEqual(response.json["task"]["priority"], "P1")
            self.assertIn("revision 2", self.issue["body"])
            self.assertEqual(self.issue["title"], "[Priority P1] Improve read-only report usability")
            self.assertGreaterEqual(remote.call_count, 4)
        with priority_tasks._db() as conn:
            events = conn.execute("SELECT action FROM priority_task_audit ORDER BY id").fetchall()
            self.assertEqual([e["action"] for e in events], ["create", "edit"])

    def test_failed_github_write_is_queued_and_manual_retry_syncs(self):
        with patch("priority_tasks._request_github",
                   side_effect=priority_tasks.GitHubUnavailable("GitHub down")):
            response = self.client.post(
                "/api/priority-tasks", headers=self.headers, json=self.payload)
        self.assertEqual(response.status_code, 202)
        task = response.json["task"]
        self.assertEqual(task["sync_state"], "pending")
        self.assertIsNone(task["github_url"])
        self.assertEqual(len(self.client.get(
            "/api/priority-tasks", headers=self.read_headers).json["tasks"]), 1)
        with patch("priority_tasks._request_github", side_effect=self.gh):
            retried = self.client.post(
                "/api/priority-tasks/" + task["id"] + "/sync",
                headers=self.headers, json={})
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json["task"]["sync_state"], "synced")

    def test_stale_task_edit_fails_closed(self):
        with patch("priority_tasks._request_github", side_effect=self.gh):
            task = self.client.post(
                "/api/priority-tasks", headers=self.headers, json=self.payload).json["task"]
            bad = {**self.payload, "expected_revision": 0}
            r = self.client.patch("/api/priority-tasks/" + task["id"],
                                  headers=self.headers, json=bad)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(priority_tasks.list_tasks()[0]["revision"], 1)

    def test_invalid_values_and_secrets_rejected(self):
        for payload in (
            {**self.payload, "priority": "P9"},
            {**self.payload, "title": "bad"},
            {**self.payload, "status": "financial_approved"},
            {**self.payload, "details": "Token: ghp_" + "a" * 40},
        ):
            with self.subTest(payload=payload):
                with patch("priority_tasks._request_github",
                           side_effect=AssertionError("Must not call GitHub")):
                    response = self.client.post(
                        "/api/priority-tasks", headers=self.headers, json=payload)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(priority_tasks.list_tasks(), [])

    def test_editor_disabled_when_credentials_not_configured(self):
        with patch("priority_tasks._request_github", side_effect=self.gh):
            created = self.client.post(
                "/api/priority-tasks", headers=self.headers, json=self.payload)
        self.assertEqual(created.status_code, 201)
        with patch.dict(os.environ, {"SBI_GITHUB_ISSUES_TOKEN": ""}):
            r = self.client.get("/api/priority-tasks", headers=self.read_headers)
            self.assertFalse(r.json["editor_available"])
            self.assertEqual(len(r.json["tasks"]), 1)
            self.assertEqual(r.json["tasks"][0]["title"], self.payload["title"])
            self.assertEqual(self.client.post("/api/priority-tasks",
                headers=self.headers, json=self.payload).status_code, 503)

    def test_unrelated_github_issue_cannot_be_edited(self):
        with patch("priority_tasks._request_github", side_effect=self.gh):
            task = self.client.post(
                "/api/priority-tasks", headers=self.headers, json=self.payload).json["task"]
        self.issue = {**self.issue, "body": "Unrelated GitHub issue"}
        with patch("priority_tasks._request_github", side_effect=self.gh):
            r = self.client.patch("/api/priority-tasks/" + task["id"],
                 headers=self.headers, json={**self.payload, "expected_revision": 1})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json["task"]["sync_state"], "pending")

    def test_html_includes_owning_controls_without_exposing_secrets(self):
        r = self.client.get("/", headers=self.read_headers)
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        for needle in ("priority-edit-toggle", "priority-owner-unlock-form",
                       "priority-task-form", "priority-owner-items",
                       "Save to task DB &amp; GitHub", "priority-public-confirm",
                       "GitHub pending", "renderOwnerTasks"):
            self.assertIn(needle, html)
        self.assertNotIn(self.key, html)
        self.assertNotIn(os.environ["SBI_GITHUB_ISSUES_TOKEN"], html)

    def test_financial_endpoints_remain_forbidden(self):
        for method, path in (("post", "/api/upload"),
                             ("post", "/api/imports/apply"),
                             ("get", "/api/reports"),
                             ("post", "/api/reconciliation/execute")):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(
                    path, headers=self.headers).status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
