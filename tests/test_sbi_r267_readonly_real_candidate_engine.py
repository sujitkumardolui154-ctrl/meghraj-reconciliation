"""R26.7 real-schema-capable planner (fully synthetic review tests only)."""
from datetime import date
from dataclasses import replace
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r267_readonly_real_candidate_engine import (
    InvoiceInput,BankInput,RelationshipProof,FinancialReviewRefusal,
    plan_review_only,refs,cash,
)

M=[("0001","SYNTHETIC ALPHA"),("0002","SYNTHETIC BETA"),("1","SYNTHETIC ALPHA")]
H="a"*64
def i(**kw):
    return replace(InvoiceInput(2,"MXP10001","0001","SYNTHETIC ALPHA",
              date(2026,9,1),("2026-09",),"1000","90","90","1180"),**kw)
def p(**kw):
    return replace(BankInput(2,"0001","SYNTHETIC ALPHA",
              date(2026,9,15),("2026-09",),
              "POSTAGE SEPTEMBER 2026 MXP10001","1160"),**kw)
def run(invoices=None,payments=None,masters=M,proofs=(),**kw):
    return plan_review_only(
        [i()] if invoices is None else list(invoices),
        [p()] if payments is None else list(payments),
        list(masters),relationship_proofs=tuple(proofs),
        source_sha256=H,master_sha256=H,**kw)

