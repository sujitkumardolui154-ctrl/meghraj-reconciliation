"""No-bank-data synthetic regression: original-S zero precedence and evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))
from sbi_marker_precedence_shadow import (
    classify_original_s, normalize_sol_text, ordinary_tds_matches,
    shadow_review,
)


def inputs(**changes):
    b = dict(
        invoice_marker="0", marker_cell_type="n", marker_is_formula=False,
        bank_source_status="", bank_sol="00123", invoice_sol="123",
        bank_date="2026-11-06", invoice_issue_date="2026-10-10",
        bank_credit="117", invoice_gross="118", taxable="100",
        source_master_verified=True, prior_ledger_verified=True,
        contradictory_reference=False, competing_claim=False,
    )
    b.update(changes)
    return b


class SBIInvoiceMarkerPrecedenceTests(unittest.TestCase):
    def test_01_original_numeric_zero_is_legacy_review_only(self):
        x = shadow_review(**inputs())
        self.assertFalse(x["strict_blank_policy_candidate"])
        self.assertTrue(x["historical_zero_or_blank_policy_candidate"])
        self.assertFalse(x["policy_precedence_resolved"])
        self.assertEqual(x["review_state"], "CANDIDATE_FOR_MASTER_REVIEW_ONLY")
        self.assertFalse(x["new_allocation_approved"])

    def test_02_blank_source_marker_qualifies_for_both_policy_screens(self):
        x = shadow_review(**inputs(invoice_marker=""))
        self.assertTrue(x["strict_blank_policy_candidate"])
        self.assertTrue(x["historical_zero_or_blank_policy_candidate"])

    def test_03_numeric_nonzero_existing_receipt_is_blocked(self):
        x = shadow_review(**inputs(invoice_marker="118"))
        self.assertFalse(x["historical_zero_or_blank_policy_candidate"])
        self.assertIn("INVOICE_SOURCE_S_NOT_ELIGIBLE", x["reasons"])

    def test_04_excel_text_zero_never_promoted(self):
        x = shadow_review(**inputs(invoice_marker="0",marker_cell_type="s"))
        self.assertEqual(x["source_s_marker_class"], "TEXT_OR_ERROR")
        self.assertFalse(x["historical_zero_or_blank_policy_candidate"])

    def test_05_formula_zero_is_ambiguous(self):
        x = shadow_review(**inputs(marker_is_formula=True))
        self.assertEqual(x["source_s_marker_class"], "FORMULA_NEEDS_RECALC")
        self.assertEqual(x["review_state"], "BLOCKED_OR_PROTECTED_REVIEW")

    def test_06_preserve_bank_L_OK_even_with_perfect_amount(self):
        x = shadow_review(**inputs(bank_source_status=" OK "))
        self.assertIn("PROTECT_HISTORICAL_BANK_L_OK", x["reasons"])
        self.assertEqual(x["review_state"], "BLOCKED_OR_PROTECTED_REVIEW")

    def test_07_bank_before_invoice_blocks_match(self):
        x = shadow_review(**inputs(bank_date="2026-08-01"))
        self.assertIn("BANK_PREDATES_INVOICE", x["reasons"])

    def test_08_invalid_bank_date_fails_closed(self):
        x = shadow_review(**inputs(bank_date="2030000000000"))
        self.assertIn("DATE_EVIDENCE_NOT_VERIFIED", x["reasons"])

    def test_09_leading_zero_code_equality_without_mutating_sources(self):
        self.assertEqual(normalize_sol_text("00123"),"123")
        x = shadow_review(**inputs())
        self.assertNotIn("SOL_TEXT_CODE_MISMATCH", x["reasons"])

    def test_10_unverified_SOL_master_blocks_allocation(self):
        x = shadow_review(**inputs(source_master_verified=False))
        self.assertIn("APPROVED_SOL_MASTER_NOT_VERIFIED", x["reasons"])

    def test_11_conflicting_MXP_invoice_reference_blocks(self):
        x = shadow_review(**inputs(contradictory_reference=True))
        self.assertIn("CONTRADICTORY_INVOICE_REFERENCE", x["reasons"])

    def test_12_duplicate_claim_blocks(self):
        x = shadow_review(**inputs(competing_claim=True))
        self.assertIn("GLOBAL_COMPETING_PAYMENT_OR_INVOICE", x["reasons"])

    def test_13_prior_ledger_provenance_is_required(self):
        x = shadow_review(**inputs(prior_ledger_verified=False))
        self.assertIn("PRIOR_ALLOCATION_LEDGER_NOT_VERIFIED", x["reasons"])

    def test_14_ordinary_tds_round_half_up_to_paise(self):
        self.assertEqual(ordinary_tds_matches(
            bank_credit="116.76", invoice_gross="117.76", taxable="100.50"
        ), ("1",))
        self.assertEqual(ordinary_tds_matches(
            bank_credit="117", invoice_gross="118", taxable="100"
        ), ("1",))

    def test_15_other_methods_remain_review_only(self):
        x=shadow_review(**inputs(bank_credit="90"))
        self.assertIn("OTHER_OWNER_APPROVED_METHOD_REQUIRED_OR_NO_AMOUNT_MATCH", x["reasons"])
        self.assertFalse(x["new_allocation_approved"])

    def test_16_strict_source_copy_and_financial_never_modified(self):
        params=inputs();saved=copy.deepcopy(params)
        x=shadow_review(**params)
        self.assertEqual(params,saved)
        self.assertFalse(x["source_cells_mutated"])
        self.assertEqual(x["finance_decision"],"NOT_VERIFIED")

    def test_17_invalid_numbers_fail_closed(self):
        x=shadow_review(**inputs(bank_credit="NaN"))
        self.assertIn("FINANCIAL_AMOUNTS_INVALID",x["reasons"])

    def test_18_cross_SOL_mismatch_not_silently_assigned(self):
        x=shadow_review(**inputs(invoice_sol="999"))
        self.assertIn("SOL_TEXT_CODE_MISMATCH",x["reasons"])


if __name__ == "__main__":
    unittest.main()
