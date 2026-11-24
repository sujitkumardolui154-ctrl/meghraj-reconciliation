"""Synthetic Case 2.4 classification regression; no financial writer or real SBI rows."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r269_case24_financial_status_shadow import StatusEvidence, classify_shadow

BASE = StatusEvidence("SYN-UPLOAD-001",2,"1160.00",source_verified=True,
    unique_bank_event_verified=True,allocation_finalized=True,
    independent_allocation_oracle_passed=True,invoice_and_sol_verified=True,
    service_period_verified=True,tds_gst_credit_note_verified=True,
    fully_accounted_credit=True)

class TestCase24(unittest.TestCase):
    def result(self,e=BASE):
        r=classify_shadow(e)
        self.assertTrue(r["financial_apply_locked"])
        self.assertFalse(r["write_column_m"])
        self.assertIsNone(r["final_column_m_status"])
        self.assertEqual(r["real_database_writes"],0)
        self.assertFalse(r["full_v251_v239_certified"])
        return r["shadow_status"]
    def test_ok_is_still_only_candidate(self):
        self.assertEqual(self.result(),"OK_CANDIDATE")
    def test_no_matrix_only_auto_ok(self):
        for key in ("allocation_finalized","independent_allocation_oracle_passed",
                    "invoice_and_sol_verified","service_period_verified",
                    "tds_gst_credit_note_verified","fully_accounted_credit",
                    "unique_bank_event_verified"):
            with self.subTest(key=key):
                self.assertEqual(self.result(replace(BASE,**{key:False})),"REVIEW_REQUIRED")
    def test_independently_proven_duplicate_candidate(self):
        self.assertEqual(self.result(replace(BASE,allocation_finalized=False,
            independently_proven_duplicate=True,duplicate_reference_verified=True)),
            "DUPLICATE_PAYMENT_CANDIDATE")
    def test_duplicate_without_independent_proof_held(self):
        self.assertEqual(self.result(replace(BASE,duplicate_reference_verified=True)),
            "REVIEW_REQUIRED")
    def test_duplicate_and_allocation_conflict_held(self):
        self.assertEqual(self.result(replace(BASE,independently_proven_duplicate=True,
            duplicate_reference_verified=True)),"REVIEW_REQUIRED")
    def test_verified_no_match(self):
        self.assertEqual(self.result(replace(BASE,allocation_finalized=False,
            certified_no_match=True)),"SUSPENSE_CANDIDATE")
    def test_no_match_unverified_event_held(self):
        self.assertEqual(self.result(replace(BASE,allocation_finalized=False,
            certified_no_match=True,unique_bank_event_verified=False)),"REVIEW_REQUIRED")
    def test_source_invalid_or_negative(self):
        for amount in ("-1","0","NaN","Infinity","error","10.001",""):
            with self.subTest(amount=amount):
                self.assertEqual(self.result(replace(BASE,original_credit=amount)),"REVIEW_REQUIRED")
    def test_protected_and_contested_hold(self):
        for k in ("protected_prior_status","competing_invoice_or_bank_hold","unresolved_exception"):
            self.assertEqual(self.result(replace(BASE,**{k:True})),"REVIEW_REQUIRED")
    def test_missing_verification_holds(self):
        self.assertEqual(self.result(replace(BASE,source_verified=False)),"REVIEW_REQUIRED")
    def test_forced_financial_unlock_refused(self):
        with self.assertRaisesRegex(ValueError,"LOCKED"):
            classify_shadow(BASE,financial_apply="ENABLED")
    def test_bad_source_row_refused(self):
        with self.assertRaises(ValueError):
            classify_shadow(replace(BASE,bank_source_row=1))
    def test_non_boolean_input_refused(self):
        with self.assertRaisesRegex(ValueError,"BOOLEAN"):
            classify_shadow(replace(BASE,source_verified=1))
    def test_partial_payment_without_final_accounting_holds(self):
        self.assertEqual(self.result(replace(BASE,fully_accounted_credit=False)),"REVIEW_REQUIRED")

if __name__=="__main__":
    unittest.main()
