"""R26.9 Case 2.1 atomic cash ledger — self-contained synthetic QA fixtures."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r269_core_cash_ledger_dry_run import (
    InvoiceCapacity, BankCapacity, MatrixProposal, GlobalAdjudicationBoundary,
    LedgerRefusal, plan_digest, dry_run_cash_ledger,
)

A="a"*64
B="b"*64
def inv(**kw):
    return replace(InvoiceCapacity("MXP10001",2,"1180.00"),**kw)
def bank(**kw):
    return replace(BankCapacity("SYN-PAY-001",2,"1160.00"),**kw)
def prop(**kw):
    return replace(MatrixProposal("SYN-PAY-001","MXP10001","1160.00",
                   "EXACT_MXP_REVIEW","SYN-EVIDENCE-001"),**kw)
def run(invoices=None,banks=None,steps=None,**extra):
    invoices=[inv()] if invoices is None else invoices
    banks=[bank()] if banks is None else banks
    steps=[prop(),GlobalAdjudicationBoundary()] if steps is None else steps
    return dry_run_cash_ledger(
       invoices,banks,steps,source_sha256=A,master_sha256=B,
       expected_plan_sha256=plan_digest(steps),**extra,
    )


class CoreLedgerDryRunQA(unittest.TestCase):
    def check_hold(self,code,**kw):
        with self.assertRaisesRegex(LedgerRefusal,code):
            run(**kw)
    def test_01_exact_cash_rest_is_only_cash_gap(self):
        r=run()
        self.assertEqual(r["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(r["shadow_cash_coverage_gap_not_receivable"],"20.00")
        self.assertEqual(r["shadow_unassigned_credit_total"],"0.00")
    def test_02_credit_conservation(self):
        self.assertTrue(run()["bank_global_cash_conserved"])
    def test_03_invoice_cash_conservation(self):
        self.assertTrue(run()["invoice_global_cash_conserved"])
    def test_04_no_real_payment_allocations(self):
        self.assertEqual(run()["real_bank_allocations"],0)
    def test_05_no_real_database_writes(self):
        self.assertEqual(run()["real_database_writes"],0)
    def test_06_no_paid_status(self):
        self.assertIsNone(run()["financial_status"])
    def test_07_no_certification_claim(self):
        self.assertFalse(run()["complete_master_v251_matrix_v239_certified"])
    def test_08_financial_apply_unlocked_rejected(self):
        self.check_hold("FINANCIAL_APPLY_LOCK_REQUIRED",financial_apply="ENABLED")
    def test_09_duplicate_invoice_number_refused(self):
        self.check_hold("DUPLICATE_INVOICE_IDENTITY",invoices=[inv(),inv(source_row=3)])
    def test_10_duplicate_invoice_source_row_refused(self):
        self.check_hold("DUPLICATE_INVOICE_IDENTITY",
                        invoices=[inv(),inv(invoice_no="MXP10002")])
    def test_11_duplicate_bank_key_refused(self):
        self.check_hold("DUPLICATE_BANK_IDENTITY",banks=[bank(),bank(source_row=3)])
    def test_12_duplicate_bank_source_row_refused(self):
        self.check_hold("DUPLICATE_BANK_IDENTITY",
                        banks=[bank(),bank(bank_key="SYN-PAY-002")])
    def test_13_protected_invoice_s_zero_refused(self):
        self.check_hold("PROTECTED_INVOICE_S_NONBLANK",invoices=[inv(original_s=0)])
    def test_14_protected_invoice_s_text_refused(self):
        self.check_hold("PROTECTED_INVOICE_S_NONBLANK",invoices=[inv(original_s="Paid")])
    def test_15_protected_bank_k_zero_refused(self):
        self.check_hold("PROTECTED_BANK_K_NONBLANK",banks=[bank(original_k=0)])
    def test_16_protected_bank_k_text_refused(self):
        self.check_hold("PROTECTED_BANK_K_NONBLANK",banks=[bank(original_k="OK")])
    def test_17_payment_credit_overdraw_refused(self):
        self.check_hold("BANK_CREDIT_CAPACITY_EXCEEDED",
                        steps=[prop(portion="1160.01"),GlobalAdjudicationBoundary()])
    def test_18_invoice_cash_overdraw_refused(self):
        self.check_hold("INVOICE_CASH_CAPACITY_EXCEEDED",
                        steps=[prop(portion="1180.01"),GlobalAdjudicationBoundary()],
                        banks=[bank(credit="1200.00")])
    def test_19_one_payment_split_two_invoices(self):
        p=bank(credit="1500.00")
        a=inv(gross="1000.00")
        b=inv(invoice_no="MXP10002",source_row=3,gross="800.00")
        steps=[prop(portion="1000.00"),prop(invoice_no="MXP10002",
                portion="500.00",evidence_ref="SYN-EVIDENCE-002"),
               GlobalAdjudicationBoundary()]
        r=run(invoices=[a,b],banks=[p],steps=steps)
        self.assertEqual(r["shadow_reserved_cash_total"],"1500.00")
        self.assertEqual(r["shadow_cash_coverage_gap_not_receivable"],"300.00")
        self.assertEqual(len(r["shadow_edges"]),2)
    def test_20_two_payments_one_invoice(self):
        b=[bank(credit="500.00"),bank(bank_key="SYN-PAY-002",
                                    source_row=3,credit="680.00")]
        steps=[prop(portion="500.00",method="PARTIAL_REVIEW"),
               prop(bank_key="SYN-PAY-002",portion="680.00",
                    evidence_ref="SYN-EVIDENCE-002",method="PARTIAL_REVIEW"),
               GlobalAdjudicationBoundary()]
        r=run(banks=b,steps=steps)
        self.assertEqual(r["shadow_invoice_cash_rows"][0][-1],"0.00")
        self.assertEqual(len(r["shadow_edges"]),2)
    def test_21_two_payments_overdraw_invoice(self):
        b=[bank(credit="600.00"),bank(bank_key="SYN-PAY-002",
                                     source_row=3,credit="600.00")]
        steps=[prop(portion="600.00",method="PARTIAL_REVIEW"),
               prop(bank_key="SYN-PAY-002",portion="600.00",
                    evidence_ref="SYN-EVIDENCE-002",method="PARTIAL_REVIEW"),
               GlobalAdjudicationBoundary()]
        self.check_hold("INVOICE_CASH_CAPACITY_EXCEEDED",
                        banks=b,steps=steps)
    def test_22_duplicate_pair_rejected(self):
        steps=[prop(portion="500.00"),
               prop(portion="100.00",evidence_ref="SYN-EVIDENCE-002"),
               GlobalAdjudicationBoundary()]
        self.check_hold("DUPLICATE_BANK_INVOICE_EDGE",steps=steps)
    def test_23_no_global_boundary_refused(self):
        self.check_hold("GLOBAL_ADJUDICATION_BOUNDARY_REQUIRED",steps=[prop()])
    def test_24_two_global_boundaries_refused(self):
        self.check_hold("GLOBAL_ADJUDICATION_REPEATED_OR_INVALID",
                        steps=[prop(),GlobalAdjudicationBoundary(),
                               GlobalAdjudicationBoundary()])
    def test_25_waterfall_before_global_refused(self):
        self.check_hold("WATERFALL_BEFORE_GLOBAL_ADJUDICATION",
                        steps=[prop(method="WATERFALL_REVIEW"),GlobalAdjudicationBoundary()])
    def test_26_prior_method_after_boundary_refused(self):
        self.check_hold("EARLIER_METHOD_AFTER_WATERFALL_BOUNDARY",
                        steps=[GlobalAdjudicationBoundary(),prop()])
    def test_27_waterfall_last_accepted_synthetic(self):
        r=run(steps=[GlobalAdjudicationBoundary(),
                     prop(method="WATERFALL_REVIEW")])
        self.assertEqual(r["shadow_reserved_cash_total"],"1160.00")
    def test_28_provisional_dnm_not_reservable(self):
        self.check_hold("PROVISIONAL_DNM_CANNOT_RESERVE_CASH",
                        steps=[prop(method="DNM_PROVISIONAL"),GlobalAdjudicationBoundary()])
    def test_29_unapproved_method_refused(self):
        self.check_hold("UNAPPROVED_ALLOCATION_METHOD",
                        steps=[prop(method="AUTO_FORCE_OK"),GlobalAdjudicationBoundary()])
    def test_30_unknown_payment_refused(self):
        self.check_hold("UNKNOWN_BANK_OR_INVOICE_ID",
                        steps=[prop(bank_key="SYN-PAY-999"),GlobalAdjudicationBoundary()])
    def test_31_unknown_invoice_refused(self):
        self.check_hold("UNKNOWN_BANK_OR_INVOICE_ID",
                        steps=[prop(invoice_no="MXP19999"),GlobalAdjudicationBoundary()])
    def test_32_missing_evidence_refused(self):
        self.check_hold("EXPLICIT_CANDIDATE_EVIDENCE_REF_REQUIRED",
                        steps=[prop(evidence_ref=""),GlobalAdjudicationBoundary()])
    def test_33_missing_plan_hash_refused(self):
        s=[prop(),GlobalAdjudicationBoundary()]
        with self.assertRaisesRegex(LedgerRefusal,"ALLOCATION_PLAN_SHA256_MISMATCH"):
            dry_run_cash_ledger([inv()],[bank()],s,source_sha256=A,
                                master_sha256=B,expected_plan_sha256="0"*64)
    def test_34_hash_format_refused(self):
        s=[prop(),GlobalAdjudicationBoundary()]
        with self.assertRaisesRegex(LedgerRefusal,"THREE_EXPLICIT_SHA256_MANIFESTS_REQUIRED"):
            dry_run_cash_ledger([inv()],[bank()],s,source_sha256="bad",
                                master_sha256=B,expected_plan_sha256=plan_digest(s))
    def test_35_cash_precision_subpaise_refused(self):
        self.check_hold("NONFINITE_OR_SUBPAISE_MONEY_REFUSED",
                        banks=[bank(credit="1160.001")])
    def test_36_float_cash_refused(self):
        self.check_hold("EXACT_DECIMAL_MONEY_REQUIRED",banks=[bank(credit=1160.0)])
    def test_37_nan_cash_refused(self):
        self.check_hold("NONFINITE_OR_SUBPAISE_MONEY_REFUSED",
                        banks=[bank(credit="NaN")])
    def test_38_negative_invoice_gross_refused(self):
        self.check_hold("NONPOSITIVE_INVOICE_GROSS",invoices=[inv(gross="-10.00")])
    def test_39_negative_bank_credit_refused(self):
        self.check_hold("NONPOSITIVE_BANK_CREDIT",banks=[bank(credit="-20.00")])
    def test_40_zero_allocation_refused(self):
        self.check_hold("NONPOSITIVE_CASH_ALLOCATION",
                        steps=[prop(portion="0.00"),GlobalAdjudicationBoundary()])
    def test_41_opening_invoice_cash_gap_is_not_receivable(self):
        r=run()
        self.assertIn("shadow_cash_coverage_gap_not_receivable",r)
        self.assertNotIn("outstanding_certified",r)
    def test_42_nonzero_unassigned_cash_kept_unreserved(self):
        r=run(banks=[bank(credit="2000.00")])
        self.assertEqual(r["shadow_unassigned_credit_total"],"840.00")
    def test_43_no_waterfall_valid_with_boundary(self):
        r=run(steps=[prop(),GlobalAdjudicationBoundary()])
        self.assertTrue(r["one_global_boundary_before_waterfall"])
    def test_44_empty_input_with_global_checkpoint(self):
        r=run(invoices=[],banks=[],steps=[GlobalAdjudicationBoundary()])
        self.assertEqual(r["shadow_reserved_cash_total"],"0.00")
    def test_45_source_order_preserved_in_audit(self):
        r=run()
        self.assertEqual(r["shadow_bank_rows"][0][1],2)
        self.assertEqual(r["shadow_invoice_cash_rows"][0][1],2)
    def test_46_rerun_same_plan_identical(self):
        a=run();b=run()
        self.assertEqual(a,b)
    def test_47_source_input_not_mutated(self):
        iv=[inv()]; b=[bank()];s=[prop(),GlobalAdjudicationBoundary()]
        before=(repr(iv),repr(b),repr(s))
        run(invoices=iv,banks=b,steps=s)
        self.assertEqual(before,(repr(iv),repr(b),repr(s)))
    def test_48_no_actual_full_certification_from_technical_pass(self):
        r=run()
        self.assertFalse(r["production_release_authorized"])
        self.assertTrue(r["financial_apply_locked"])


if __name__=="__main__":
    unittest.main()
