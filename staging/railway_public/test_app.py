import base64
import os
import importlib.util
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch
from app import app


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.env = patch.dict(os.environ, {
            "PREVIEW_USERNAME": "tester",
            "PREVIEW_PASSWORD": "a-very-long-test-only-password",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def auth(self):
        token = base64.b64encode(b"tester:a-very-long-test-only-password").decode()
        return {"Authorization": "Basic " + token}

    def test_login_required(self):
        self.assertEqual(self.client.get("/").status_code, 401)
        self.assertEqual(self.client.get("/api/pipeline/status").status_code, 401)
        self.assertEqual(self.client.get("/pipeline").status_code, 401)

    def test_health_non_sensitive(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["financial_data_connected"])

    def test_dashboard_html_is_auth_protected_and_read_only(self):
        r = self.client.get("/", headers=self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"All stages. One control center.", r.data)
        self.assertIn(b"Financial production restricted", r.data)
        self.assertEqual(r.headers["Cache-Control"], "private, no-store")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_pipeline_status_is_read_only_and_no_mock_agent_running(self):
        record = {
            "sources": {"qa": "available", "staging": "available",
                        "task_register": "available"},
            "financial_api_connected": False,
            "financial_production": "restricted",
            "register": {"available": True, "total": 92, "tasks": []},
        }
        with patch("app.current_pipeline", return_value=record) as status:
            r = self.client.get("/api/pipeline/status", headers=self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["register"]["total"], 92)
        self.assertFalse(r.json["financial_api_connected"])
        status.assert_called_once()


    def test_deployed_version_only_from_embedded_image_sha(self):
        sha = "a" * 40
        with patch.dict(os.environ, {"SBI_SOURCE_SHA": sha,
                                      "SBI_RELEASE_CHANNEL": "aws-staging"}):
            response = self.client.get("/api/pipeline/version", headers=self.auth())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["version"], "git-" + sha[:12])
            self.assertEqual(response.json["channel"], "aws-staging")
            self.assertEqual(response.json["source_sha"], sha)
            self.assertIsNone(response.json["deployed_at_utc"])
        with patch.dict(os.environ, {"SBI_SOURCE_SHA": "main",
                                      "SBI_RELEASE_CHANNEL": "aws-public-preview"}):
            response = self.client.get("/api/pipeline/version", headers=self.auth())
            self.assertEqual(response.json["version"], "UNVERIFIED")
            self.assertIsNone(response.json["source_sha"])

    def test_deployment_history_csv_authenticated_and_safe(self):
        self.assertEqual(self.client.get("/api/pipeline/history.csv").status_code, 401)
        data = {
            "activity": {"events": [{"kind": "code_change",
                "timestamp": "2026-11-03T07:00:00Z", "version": "git-abcdef123456",
                "status": "source_only", "title": "=HYPERLINK(\"bad\")",
                "url": "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/commit/abc"}]}
        }
        with patch("app.current_pipeline", return_value=data):
            response = self.client.get("/api/pipeline/history.csv", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("Content-Type", ""))
        self.assertIn("git-abcdef123456", response.get_data(as_text=True))
        self.assertIn("'=HYPERLINK", response.get_data(as_text=True))

    def test_dashboard_exposes_version_history_section(self):
        response = self.client.get("/", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Version &amp; deployment change log", response.data.replace(b"& deployment", b"&amp; deployment"))
        self.assertIn(b"/api/pipeline/history.csv", response.data)
        self.assertIn(b"running-version", response.data)


    def test_git_change_log_does_not_claim_code_deployed(self):
        import pipeline_data
        sha = "b" * 40
        response = [{"sha": sha, "html_url": "https://github.com/example/commit/" + sha,
                     "commit": {"message": "Version update\\nmore details",
                                "committer": {"date": "2026-11-03T09:00:00Z"}}}]
        with patch("pipeline_data._fetch_payload", return_value=response):
            changes = pipeline_data._recent_changes()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["version"], "git-" + sha[:12])
        self.assertEqual(changes[0]["status"], "source_only")

    def test_staging_history_status_is_from_github_run(self):
        import pipeline_data
        sha = "c" * 40
        response = {"workflow_runs": [
            {"head_sha": sha, "status": "completed", "conclusion": "failure",
             "name": "Staging", "id": 123, "created_at": "2026-11-03T09:00:00Z",
             "updated_at": "2026-11-03T09:01:00Z", "html_url": "https://github.com/example/actions/runs/123"}
        ]}
        with patch("pipeline_data._fetch_json", return_value=response):
            events = pipeline_data._deployment_history()
        self.assertEqual(events[0]["kind"], "staging_release")
        self.assertEqual(events[0]["status"], "failure")
        self.assertEqual(events[0]["run_id"], 123)


    def test_public_versioned_release_scripts_parse(self):
        folder = Path(__file__).resolve().parents[1] / "aws_lightsail"
        for name in ("publish_pipeline_dashboard.sh", "release_pipeline_dashboard.sh"):
            with self.subTest(name=name):
                proc = subprocess.run(["bash", "-n", str(folder / name)],
                                      capture_output=True, text=True, check=False)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_public_release_receipt_contains_version_and_no_financial_data(self):
        source = (Path(__file__).resolve().parents[1] /
                  "aws_lightsail/publish_pipeline_dashboard.sh").read_text()
        self.assertIn('SBI_SOURCE_SHA="$SHA"', source)
        self.assertIn('SBI_RELEASE_CHANNEL=aws-public-preview', source)
        self.assertIn('RELEASE_AUDIT_DIR=', source)
        self.assertIn('write_receipt "success"', source)
        self.assertIn('write_receipt "failure"', source)
        self.assertIn('"financial_writes": False', source)
        self.assertIn('chmod 0600 "$RELEASE_AUDIT.sha256"', source)
        for unsafe in ("gh secret set", "docker compose down", "gcloud run deploy",
                       "firestore", "PAYMENT_DATABASE_URL"):
            self.assertNotIn(unsafe, source)

    def test_legacy_public_preview_credential_rotation_contract(self):
        script = Path(__file__).resolve().parents[1] / "aws_lightsail" / "rotate_public_preview_login.py"
        self.assertTrue(script.is_file())
        spec = importlib.util.spec_from_file_location("sbi_preview_rotation_contract", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = "SITE_DOMAIN=example.com\\nPREVIEW_USERNAME=reviewer\\nPREVIEW_PASSWORD=short\\n"
        revised = module.replace_password(original, "safe-secret-string-1234567890")
        self.assertIn("SITE_DOMAIN=example.com", revised)
        self.assertIn("PREVIEW_USERNAME=reviewer", revised)
        self.assertIn("PREVIEW_PASSWORD=safe-secret-string-1234567890", revised)
        self.assertNotIn("PREVIEW_PASSWORD=short", revised)
        with self.assertRaises(ValueError):
            module.replace_password(original, "short")
        with self.assertRaises(ValueError):
            module.replace_password(original + "PREVIEW_PASSWORD=duplicate\\n", "safe-secret-string-1234567890")
        with self.assertRaises(ValueError):
            module.replace_password(original, "not safe with spaces 1234567890")
        source = script.read_text(encoding="utf-8")
        self.assertIn("getpass.getpass", source)
        self.assertIn("AUTH_ROTATION_ROLLBACK=ATTEMPTED", source)
        self.assertIn("PUBLIC_IMAGE_UNCHANGED=PASS", source)
        self.assertIn("FINANCIAL_WRITES=DISABLED", source)
        for forbidden in ("docker compose down", "docker system prune", "gcloud run deploy",
                          "gh secret set", "PAYMENT_DATABASE_URL", "docker rm -f"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_api_denied_after_login(self):
        for method, path in [("post", "/api/imports/apply"),
                             ("post", "/api/upload"), ("get", "/api/reports"),
                             ("get", "/api/reconciliation/execute")]:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, headers=self.auth())
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
