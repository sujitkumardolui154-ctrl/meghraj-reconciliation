"""R26.3 shadow adjudication tests: fictitious payments only; no database."""
import sys
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
from sbi_r26_independent_financial_oracle import Invoice, Payment, R26Refusal
from sbi_r262_rebuild_candidate_planner import fixture_digest
from sbi_r263_global_allocation_shadow import (
    SyntheticProof, Proposal, GlobalGate, R263Refusal,
    proposal_digest, shadow_adjudicate,
)

MASTER = (
    ("0001", "SYNTHETIC ALPHA"),
    ("0002", "SYNTHETIC BETA"),
    ("1", "SYNTHETIC ALPHA"),
)

def inv(**kwargs):
    obj = Invoice(
        "SYN-MXP-001", "0001", "SYNTHETIC ALPHA", "1000.00",
        "90.00", "90.00", "1180.00", "1180.00",
        date(2026,9,1), ("2026-09",),
    )
    return replace(obj,**kwargs)

def pay(**kwargs):
    obj = Payment(
        "SYN-PAY-001", "0001", "SYNTHETIC ALPHA",
        "1160.00", date(2026,9,15), ("2026-09",),
        ("SYN-MXP-001",),
    )
    return replace(obj,**kwargs)

def prop(**kwargs):
    obj = Proposal("SYN-PAY-001","SYN-MXP-001","1160.00","STANDARD","")
    return replace(obj,**kwargs)

def proof(kind="PARTIAL", *, key="SYN-PROOF-001",
          p="SYN-PAY-001", i="SYN-MXP-001", authority="SYNTHETIC_QA_ONLY"):
    return SyntheticProof(key,kind,p,i,authority)

def run(invoices=None, payments=None, steps=None, proofs=(), master=MASTER,
        **extra):
    invoices = [inv()] if invoices is None else list(invoices)
    payments = [pay()] if payments is None else list(payments)
    steps = [prop(),GlobalGate()] if steps is None else list(steps)
    return shadow_adjudicate(
        invoices,payments,list(master),steps,list(proofs),
        expected_fixture_sha256=fixture_digest(invoices,payments,list(master)),
        expected_plan_sha256=proposal_digest(steps,list(proofs)),
        **extra,
    )

