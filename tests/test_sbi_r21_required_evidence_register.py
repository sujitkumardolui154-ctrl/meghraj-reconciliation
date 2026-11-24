"""R21 release-evidence register: cannot promote synthetic tests to bank approval."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"/"ci"))
from sbi_r21_required_evidence_register import (
    assess_evidence, inspect_candidate_receipt, inspect_development_tree,
    REQUIRED_FILES, GATES, EvidenceRefusal, KNOWN_OLDER_ENGINE_SHA,
)


def baseline(claims=None):
    return assess_evidence(ROOT,claims)


class R21ProvenanceAndHandoverTests(unittest.TestCase):
    def test_01_full_development_source_allowlist_hashes(self):
        r=baseline()
        self.assertEqual(len(r["development_files_sha256"]),len(REQUIRED_FILES))

    def test_02_all_8_independent_gates_present(self):
        self.assertEqual(len(baseline()["gates"]),8)

    def test_03_all_gates_blocked_without_external_authority(self):
        self.assertTrue(all(
            x["status"]=="BLOCKED_EXTERNAL_EVIDENCE" for x in baseline()["gates"]
        ))

    def test_04_no_synthetic_CI_can_unlock_finance(self):
        r=baseline()
        self.assertEqual(r["synthetic_ci_reference"]["tests_passed_reported"],206)
        self.assertTrue(r["financial_apply_locked"])
        self.assertFalse(r["production_financial_release_ready"])

    def test_05_real_bank_not_claimed_accessed(self):
        r=baseline()
        self.assertEqual(r["real_bank_allocations"],0)
        self.assertFalse(r["real_financial_database_accessed"])

    def test_06_previous_green_CI_is_scoped_not_finance_approved(self):
        r=baseline()
        self.assertFalse(r["synthetic_ci_reference"]["financial_method_certification"])

    def test_07_untrusted_all_pass_booleans_cannot_promote(self):
        claims={k:True for k,_ in GATES}
        claims.update(approved=True,security_signed=True,finance_authorized=True)
        self.assertFalse(baseline(claims)["production_financial_release_ready"])

    def test_08_untrusted_forged_bank_provenance_cannot_promote(self):
        r=baseline({"source_attached":True,"source_sha256":"a"*64,
                    "fresh_user_request":True,"original_workbook_provenance":True})
        self.assertEqual(r["gates"][0]["reason"],
                         "CURRENT_REQUEST_FFI001_ATTACHMENT_PROVENANCE_REQUIRED")

    def test_09_untrusted_master_signoff_cannot_promote(self):
        r=baseline({"master_approved":True,"master_sha256":"f"*64})
        self.assertEqual(r["gates"][1]["status"],"BLOCKED_EXTERNAL_EVIDENCE")

    def test_10_untrusted_R14_token_pass_cannot_promote(self):
        r=baseline({"real_signed_id_token_passed":True,"flask_session_passed":True})
        self.assertIn("R14_REAL_CLOUD_SHELL",r["gates"][5]["reason"])

    def test_11_untrusted_real_AWS_report_cannot_promote(self):
        r=baseline({"aws_staging_postgres_readonly_verified":True,
                    "production_database_write_denied":True})
        self.assertEqual(r["gates"][6]["status"],"BLOCKED_EXTERNAL_EVIDENCE")

    def test_12_two_known_archived_engine_hashes_rejected(self):
        for digest in KNOWN_OLDER_ENGINE_SHA:
            with self.subTest(digest=digest[:10]):
                p=inspect_candidate_receipt({"sha256":digest,"master_version":"v2.51",
                                             "matrix_version":"v2.39","approved":True})
                self.assertEqual(p["result"],"REJECTED")

    def test_13_missing_engine_candidate_declares_unverified(self):
        self.assertEqual(inspect_candidate_receipt(None)["result"],"NOT_VERIFIED")

    def test_14_arbitrary_candidate_source_hash_still_not_certified(self):
        p=inspect_candidate_receipt({
            "sha256":"b"*64,
            "master_version":"v2.51",
            "matrix_version":"v2.39",
            "approved":True, "finance_signed":True,"tests_passed":99999,
        })
        self.assertFalse(p["release_eligible"])
        self.assertFalse(p["independent_method_coverage"])

    def test_15_wrong_candidate_version_remains_unverified(self):
        p=inspect_candidate_receipt({"sha256":"c"*64,
                                   "master_version":"v2.22","matrix_version":"v2.10"})
        self.assertEqual(p["reason"],"APPROVED_VERSION_PAIR_NOT_PROVEN")

    def test_16_missing_candidate_hash_refused(self):
        with self.assertRaisesRegex(EvidenceRefusal,"ENGINE_CANDIDATE_SHA256_REQUIRED"):
            inspect_candidate_receipt({"master_version":"v2.51"})

    def test_17_bad_candidate_hash_syntax_refused(self):
        with self.assertRaisesRegex(EvidenceRefusal,"ENGINE_CANDIDATE_SHA256_REQUIRED"):
            inspect_candidate_receipt({"sha256":"abcd"})

    def test_18_non_dict_candidate_refused(self):
        with self.assertRaisesRegex(EvidenceRefusal,"ENGINE_CANDIDATE_MANIFEST_INVALID"):
            inspect_candidate_receipt("approved")

    def test_19_non_dict_claims_refused(self):
        with self.assertRaisesRegex(EvidenceRefusal,"EVIDENCE_CLAIMS_MUST_BE_OBJECT"):
            baseline(["approved"])

    def test_20_missing_repository_root_refused(self):
        with self.assertRaisesRegex(EvidenceRefusal,"CHECKED_OUT_DEVELOPMENT_TREE_REQUIRED"):
            inspect_development_tree(Path("/definitely-not-the-project"))

    def test_21_missing_required_source_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(EvidenceRefusal,"DEVELOPMENT_REFERENCE_MODULE_MISSING"):
                inspect_development_tree(Path(tmp))

    def test_22_json_serializes_to_nonsecret_aggregate(self):
        r=baseline()
        json_dump=json.dumps(r)
        for private in ("AIza", "idToken", "PRIVATE KEY",
                        "SBI-R9-TEST-PASSWORD", "SYN-PAY-001", "MXP19970"):
            self.assertNotIn(private,json_dump)

    def test_23_real_R14_not_approved_by_offline_tests(self):
        r=baseline()
        self.assertEqual(r["gates"][5]["status"],"BLOCKED_EXTERNAL_EVIDENCE")

    def test_24_disposable_sql_is_not_real_staging_sql(self):
        r=baseline()
        self.assertEqual(r["gates"][6]["reason"],
                         "DISPOSABLE_CI_POSTGRES_NOT_REAL_STAGING_DATABASE")

    def test_25_not_a_production_main_deployment(self):
        self.assertFalse(baseline()["production_main_deployed"])

    def test_26_release_lock_exact(self):
        self.assertEqual(baseline()["release_lock"],"FINANCIAL_APPLY_LOCKED")

if __name__=="__main__":
    unittest.main()
