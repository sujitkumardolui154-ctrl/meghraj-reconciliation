"""Offline SBI Credit Note external-readiness preflight regression tests."""
import importlib.util
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / "tools/sbi_cn_external_readiness_preflight.py"
spec = importlib.util.spec_from_file_location("sbi_cn_external_preflight_test", TOOL)
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


class ExternalReadinessPreflightTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        for name in auditor.REQUIRED_SOURCE:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("", encoding="utf-8")
        stage = self.root / "staging/sbi_cn_isolated_stage_app.py"
        stage.write_text(
            "def offline_preview():\n"
            "    return 'STAGING_FINANCIAL_DATABASE_NOT_CONNECTED'\n",
            encoding="utf-8",
        )
        gateway = self.root / auditor.EXPECTED_PRODUCTION_GATEWAY
        gateway.parent.mkdir(parents=True, exist_ok=True)
        gateway.write_text("# no new staging endpoint\n", encoding="utf-8")

    def collect(self, *, clean=True):
        def git(_, cmd):
            return "a" * 40 if cmd == ["rev-parse", "HEAD"] else ("" if clean else " M file")
        with patch.object(auditor, "_git", side_effect=git):
            return auditor.collect(self.root, self.evidence)

    def test_source_preflight_passes_for_separated_offline_stage(self):
        result = self.collect()
        self.assertTrue(result["source_checks"]["source_boundary_pass"])
        self.assertEqual(result["source_commit"], "a" * 40)
        self.assertEqual(
            result["preflight_status"], "LOCAL_SOURCE_PREFLIGHT_PASS_EXTERNAL_BLOCKERS"
        )

    def test_unverified_iam_must_remain_unverified(self):
        result = self.collect()
        self.assertEqual(result["external_gates"]["EFFECTIVE_GOOGLE_CLOUD_READONLY_IAM"], "NOT_VERIFIED")
        self.assertEqual(result["external_gates_certified"], 0)
        self.assertFalse(result["live_database_connected"])

    def test_no_real_login_or_release_claimed(self):
        result = self.collect()
        self.assertFalse(result["real_login_tested"])
        self.assertEqual(result["owner_production_approval"], "NOT_GRANTED")
        self.assertEqual(result["production_cutover"], "BLOCKED")
        self.assertEqual(result["financial_writes"], "NOT_PERFORMED")

    def test_stage_route_registered_in_production_fails_preflight(self):
        gateway = self.root / auditor.EXPECTED_PRODUCTION_GATEWAY
        gateway.write_text("create_credit_note_staging_blueprint()\n", encoding="utf-8")
        self.assertFalse(self.collect()["source_checks"]["source_boundary_pass"])

    def test_missing_required_source_blocks(self):
        (self.root / auditor.REQUIRED_SOURCE[0]).unlink()
        result = self.collect()
        self.assertFalse(result["source_checks"]["source_boundary_pass"])
        self.assertEqual(result["preflight_status"], "LOCAL_SOURCE_REVIEW_REQUIRED_EXTERNAL_BLOCKERS")

    def test_dirty_git_does_not_claim_pass(self):
        result = self.collect(clean=False)
        self.assertFalse(result["source_worktree_clean"])
        self.assertEqual(result["preflight_status"], "LOCAL_SOURCE_REVIEW_REQUIRED_EXTERNAL_BLOCKERS")

    def test_missing_evidence_is_absent_not_a_certification(self):
        result = self.collect()
        self.assertTrue(all(not item["present"] for item in result["evidence_file_presence"]))
        self.assertEqual(result["external_gates"]["INDEPENDENT_FIRESTORE_BACKUP_RESTORE"], "NOT_VERIFIED")

    def test_existing_evidence_presence_only(self):
        p = self.evidence / auditor.KNOWN_EVIDENCE_NAMES[0]
        p.write_text('{"release_status":"REVIEW_REQUIRED"}', encoding="utf-8")
        result = self.collect()
        found = next(x for x in result["evidence_file_presence"] if x["artifact"] == p.name)
        self.assertTrue(found["present"])
        self.assertEqual(found["size_bytes"], p.stat().st_size)
        self.assertEqual(result["external_gates_certified"], 0)

    def test_no_network_calls_are_recorded(self):
        self.assertFalse(
            self.collect()["credential_configuration_flags"]["network_requests_made"]
        )


if __name__ == "__main__":
    main(verbosity=2)
