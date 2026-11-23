"""Synthetic Phase 2 Cloud Run canary gate: no cloud or financial access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_stage_canary", ROOT / "staging/gcp_owner_private/canary.py"
)
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)
SHA = "abcdef1234567890abcdef1234567890abcdef12"
FLAGS = {
    "STAGING_ONLY": "true",
    "FINANCIAL_WRITES_DISABLED": "true",
    "RECONCILIATION_EXECUTION_ENABLED": "false",
    "SOURCE_COMMIT_SHA": SHA,
}


class CanarySafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.evidence = self.root / "checked.py"
        self.evidence.write_text("def f(): return 42\n", encoding="utf-8")
        import hashlib
        self.manifest = self.root / "RELEASE_PREFLIGHT_MANIFEST.json"
        self.payload = {
            "result": "PASS_SOURCE_PACKAGE_ONLY",
            "production_release": "BLOCKED",
            "cloud_staging_deployment": "NOT_PERFORMED",
            "finance_database_write_permission": "NOT_GRANTED",
            "source_files": {
                "checked.py": {"sha256": hashlib.sha256(self.evidence.read_bytes()).hexdigest(), "bytes": self.evidence.stat().st_size}
            }
        }
        # Canary deliberately requires 8 independently hashed files.
        for j in range(1, 8):
            name = f"checked_{j}.py"
            path = self.root / name
            path.write_text(f"print({j})\n")
            self.payload["source_files"][name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
        self.save_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def save_manifest(self):
        self.manifest.write_text(json.dumps(self.payload))

    def verify(self, overrides=None):
        env=dict(FLAGS)
        env.update(overrides or {})
        return canary.validate_runtime(environ=env, source_manifest=self.manifest)

    def test_01_valid_readonly_source_can_start(self):
        self.assertEqual(self.verify()["source_files_verified"], 8)

    def test_02_source_commit_must_be_full_hex_sha(self):
        with self.assertRaisesRegex(RuntimeError, "UNPINNED_SOURCE_COMMIT"):
            self.verify({"SOURCE_COMMIT_SHA":"latest"})

    def test_03_cloud_staging_flag_required(self):
        with self.assertRaisesRegex(RuntimeError, "RUNTIME_FLAGS"):
            self.verify({"STAGING_ONLY":"false"})

    def test_04_finance_write_disabled_flag_required(self):
        with self.assertRaisesRegex(RuntimeError, "RUNTIME_FLAGS"):
            self.verify({"FINANCIAL_WRITES_DISABLED":"false"})

    def test_05_reconciliation_execution_disabled_flag_required(self):
        with self.assertRaisesRegex(RuntimeError, "RUNTIME_FLAGS"):
            self.verify({"RECONCILIATION_EXECUTION_ENABLED":"true"})

    def test_06_source_hash_tamper_fails_closed(self):
        self.evidence.write_text("def f(): return 0\n")
        with self.assertRaisesRegex(RuntimeError, "SOURCE_DIGEST_MISMATCH"):
            self.verify()

    def test_07_source_manifest_requires_blocked_production(self):
        self.payload["production_release"]="OK"
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "RELEASE_GUARD"):
            self.verify()

    def test_08_financial_permission_must_be_not_granted(self):
        self.payload["finance_database_write_permission"]="GRANTED"
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "FINANCE_PERMISSION"):
            self.verify()

    def test_09_no_claim_of_deployed_source_inside_manifest(self):
        self.payload["cloud_staging_deployment"]="DEPLOYED"
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "FALSE_CLAIM"):
            self.verify()

    def test_10_no_unauthorized_source_file_count(self):
        del self.payload["source_files"]["checked_1.py"]
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_SOURCE"):
            self.verify()

    def test_11_source_symlinks_fail_closed(self):
        path=self.root/"checked_1.py"
        path.unlink()
        path.symlink_to(self.evidence)
        with self.assertRaisesRegex(RuntimeError, "UNSAFE_SOURCE_PATH"):
            self.verify()

    def test_12_health_is_readonly_and_reports_not_connected(self):
        status,p=canary.payload("/healthz", self.verify())
        self.assertEqual(status,200)
        self.assertFalse(p["financial_database_connected"])
        self.assertEqual(p["source_commit"],SHA)

    def test_13_release_evidence_is_not_real_application_claim(self):
        status,p=canary.payload("/release-evidence",self.verify())
        self.assertEqual(status,200)
        self.assertEqual(p["real_application_runtime"],"NOT_INCLUDED")
        self.assertEqual(p["live_bank_invoice_parity"],"NOT_VERIFIED")

    def test_14_financial_apis_denied(self):
        for route in ("/api/reports","/imports/preview","/upload",
                      "/reports/credit-note.csv","/payments","/admin/users",
                      "/credit-note/report","/reconciliation/apply"):
            status,_=canary.payload(route, self.verify())
            self.assertEqual(status,503,route)

    def test_15_unknown_route_not_exposing_finance(self):
        status,_=canary.payload("/surprise",self.verify())
        self.assertEqual(status,404)


if __name__ == "__main__":
    unittest.main()