class R267RealSchemaCandidateTests(unittest.TestCase):
    def test_01_exact_mxp_two_percent(self):
        r=run()
        self.assertEqual(r["review_method_counts"]["EXACT_MXP_TDS_REVIEW"],1)
        self.assertEqual(r["candidate_rows"][0][4],2)
    def test_02_finance_apply_remains_locked(self):
        r=run()
        self.assertTrue(r["financial_apply_locked"])
        self.assertEqual(r["real_database_writes"],0)
        self.assertFalse(r["production_release_authorized"])
        self.assertFalse(r["complete_master_v251_matrix_v239_certified"])
    def test_03_never_marks_actual_ok(self):
        self.assertEqual(run()["all_real_bank_statuses"],
                         "SUSPENSE_UNTIL_INDEPENDENT_FINANCE_APPROVAL")
    def test_04_zero_rate_exact(self):
        self.assertEqual(run(payments=[p(credit="1180")])["candidate_rows"][0][4],0)
    def test_05_one_rate_exact(self):
        self.assertEqual(run(payments=[p(credit="1170")])["candidate_rows"][0][4],1)
    def test_06_three_rate_exact(self):
        self.assertEqual(run(payments=[p(credit="1150")])["candidate_rows"][0][4],3)
    def test_07_half_up_correct(self):
        inv=i(taxable="105.50",cgst="6.25",sgst="6.25",gross="118.00")
        r=run(invoices=[inv],payments=[p(credit="114.83")])
        self.assertEqual(r["candidate_rows"][0][4],3)
    def test_08_no_float_financial_input(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"MONEY_MUST_BE_EXACT"):
            cash(10.1)
    def test_09_none_money_refused(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"MONEY_MUST_BE_EXACT"):
            run(invoices=[i(gross=None)])
    def test_10_nan_money_refused(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"NONFINITE_MONEY"):
            run(payments=[p(credit="NaN")])
    def test_11_duplicate_invoice_id_holds_all(self):
        r=run(invoices=[i(),i(source_row=3)])
        self.assertEqual(len(r["candidate_rows"]),0)
        self.assertEqual(len(r["invoice_quarantines"]),2)
    def test_12_numeric_sol_invoice_refused(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"INVOICE_SOL_NOT_EXACT_TEXT"):
            run(invoices=[i(sol=1)])
    def test_13_payment_numeric_sol_refused(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"BANK_SOL_NOT_EXACT_TEXT"):
            run(payments=[p(sol=1)])
    def test_14_invoice_s_zero_protected(self):
        r=run(invoices=[i(original_s=0)])
        self.assertEqual(r["candidate_rows"],())
        self.assertIn("PROTECTED_INVOICE_S_NONBLANK",r["invoice_quarantines"][0][1])
    def test_15_payment_k_zero_protected(self):
        r=run(payments=[p(original_k=0)])
        self.assertEqual(r["candidate_rows"],())
        self.assertIn("PROTECTED_BANK_K_NONBLANK",r["bank_review_holds"][0][1])
    def test_16_other_mxp_narration_does_not_guess(self):
        r=run(payments=[p(description="POSTAGE MXP19999 SEPTEMBER 2026")])
        self.assertIn("NAMED_MXP_UNAVAILABLE_OR_QUARANTINED",r["bank_review_holds"][0][1])
    def test_17_more_than_one_mxp_ref_holds(self):
        r=run(payments=[p(description="MXP10001 MXP10002 SEPTEMBER 2026")])
        self.assertIn("CONTRADICTORY_MULTIPLE_MXP_REFERENCES",r["bank_review_holds"][0][1])
    def test_18_unicode_lookalike_no_mxp_claim(self):
        self.assertEqual(refs("ＭＸＰ10001"),())
    def test_19_partial_only_with_documentary_approval(self):
        q=RelationshipProof(2,"MXP10001","PARTIAL","SYN-DOC-01",True)
        r=run(payments=[p(credit="500")],proofs=[q])
        self.assertEqual(r["candidate_rows"][0][3],"EXACT_MXP_PARTIAL_REVIEW")
    def test_20_partial_without_proof_held(self):
        r=run(payments=[p(credit="500")])
        self.assertIn("EXACT_MXP_AMOUNT_OR_PARTIAL_PROOF_MISSING",r["bank_review_holds"][0][1])
    def test_21_false_boolean_provenance_refused(self):
        q=RelationshipProof(2,"MXP10001","PARTIAL","SYN-DOC-01","True")
        with self.assertRaisesRegex(FinancialReviewRefusal,"DOCUMENTARY_CONFIRMATION_INVALID"):
            run(proofs=[q])
    def test_22_unconfirmed_document_hold(self):
        q=RelationshipProof(2,"MXP10001","PARTIAL","SYN-DOC-01",False)
        self.assertEqual(run(payments=[p(credit="500")],proofs=[q])["candidate_rows"],())
    def test_23_gst_narration_without_proof_held(self):
        r=run(payments=[p(description="GST SEPTEMBER 2026 MXP10001",credit="180")])
        self.assertIn("GST_LATER_APPROVAL_MISSING",r["bank_review_holds"][0][1])
    def test_24_gst_with_proof_candidate_only(self):
        q=RelationshipProof(2,"MXP10001","GST","SYN-DOC-02",True)
        r=run(payments=[p(description="GST SEPTEMBER 2026 MXP10001",credit="180")],proofs=[q])
        self.assertEqual(r["candidate_rows"][0][3],"GST_LATER_DOCUMENTED_CANDIDATE")
    def test_25_gst_with_proof_wrong_amount_held(self):
        q=RelationshipProof(2,"MXP10001","GST","SYN-DOC-02",True)
        r=run(payments=[p(description="GST SEPTEMBER 2026 MXP10001",credit="190")],proofs=[q])
        self.assertIn("GST_COMPONENT_NOT_EQUAL_SOURCE_TAX",r["bank_review_holds"][0][1])
    def test_26_cross_sol_requires_pair_document(self):
        r=run(payments=[p(sol="0002",client="SYNTHETIC BETA")])
        self.assertIn("CROSS_SOL_DOCUMENTARY_PROOF_REQUIRED",r["bank_review_holds"][0][1])
    def test_27_cross_sol_proof_candidate_never_ok(self):
        q=RelationshipProof(2,"MXP10001","CROSS_SOL","SYN-DOC-03",True)
        r=run(payments=[p(sol="0002",client="SYNTHETIC BETA")],proofs=[q])
        self.assertEqual(r["candidate_rows"][0][3],"EXACT_MXP_TDS_REVIEW")
        self.assertEqual(r["all_real_bank_statuses"],"SUSPENSE_UNTIL_INDEPENDENT_FINANCE_APPROVAL")
    def test_28_sbisa_without_document_hold(self):
        r=run(invoices=[i(sol="")],payments=[p(sol="1")])
        self.assertIn("SBISA_DOCUMENTARY_PROOF_REQUIRED",r["bank_review_holds"][0][1])
    def test_29_sbisa_with_document_review_only(self):
        q=RelationshipProof(2,"MXP10001","SBISA","SYN-DOC-04",True)
        r=run(invoices=[i(sol="")],payments=[p(sol="1")],proofs=[q])
        self.assertEqual(len(r["candidate_rows"]),1)
        self.assertTrue(r["financial_apply_locked"])
    def test_30_leading_zero_not_equivalent(self):
        r=run(payments=[p(sol="1")])
        self.assertIn("CROSS_SOL_DOCUMENTARY_PROOF_REQUIRED",r["bank_review_holds"][0][1])
    def test_31_unverified_official_name_hold(self):
        r=run(masters=[("0001","SYNTHETIC WRONG")])
        self.assertIn("SOL_CLIENT_NOT_IN_SELECTED_MASTER",r["bank_review_holds"][0][1])
    def test_32_invalid_month_hold(self):
        r=run(payments=[p(service_periods=("2026-08",))])
        self.assertIn("SERVICE_PERIOD_CONFLICT",r["bank_review_holds"][0][1])
    def test_33_multi_month_coverage(self):
        r=run(invoices=[i(service_periods=("2026-03","2026-04","2026-05"))],
              payments=[p(service_periods=("2026-03","2026-04","2026-05"))])
        self.assertEqual(len(r["candidate_rows"]),1)
    def test_34_multi_month_incomplete_hold(self):
        r=run(invoices=[i(service_periods=("2026-03","2026-04","2026-05"))],
              payments=[p(service_periods=("2026-05",))])
        self.assertIn("SERVICE_PERIOD_CONFLICT",r["bank_review_holds"][0][1])
    def test_35_bank_before_invoice_hold(self):
        r=run(payments=[p(bank_date=date(2026,8,1))])
        self.assertIn("INVOICE_AFTER_BANK_POSTING",r["bank_review_holds"][0][1])
    def test_36_nonnumeric_financial_tax_hold(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"INVALID_EXACT_MONEY"):
            run(invoices=[i(sgst="OK")])
    def test_37_gross_components_mismatch_quarantined(self):
        r=run(invoices=[i(gross="1190")])
        self.assertIn("INVOICE_GROSS_COMPONENTS_MISMATCH",r["invoice_quarantines"][0][1])
    def test_38_negative_credit_note_quarantined(self):
        r=run(invoices=[i(taxable="-100",gross="-118")])
        self.assertIn("NEGATIVE_GROSS_CREDIT_NOTE_REVIEW",r["invoice_quarantines"][0][1])
    def test_39_payment_nonpositive_hold(self):
        r=run(payments=[p(credit="0")])
        self.assertIn("NONPOSITIVE_BANK_CREDIT",r["bank_review_holds"][0][1])
    def test_40_duplicate_bank_row_quarantined(self):
        r=run(payments=[p(),p(credit="1160")])
        self.assertEqual(r["candidate_rows"],())
        self.assertIn("DUPLICATE_BANK_SOURCE_ROW",r["bank_review_holds"][0][1])
    def test_41_second_full_credit_cannot_overallocate(self):
        r=run(payments=[p(),p(source_row=3)])
        self.assertEqual(len(r["candidate_rows"]),1)
        self.assertIn("INVOICE_CASH_CAPACITY_CONFLICT",r["bank_review_holds"][0][1])
    def test_42_DNM_unique_review_not_reserved(self):
        r=run(payments=[p(description="POSTAGE SEPTEMBER 2026")])
        self.assertEqual(r["candidate_rows"][0][3],"DNM01_PROVISIONAL_NO_RESERVATION")
        self.assertEqual(r["global_cash_reserved_hypothesis_only"],"0.00")
    def test_43_DNM_missing_service_period_hold(self):
        r=run(payments=[p(description="POSTAGE",service_periods=())])
        self.assertIn("DNM_NO_ELIGIBLE_CANDIDATE",r["bank_review_holds"][0][1])
    def test_44_DNM_two_equal_competing_invoices(self):
        r=run(invoices=[i(),i(source_row=3,invoice_no="MXP10002")],
              payments=[p(description="POSTAGE SEPTEMBER 2026")])
        self.assertIn("DNM_AMBIGUOUS_RUNNER_UP",r["bank_review_holds"][0][1])
    def test_45_DNM_best_over_1_held(self):
        r=run(payments=[p(description="POSTAGE SEPTEMBER 2026",credit="1162")])
        self.assertIn("DNM_NEAREST_OVER_ONE_RUPEE",r["bank_review_holds"][0][1])
    def test_46_DNM_outside_180_days_hold(self):
        r=run(payments=[p(description="POSTAGE SEPTEMBER 2026",bank_date=date(2027,4,1))])
        self.assertIn("DNM_NO_ELIGIBLE_CANDIDATE",r["bank_review_holds"][0][1])
    def test_47_DNM_explicit_contradictory_ref_never_fallback(self):
        r=run(payments=[p(description="MXP99999 POSTAGE SEPTEMBER 2026")])
        self.assertNotIn("DNM01_PROVISIONAL",r["review_method_counts"])
    def test_48_finance_apply_unlock_refused(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"FINANCIAL_APPLY_LOCK_REQUIRED"):
            run(financial_apply="ENABLED")
    def test_49_source_sha_required(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"EXACT_SOURCE_AND_MASTER_SHA256_REQUIRED"):
            plan_review_only([i()],[p()],M,source_sha256="bad",master_sha256=H)
    def test_50_same_sol_mismatch_name_held(self):
        r=run(payments=[p(client="SYNTHETIC BETA")])
        self.assertIn("SOL_CLIENT_NOT_IN_SELECTED_MASTER",r["bank_review_holds"][0][1])
    def test_51_no_fuzzy_alias_auto_match(self):
        r=run(payments=[p(client="SYNTHETIC ALPHA OTHER")])
        self.assertEqual(r["candidate_rows"],())
    def test_52_date_type_must_be_date(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"BANK_CLIENT_OR_DATE_UNVERIFIED"):
            run(payments=[p(bank_date="2026-09-15")])
    def test_53_original_bank_description_not_text_hold(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"BANK_NARRATION_NOT_TEXT"):
            run(payments=[p(description=123)])
    def test_54_tds_not_financial_actual_tax_certificate(self):
        r=run()
        self.assertNotIn("OK",r["all_real_bank_statuses"])
        self.assertFalse(r["real_v218_financial_writer_certified"])
    def test_55_waterfall_requires_global_approval(self):
        r=run(payments=[p(description="POSTAGE SEPTEMBER 2026")])
        self.assertTrue(r["waterfall_only_after_global"])
    def test_56_missing_mxp_invoice_ref_holds(self):
        r=run(invoices=[i(invoice_no="NOT-MXP")])
        self.assertEqual(r["candidate_rows"],())
    def test_57_duplicate_name_different_sol_not_auto_merge(self):
        r=run(payments=[p(sol="0002")],
              masters=M+[("0002","SYNTHETIC ALPHA")])
        self.assertEqual(len(r["candidate_rows"]),0)
    def test_58_two_payment_partial_requires_document(self):
        qs=[RelationshipProof(2,"MXP10001","PARTIAL","SYN-DOC-1",True),
            RelationshipProof(3,"MXP10001","PARTIAL","SYN-DOC-2",True)]
        r=run(payments=[p(credit="500"),p(source_row=3,credit="660")],proofs=qs)
        self.assertEqual(len(r["candidate_rows"]),2)
        self.assertEqual(r["global_cash_reserved_hypothesis_only"],"1160.00")
    def test_59_non_whitelisted_method_never_written(self):
        r=run()
        self.assertEqual(r["all_real_bank_statuses"],"SUSPENSE_UNTIL_INDEPENDENT_FINANCE_APPROVAL")
    def test_60_reruns_deterministic(self):
        a=run();b=run();self.assertEqual(a,b)

if __name__=="__main__":unittest.main()