class R263AtomicGlobalLedgerTests(unittest.TestCase):
    def test_01_full_exact_credit_shadow_passes(self):
        r=run()
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertEqual(r["shadow_candidate_edges"],
            (("SYN-PAY-001","SYN-MXP-001","1160.00","STANDARD"),))
        self.assertEqual(r["shadow_credit_balance"],(("SYN-PAY-001","0.00"),))
        self.assertEqual(r["shadow_invoice_cash_coverage_gap"],(("SYN-MXP-001","20.00"),))
        self.assertTrue(r["tds_withheld_not_recognized_as_cash_or_invoice_settlement"])

    def test_02_tds_gap_not_financial_settlement(self):
        r=run()
        self.assertIsNone(r["financial_status"])
        self.assertEqual(r["real_bank_payments_allocated"],0)
        self.assertEqual(r["real_invoice_status_updates"],0)
        self.assertEqual(r["real_database_writes"],0)
        self.assertTrue(r["financial_apply_locked"])
        self.assertFalse(r["complete_master_v251_matrix_v239_certified"])

    def test_03_zero_tds_full_gross_cash(self):
        r=run(payments=[pay(credit="1180.00")],
              steps=[prop(credit_portion="1180.00"),GlobalGate()])
        self.assertEqual(r["shadow_invoice_cash_coverage_gap"],
                         (("SYN-MXP-001","0.00"),))

    def test_04_two_partial_payments_one_invoice_in_memory(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="580.00")
        steps=[
            prop(credit_portion="600.00",kind="PARTIAL_REVIEW",proof_key="SYN-PROOF-001"),
            prop(payment_key="SYN-PAY-002",credit_portion="580.00",
                 kind="PARTIAL_REVIEW",proof_key="SYN-PROOF-002"),
            GlobalGate(),
        ]
        proofs=[proof(),proof(key="SYN-PROOF-002",p="SYN-PAY-002")]
        r=run(payments=[p1,p2],steps=steps,proofs=proofs)
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertEqual(len(r["shadow_candidate_edges"]),2)
        self.assertEqual(r["shadow_invoice_cash_coverage_gap"],
                         (("SYN-MXP-001","0.00"),))

    def test_05_partial_credit_only_leaves_gap(self):
        r=run(payments=[pay(credit="600.00")],
              steps=[prop(credit_portion="600.00",kind="PARTIAL_REVIEW",
                          proof_key="SYN-PROOF-001"),GlobalGate()],
              proofs=[proof()])
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertEqual(r["shadow_invoice_cash_coverage_gap"],
                         (("SYN-MXP-001","580.00"),))

    def test_06_waterfall_cash_split_two_invoices_after_gate(self):
        i1=inv(taxable="500.00",cgst="45.00",sgst="45.00",
               gross="590.00",outstanding="590.00")
        i2=replace(i1,key="SYN-MXP-002")
        p=pay(credit="1000.00",mxp_refs=())
        steps=[GlobalGate(),
               prop(credit_portion="590.00",kind="WATERFALL",
                    proof_key="SYN-PROOF-001"),
               prop(invoice_key="SYN-MXP-002",credit_portion="410.00",
                    kind="WATERFALL",proof_key="SYN-PROOF-002")]
        proofs=[proof("WATERFALL"),proof("WATERFALL",key="SYN-PROOF-002",i="SYN-MXP-002")]
        r=run(invoices=[i1,i2],payments=[p],steps=steps,proofs=proofs)
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertEqual(r["shadow_credit_balance"],(("SYN-PAY-001","0.00"),))
        self.assertEqual(r["shadow_invoice_cash_coverage_gap"],
                         (("SYN-MXP-001","0.00"),("SYN-MXP-002","180.00")))

    def test_07_waterfall_before_gate_is_atomic_rejection(self):
        r=run(payments=[pay(mxp_refs=())],
              steps=[prop(kind="WATERFALL",proof_key="SYN-PROOF-001"),GlobalGate()],
              proofs=[proof("WATERFALL")])
        self.assertIn("WATERFALL_BEFORE_GLOBAL_GATE",r["blocker_codes"])
        self.assertEqual(r["shadow_candidate_edges"],())
        self.assertEqual(r["shadow_credit_balance"],())

    def test_08_earlier_matching_after_gate_rejected(self):
        r=run(steps=[GlobalGate(),prop()])
        self.assertIn("EARLIER_MATCHING_AFTER_GLOBAL_GATE",r["blocker_codes"])

    def test_09_global_gate_required(self):
        r=run(steps=[prop()])
        self.assertIn("GLOBAL_GATE_MISSING",r["blocker_codes"])

    def test_10_repeated_gate_refused(self):
        r=run(steps=[prop(),GlobalGate(),GlobalGate("SYN-GATE-002")])
        self.assertIn("GLOBAL_GATE_REPEATED",r["blocker_codes"])

    def test_11_waterfall_overcommitted_credit_atomic_rejection(self):
        i1=inv()
        i2=inv(key="SYN-MXP-002")
        p=pay(credit="1000.00",mxp_refs=())
        s=[GlobalGate(),prop(kind="WATERFALL",credit_portion="700.00",proof_key="SYN-PROOF-001"),
           prop(invoice_key="SYN-MXP-002",kind="WATERFALL",credit_portion="700.00",
                proof_key="SYN-PROOF-002")]
        proofs=[proof("WATERFALL"),proof("WATERFALL",key="SYN-PROOF-002",i="SYN-MXP-002")]
        r=run(invoices=[i1,i2],payments=[p],steps=s,proofs=proofs)
        self.assertIn("SHADOW_PAYMENT_CREDIT_OVERALLOCATED",r["blocker_codes"])
        self.assertFalse(r["atomic_shadow_review_pass"])
        self.assertEqual(r["shadow_candidate_edges"],())

    def test_12_two_partials_over_invoice_outstanding_rejected(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="600.00")
        s=[prop(kind="PARTIAL_REVIEW",credit_portion="600.00",proof_key="SYN-PROOF-001"),
           prop(payment_key="SYN-PAY-002",kind="PARTIAL_REVIEW",
                credit_portion="600.00",proof_key="SYN-PROOF-002"),GlobalGate()]
        r=run(payments=[p1,p2],steps=s,
              proofs=[proof(),proof(key="SYN-PROOF-002",p="SYN-PAY-002")])
        self.assertIn("SHADOW_INVOICE_OUTSTANDING_OVERALLOCATED",r["blocker_codes"])
        self.assertEqual(r["shadow_candidate_edges"],())

    def test_13_duplicate_payment_invoice_edge_rejected(self):
        r=run(steps=[prop(),prop(),GlobalGate()])
        self.assertIn("REPEATED_PAYMENT_INVOICE_EDGE",r["blocker_codes"])

    def test_14_duplicate_source_payment_key_quarantined(self):
        r=run(payments=[pay(),pay()])
        self.assertIn("DUPLICATE_SOURCE_PAYMENT",r["blocker_codes"])

    def test_15_duplicate_source_invoice_key_quarantined(self):
        r=run(invoices=[inv(),inv()])
        self.assertIn("DUPLICATE_SOURCE_INVOICE",r["blocker_codes"])

    def test_16_original_bank_k_status_is_protected(self):
        r=run(payments=[pay(original_k="OK")])
        self.assertIn("ORIGINAL_K_OR_S_PROTECTED",r["blocker_codes"])

    def test_17_original_invoice_s_zero_is_protected(self):
        r=run(invoices=[inv(source_s_marker=0)])
        self.assertIn("ORIGINAL_K_OR_S_PROTECTED",r["blocker_codes"])

    def test_18_cross_sol_without_proof_held(self):
        r=run(payments=[pay(sol="0002",client="SYNTHETIC BETA")])
        self.assertIn("SAME_SOL_OFFICIAL_IDENTITY_NOT_VERIFIED",r["blocker_codes"])

    def test_19_leading_zero_not_silently_merged(self):
        r=run(payments=[pay(sol="1")])
        self.assertIn("SAME_SOL_OFFICIAL_IDENTITY_NOT_VERIFIED",r["blocker_codes"])

    def test_20_missing_exact_official_master_pair_held(self):
        r=run(master=(("0002","SYNTHETIC BETA"),))
        self.assertIn("SAME_SOL_OFFICIAL_IDENTITY_NOT_VERIFIED",r["blocker_codes"])

    def test_21_client_name_difference_held(self):
        r=run(payments=[pay(client="SYNTHETIC OTHER")])
        self.assertIn("SAME_SOL_OFFICIAL_IDENTITY_NOT_VERIFIED",r["blocker_codes"])

    def test_22_bank_before_invoice_held(self):
        r=run(payments=[pay(bank_date=date(2026,8,1))])
        self.assertIn("BANK_DATE_BEFORE_INVOICE",r["blocker_codes"])

    def test_23_wrong_service_month_held(self):
        r=run(payments=[pay(service_periods=("2026-08",))])
        self.assertIn("SERVICE_PERIOD_NOT_FULLY_VERIFIED",r["blocker_codes"])

    def test_24_complete_multimonth_period_is_eligible(self):
        i=inv(service_periods=("2026-03","2026-04","2026-05"))
        p=pay(service_periods=("2026-03","2026-04","2026-05"))
        self.assertTrue(run(invoices=[i],payments=[p])["atomic_shadow_review_pass"])

    def test_25_contradictory_invoice_ref_held(self):
        r=run(payments=[pay(mxp_refs=("SYN-MXP-002",))])
        self.assertIn("CONTRADICTORY_MXP_REFERENCE",r["blocker_codes"])

    def test_26_multiple_mxp_refs_held(self):
        r=run(payments=[pay(mxp_refs=("SYN-MXP-001","SYN-MXP-002"))])
        self.assertIn("MULTIPLE_MXP_REFERENCES",r["blocker_codes"])

    def test_27_standard_without_exact_ref_held(self):
        r=run(payments=[pay(mxp_refs=())])
        self.assertIn("STANDARD_EXACT_REFERENCE_REQUIRED",r["blocker_codes"])

    def test_28_standard_inexact_tds_value_held(self):
        p=pay(credit="1160.01")
        r=run(payments=[p],steps=[prop(credit_portion="1160.01"),GlobalGate()])
        self.assertIn("EXACT_TDS_HYPOTHESIS_NOT_UNIQUE",r["blocker_codes"])

    def test_29_standard_split_amount_without_partial_proof_held(self):
        r=run(steps=[prop(credit_portion="100.00"),GlobalGate()])
        self.assertIn("STANDARD_EDGE_MUST_COVER_EXACT_CREDIT",r["blocker_codes"])

    def test_30_partial_without_explicit_proof_held(self):
        r=run(payments=[pay(credit="600.00")],
              steps=[prop(credit_portion="600.00",kind="PARTIAL_REVIEW"),GlobalGate()])
        self.assertIn("PARTIAL_RECEIPT_DOCUMENTARY_PROOF_REQUIRED",r["blocker_codes"])

    def test_31_partial_proof_for_other_invoice_not_reused(self):
        r=run(payments=[pay(credit="600.00")],
              steps=[prop(credit_portion="600.00",kind="PARTIAL_REVIEW",
                          proof_key="SYN-PROOF-001"),GlobalGate()],
              proofs=[proof(i="SYN-MXP-002")],
              invoices=[inv(),inv(key="SYN-MXP-002")])
        self.assertIn("PARTIAL_RECEIPT_DOCUMENTARY_PROOF_REQUIRED",r["blocker_codes"])

    def test_32_forged_real_authority_value_refused(self):
        with self.assertRaisesRegex(R263Refusal,"REAL_OR_UNSUPPORTED_PROOF_REFUSED"):
            run(proofs=[proof(authority="SIGNED_PRODUCTION_APPROVAL")])

    def test_33_gst_component_with_fictitious_proof_is_shadow_only(self):
        p=pay(credit="180.00",gst_narration=True)
        s=[prop(credit_portion="180.00",kind="GST_REVIEW",proof_key="SYN-PROOF-001"),GlobalGate()]
        r=run(payments=[p],steps=s,proofs=[proof("GST")])
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertTrue(r["sbisa_cross_sol_gst_proofs_are_fictitious"])
        self.assertEqual(r["real_bank_payments_allocated"],0)

    def test_34_gst_component_without_proof_held(self):
        p=pay(credit="180.00",gst_narration=True)
        r=run(payments=[p],steps=[prop(credit_portion="180.00",kind="GST_REVIEW"),GlobalGate()])
        self.assertIn("GST_COMPONENT_DOCUMENTARY_PROOF_REQUIRED",r["blocker_codes"])

    def test_35_gst_amount_above_original_tax_held(self):
        p=pay(credit="200.00",gst_narration=True)
        r=run(payments=[p],steps=[
            prop(credit_portion="200.00",kind="GST_REVIEW",proof_key="SYN-PROOF-001"),
            GlobalGate()],proofs=[proof("GST")])
        self.assertIn("GST_PORTION_EXCEEDS_INVOICE_GST",r["blocker_codes"])

    def test_36_gst_proof_without_narration_held(self):
        r=run(payments=[pay(credit="180.00")],steps=[
            prop(credit_portion="180.00",kind="GST_REVIEW",proof_key="SYN-PROOF-001"),
            GlobalGate()],proofs=[proof("GST")])
        self.assertIn("GST_COMPONENT_DOCUMENTARY_PROOF_REQUIRED",r["blocker_codes"])

    def test_37_sbisa_blank_invoice_sol_synthetic_proof(self):
        i=inv(sol="")
        p=pay(sol="1")
        r=run(invoices=[i],payments=[p],steps=[
            prop(kind="SBISA_REVIEW",proof_key="SYN-PROOF-001"),GlobalGate()],
            proofs=[proof("SBISA")])
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertFalse(r["authoritative_oct27_master_data_loaded"])

    def test_38_sbisa_without_explicit_proof_held(self):
        r=run(invoices=[inv(sol="")],payments=[pay(sol="1")],
              steps=[prop(kind="SBISA_REVIEW"),GlobalGate()])
        self.assertIn("SBISA_DOCUMENTARY_RELATIONSHIP_NOT_VERIFIED",r["blocker_codes"])

    def test_39_cross_sol_with_two_master_identities_and_proof(self):
        p=pay(sol="0002",client="SYNTHETIC BETA")
        r=run(payments=[p],steps=[
            prop(kind="CROSS_SOL_REVIEW",proof_key="SYN-PROOF-001"),GlobalGate()],
            proofs=[proof("CROSS_SOL")])
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertEqual(r["real_database_writes"],0)

    def test_40_cross_sol_without_proof_held(self):
        r=run(payments=[pay(sol="0002",client="SYNTHETIC BETA")],
              steps=[prop(kind="CROSS_SOL_REVIEW"),GlobalGate()])
        self.assertIn("CROSS_SOL_DOCUMENTARY_RELATIONSHIP_NOT_VERIFIED",r["blocker_codes"])

    def test_41_cross_sol_wrong_same_source_sol_not_exception(self):
        r=run(steps=[prop(kind="CROSS_SOL_REVIEW",proof_key="SYN-PROOF-001"),GlobalGate()],
              proofs=[proof("CROSS_SOL")])
        self.assertIn("CROSS_SOL_DOCUMENTARY_RELATIONSHIP_NOT_VERIFIED",r["blocker_codes"])

    def test_42_dnm_review_never_reserves_cash(self):
        r=run(payments=[pay(mxp_refs=())],
              steps=[prop(kind="DNM_REVIEW"),GlobalGate()])
        self.assertTrue(r["atomic_shadow_review_pass"])
        self.assertEqual(r["dnm_provisional_edges_held"],1)
        self.assertEqual(r["shadow_candidate_edges"],())
        self.assertEqual(r["shadow_credit_balance"],(("SYN-PAY-001","1160.00"),))

    def test_43_dnm_with_contradictory_reference_aborts(self):
        r=run(payments=[pay(mxp_refs=("SYN-MXP-002",))],
              steps=[prop(kind="DNM_REVIEW"),GlobalGate()])
        self.assertIn("CONTRADICTORY_MXP_REFERENCE",r["blocker_codes"])

    def test_44_explicit_plan_digest_required(self):
        with self.assertRaisesRegex(R263Refusal,"EXPLICIT_PLAN_SHA256_REQUIRED"):
            shadow_adjudicate([inv()],[pay()],MASTER,[prop(),GlobalGate()],
                expected_fixture_sha256=fixture_digest([inv()],[pay()],MASTER),
                expected_plan_sha256="bad")

    def test_45_stale_plan_digest_refused(self):
        with self.assertRaisesRegex(R263Refusal,"PLAN_SHA256_MISMATCH"):
            shadow_adjudicate([inv()],[pay()],MASTER,[prop(),GlobalGate()],
                expected_fixture_sha256=fixture_digest([inv()],[pay()],MASTER),
                expected_plan_sha256="0"*64)

    def test_46_finance_apply_unlock_refused(self):
        with self.assertRaisesRegex(R263Refusal,"FINANCIAL_APPLY_CANNOT_BE_UNLOCKED"):
            run(financial_apply="ENABLED")

    def test_47_binary_float_amount_not_accepted(self):
        with self.assertRaisesRegex(R26Refusal,"UNSAFE_MONEY_TYPE"):
            run(steps=[prop(credit_portion=1.1),GlobalGate()])

    def test_48_real_invoice_identifier_refused(self):
        with self.assertRaisesRegex(R26Refusal,"SYNTHETIC_INVOICE_REQUIRED"):
            run(invoices=[inv(key="MXP19970")])

    def test_49_nonsynthetic_proof_id_refused(self):
        with self.assertRaisesRegex(R263Refusal,"REAL_OR_UNSUPPORTED_PROOF_REFUSED"):
            run(proofs=[proof(key="PROD-APPROVAL-1")])

    def test_50_invoice_without_unreserved_outstanding_rejected(self):
        r=run(invoices=[inv(outstanding="0.00")])
        self.assertIn("SHADOW_INVOICE_OUTSTANDING_OVERALLOCATED",r["blocker_codes"])

    def test_51_source_input_row_order_does_not_alter_balances(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="580.00")
        steps=[
            prop(credit_portion="600.00",kind="PARTIAL_REVIEW",proof_key="SYN-PROOF-001"),
            prop(payment_key="SYN-PAY-002",credit_portion="580.00",
                 kind="PARTIAL_REVIEW",proof_key="SYN-PROOF-002"),GlobalGate()]
        proofs=[proof(),proof(key="SYN-PROOF-002",p="SYN-PAY-002")]
        a=run(payments=[p1,p2],steps=steps,proofs=proofs)
        b=run(payments=[p2,p1],steps=steps,proofs=proofs)
        self.assertEqual(a,b)

    def test_52_invalid_proposal_kind_refused(self):
        with self.assertRaisesRegex(R263Refusal,"UNKNOWN_SIMULATED_METHOD"):
            run(steps=[prop(kind="APPLY_AND_MARK_OK"),GlobalGate()])

    def test_53_malformed_gate_refused(self):
        with self.assertRaisesRegex(R263Refusal,"INVALID_SYNTHETIC_GLOBAL_GATE"):
            run(steps=[prop(),GlobalGate("PROD-CUTOVER")])

    def test_54_duplicate_proof_id_refused(self):
        with self.assertRaisesRegex(R263Refusal,"DUPLICATE_SYNTHETIC_PROOF_ID"):
            run(proofs=[proof(),proof()])

    def test_55_source_master_with_numeric_sol_refused(self):
        from sbi_r262_rebuild_candidate_planner import RebuildRefusal
        with self.assertRaisesRegex(RebuildRefusal,"SYNTHETIC_MASTER_ONLY"):
            run(master=((1,"SYNTHETIC ALPHA"),))

if __name__ == "__main__":
    unittest.main()
