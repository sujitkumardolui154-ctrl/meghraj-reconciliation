"""Only synthetic identifiers and names; NO original bank or SBI data in CI."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
from sbi_r25_sol_identity_review import (
    R25IdentityReviewRefusal, review_identity,
)

SYN = (
    ("0001", "SYNTHETIC ALPHA"),
    ("0002", "SYNTHETIC BETA"),
    ("1", "SYNTHETIC DIFFERENT"),
)


def scan(sol, client="SYNTHETIC ALPHA", master=SYN):
    return review_identity(sol, client, master)


class R25SOLIdentityReview(unittest.TestCase):
    def test_01_exact_text_sol_name_still_unapproved(self):
        r = scan("0001")
        self.assertEqual(r["status"], "EXACT_SOL_AND_OFFICIAL_NAME_REVIEW_ONLY")
        self.assertEqual(r["candidate_master_sol"], "0001")
        self.assertFalse(r["formal_master_authority_verified"])
        self.assertFalse(r["payment_allocation_executed"])

    def test_02_unique_padded_name_is_review_only(self):
        r = scan("2", "SYNTHETIC BETA")
        self.assertEqual(r["status"], "UNIQUE_PADDED_SOL_OFFICIAL_NAME_REVIEW_ONLY")
        self.assertEqual(r["source_sol_preserved"], "2")
        self.assertEqual(r["candidate_master_sol"], "0002")
        self.assertFalse(r["production_release_authorized"])

    def test_03_numeric_source_sol_never_silently_coerced(self):
        r = scan(1)
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["candidate_master_sol"])
        self.assertIn("SOURCE_SOL_NON_TEXT_OR_INVALID_HOLD", r["reason_codes"])

    def test_04_bad_source_sol_text_held(self):
        for sol in ("NA", "1.0", "SOL1", "01 ", "-1", "1\n", ""):
            with self.subTest(sol=sol):
                self.assertIn("SOURCE_SOL_NON_TEXT_OR_INVALID_HOLD",
                              scan(sol)["reason_codes"])

    def test_05_exact_sol_does_not_merge_with_padded_distinct_key(self):
        r = scan("1", "SYNTHETIC DIFFERENT")
        self.assertEqual(r["candidate_master_sol"], "1")
        self.assertTrue(r["zero_padding_collision"])
        self.assertEqual(r["numeric_equivalent_master_sols"], ["0001", "1"])

    def test_06_collision_but_no_exact_source_sol_is_held(self):
        r = scan("01", "SYNTHETIC ALPHA")
        self.assertEqual(r["status"], "HOLD")
        self.assertIn("AMBIGUOUS_ZERO_PADDED_MASTER_KEYS_HOLD", r["reason_codes"])
        self.assertIsNone(r["candidate_master_sol"])

    def test_07_unique_padded_wrong_client_held(self):
        r = scan("2", "SYNTHETIC WRONG")
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["candidate_master_sol"], "0002")
        self.assertIn("PADDED_SOL_NAME_MISMATCH_HOLD", r["reason_codes"])

    def test_08_exact_sol_wrong_client_held(self):
        r = scan("0001", "SYNTHETIC OTHER")
        self.assertIn("EXACT_SOL_CLIENT_NAME_MISMATCH_HOLD", r["reason_codes"])

    def test_09_generic_client_not_promoted(self):
        for name in ("SBI", "STATE BANK OF INDIA", "", "MISSING", "REVIEW"):
            with self.subTest(name=name):
                r = scan("0001", name)
                self.assertIn("SOURCE_CLIENT_UNVERIFIED_HOLD", r["reason_codes"])

    def test_10_unknown_sol_held(self):
        r = scan("0321")
        self.assertIn("SOL_NOT_IN_MASTER_HOLD", r["reason_codes"])

    def test_11_conflicting_official_names_not_autoselected(self):
        r = scan("0001", master=SYN+(("0001", "SYNTHETIC OTHER"),))
        self.assertIn("CONFLICTING_MASTER_OFFICIAL_NAMES_HOLD", r["reason_codes"])

    def test_12_duplicate_same_sol_name_does_not_create_conflict(self):
        r = scan("0001", master=SYN+(("0001", "SYNTHETIC ALPHA"),))
        self.assertEqual(r["status"], "EXACT_SOL_AND_OFFICIAL_NAME_REVIEW_ONLY")

    def test_13_invalid_master_sol_is_not_imputed(self):
        r = scan("0001", master=SYN+((None, "SYNTHETIC UNKNOWN"),))
        self.assertIn("MASTER_HAS_UNRESOLVED_INVALID_IDENTITIES", r["reason_codes"])
        self.assertEqual(r["master_invalid_identity_rows"], 1)

    def test_14_no_master_claims_authority(self):
        for r in (scan("0001"), scan("2", "SYNTHETIC BETA"), scan("01")):
            self.assertFalse(r["formal_master_authority_verified"])
            self.assertFalse(r["financial_database_connected"])
            self.assertFalse(r["payment_allocation_executed"])
            self.assertTrue(r["financial_apply_locked"])
            self.assertIsNone(r["financial_status"])

    def test_15_missing_master_rows_are_not_fabricated(self):
        r = scan("0001", master=[])
        self.assertIn("SOL_NOT_IN_MASTER_HOLD", r["reason_codes"])

    def test_16_untrusted_master_row_schema_refused(self):
        with self.assertRaisesRegex(R25IdentityReviewRefusal, "MASTER_IDENTITY_PAIR_REQUIRED"):
            scan("0001", master=[("0001",)])

    def test_17_master_too_many_rows_refused(self):
        with self.assertRaisesRegex(R25IdentityReviewRefusal, "MASTER_ROWS_REQUIRED_LIMITED"):
            scan("0001", master=[("0001", "SYNTHETIC")] * 25001)

    def test_18_no_bank_payment_status_terms_from_diagnostic(self):
        output = scan("2", "SYNTHETIC BETA")
        self.assertNotIn("OK", repr(output))
        self.assertNotIn("SUSPENSE", repr(output))
        self.assertNotIn("Duplicate Payment", repr(output))


if __name__ == "__main__":
    unittest.main()
